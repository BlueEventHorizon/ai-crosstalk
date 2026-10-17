"""Orca の adapter。orca worktree ps / orca terminal list の出力を突き合わせて候補にする。

出力の形のうち、実機（Orca 1.4.220）で確認できたものと、確認できていないものを区別する。

確認できたもの:
- orca status --json: {"ok": true, "result": {"runtime": {"reachable": true, ...}}}
- orca worktree ps --json: {"ok": true, "result": {"worktrees": [...], "truncated": false}}
  各 worktree の repo / repoId / path / branch（"refs/heads/" 付き。detached では空文字）/
  worktreeId / workspaceKind / agents[]（paneKey / agentType / state）
- orca terminal list --json: {"ok": true, "result": {"terminals": [...], "truncated": false}}
  各 terminal の handle / worktreeId / tabId / leafId / agentIdentity（"claude" / "codex"。
  エージェントが居ない端末では項目ごと無い）
- terminal.worktreeId は worktree.worktreeId と一致し、worktrees[].agents[].paneKey は
  terminal の "<tabId>:<leafId>" と一致する（環境変数 ORCA_PANE_KEY も同じ形）

確認できていないもの:
- "projectId" 項目: 確認した版の worktree ps には現れなかった。項目があり、かつ空のときは
  リポジトリに紐づかない worktree として扱う（項目が無いことは紐づきの有無を意味しない）
- "ok": false のときの error の形（error 項目をそのまま reason に載せる）
- workspaceKind が "git" 以外の値

受信側の状態（receiver_state）で確認できたもの・できていないもの:
- Claude Code: worktree ps の agents[].state は "done" と "working" を確認した。他の値は未確認
  のため、推測せず unknown にする。paneKey に対応する記録が無い場合（記録が遅れている等）も
  unknown にする。unknown は「状態を確認できなかった」旨を添えてユーザーが判断する扱いで、
  期待と異なる出力を error で止める他の箇所と違い、状態の判定では安全側（送らない・ユーザーに
  聞く）に倒せるため、error にはしない。
- Codex: Orca は状態を記録しない。orca terminal read --screen --json の
  result.terminal.tail（行の配列）と result.terminal.source（"screen"）を使う。
  入力待ちの画面で確認できた表示は、末尾の空でない 3 行が
  「"› Ask Codex to do anything"（入力欄のプレースホルダ全文）」「モデルと作業ディレクトリの行」
  「"for shortcuts" を含むヒント行」の並びであること。この並びだけを idle とする。
- Codex の処理中の画面: 未確認（送信が禁止のため、処理中の画面を観察できなかった）。
  推測で判定パターンを作らないので、Codex の working は返さない。
  限界: idle の判定は末尾 3 行しか見ない。処理中の Codex が入力欄を下部に残したまま末尾 3 行が
  入力待ちと同じ並びに見える場合、idle と誤判定する可能性を排除できていない（処理中の画面を
  観察できていないため）。したがって Codex の idle は「入力待ちに見える」ことを示すもので、
  処理中でないことの保証ではない。実機で処理中の画面を観察できたら判定を追加すること。
- 画面の表示の解釈は版に依存する。判別できない入力は必ず unknown にする。

リポジトリに紐づかない worktree の識別: repo / repoId が空、projectId 項目が空、
workspaceKind が "git" 以外、または path が一時ディレクトリ配下（実機で、一時ディレクトリの
worktree が repoId を持ったまま現れることを確認した）のいずれか。
候補から落とすのは resolve の担当で、この adapter は識別の手段（is_unlinked）だけを提供する。
"""

import json
import os
import shlex
import subprocess

from ..output import CrosstalkError
from .base import (
    RECEIPT_NOT_OBSERVED,
    SEND_FAILED_REASON,
    STATE_IDLE,
    STATE_UNKNOWN,
    STATE_WORKING,
    Candidate,
    ChannelAdapter,
    SendResult,
    redact_text,
)

COMMAND_TIMEOUT_SECONDS = 10

# orca terminal send --wait-submit の観測の秒数と、コマンド自体の上限（観測より長くする）
WAIT_SUBMIT_SECONDS = 10
SEND_TIMEOUT_SECONDS = 30

# 受領ありを示す段階の名前
TURN_STARTED = "turn_started"
SEND_SOURCE = "orca terminal send 結果の段階"

BRANCH_PREFIX = "refs/heads/"

# 回答の先頭に付ける印（%s は依頼 ID）。
REPLY_PREFIX = "[crosstalk 回答 ID: %s] <回答>"

# 一時ディレクトリとみなす path の接頭辞（macOS は /tmp と /var/folders が /private 配下へ解決される）
TEMP_DIR_PREFIXES = (
    "/tmp/",
    "/private/tmp/",
    "/var/tmp/",
    "/private/var/tmp/",
    "/var/folders/",
    "/private/var/folders/",
)

AVAILABLE_ENV = "ORCA_TERMINAL_HANDLE"


def own_terminal_handle(env=None):
    """自分の端末のハンドル（環境変数 ORCA_TERMINAL_HANDLE）。無ければ空文字。"""
    env = os.environ if env is None else env
    return env.get(AVAILABLE_ENV, "")


def _load_envelope(text, label):
    """{"ok": true, "result": {...}} のエンベロープを外して result を返す。"""
    try:
        data = json.loads(text)
    except (ValueError, TypeError) as e:
        raise CrosstalkError("%s の出力が JSON ではない: %s" % (label, e))
    if not isinstance(data, dict):
        raise CrosstalkError("%s の出力がオブジェクトではない" % label)
    if data.get("ok") is not True:
        raise CrosstalkError(
            "%s がエラーを返した" % label,
            detail=json.dumps(data.get("error"), ensure_ascii=False)[:300],
        )
    result = data.get("result")
    if not isinstance(result, dict):
        raise CrosstalkError("%s の出力に result が無い" % label)
    return result


def _require_str(item, field, label, index, allow_empty=False):
    value = item.get(field)
    if not isinstance(value, str) or (not value and not allow_empty):
        raise CrosstalkError(
            "%s の項目に必須の文字列 %s が無い" % (label, field), index=index
        )
    return value


def _items(result, key, label):
    items = result.get(key)
    if not isinstance(items, list):
        raise CrosstalkError("%s の出力に %s の配列が無い" % (label, key))
    if result.get("truncated") is True:
        raise CrosstalkError("%s の出力が途中で切れている（truncated）" % label)
    return items


def _is_temp_path(path):
    return path.startswith(TEMP_DIR_PREFIXES)


def _worktree_unlinked(row):
    """worktree の行が、リポジトリに紐づかないものか。"""
    if not row["repo"] or not row["repoId"]:
        return True
    if "projectId" in row and not row["projectId"]:
        return True
    if row["workspaceKind"] != "git":
        return True
    return _is_temp_path(row["path"])


def parse_worktrees(text):
    """orca worktree ps --json の出力を、worktreeId をキーにした辞書にする。"""
    label = "orca worktree ps"
    rows = {}
    for index, item in enumerate(
        _items(_load_envelope(text, label), "worktrees", label)
    ):
        if not isinstance(item, dict):
            raise CrosstalkError("%s の項目がオブジェクトではない" % label, index=index)
        row = {
            "worktreeId": _require_str(item, "worktreeId", label, index),
            "repo": _require_str(item, "repo", label, index, allow_empty=True),
            "repoId": _require_str(item, "repoId", label, index, allow_empty=True),
            "path": _require_str(item, "path", label, index),
            "branch": _require_str(item, "branch", label, index, allow_empty=True),
            "workspaceKind": _require_str(item, "workspaceKind", label, index),
        }
        if "projectId" in item:
            row["projectId"] = item["projectId"]
        agents = item.get("agents")
        if not isinstance(agents, list):
            raise CrosstalkError("%s の項目に agents の配列が無い" % label, index=index)
        row["agents"] = {}
        row["agent_states"] = {}
        for agent in agents:
            if not isinstance(agent, dict):
                raise CrosstalkError(
                    "%s の agents の項目がオブジェクトではない" % label, index=index
                )
            pane_key = _require_str(agent, "paneKey", label, index)
            row["agents"][pane_key] = _require_str(agent, "agentType", label, index)
            # state は受信側の状態の判定にだけ使う。無い・文字列でないときは None（判定は unknown）
            state = agent.get("state")
            row["agent_states"][pane_key] = state if isinstance(state, str) else None
        if row["worktreeId"] in rows:
            raise CrosstalkError("%s に worktreeId の重複がある" % label, index=index)
        rows[row["worktreeId"]] = row
    return rows


def parse_terminals(text):
    """orca terminal list --json の出力から、エージェントの居る端末の行のリストを返す。"""
    label = "orca terminal list"
    terminals = []
    for index, item in enumerate(
        _items(_load_envelope(text, label), "terminals", label)
    ):
        if not isinstance(item, dict):
            raise CrosstalkError("%s の項目がオブジェクトではない" % label, index=index)
        handle = _require_str(item, "handle", label, index)
        identity = item.get("agentIdentity")
        if identity is None:
            continue  # エージェントの居ない端末は宛先の候補ではない
        if not isinstance(identity, str) or not identity:
            raise CrosstalkError(
                "%s の agentIdentity が文字列ではない" % label, index=index
            )
        terminals.append(
            {
                "handle": handle,
                "worktreeId": _require_str(item, "worktreeId", label, index),
                "paneKey": _require_str(item, "tabId", label, index)
                + ":"
                + _require_str(item, "leafId", label, index),
                "agentIdentity": identity,
            }
        )
    return terminals


def build_candidates(worktrees_text, terminals_text):
    """二つの出力を突き合わせる。(Candidate のリスト, target をキーにした識別情報) を返す。

    識別情報は {"unlinked": bool, "pane_key": str, "recorded_state": str | None}。
    candidates の state は確定させない（STATE_UNKNOWN）。状態は receiver_state が判定する。
    """
    worktrees = parse_worktrees(worktrees_text)
    candidates = []
    details = {}
    for terminal in parse_terminals(terminals_text):
        row = worktrees.get(terminal["worktreeId"])
        if row is None:
            raise CrosstalkError(
                "端末の worktreeId に対応する worktree が無い",
                target=terminal["handle"],
            )
        agent_type = row["agents"].get(terminal["paneKey"])
        if agent_type is not None and agent_type != terminal["agentIdentity"]:
            raise CrosstalkError(
                "worktree の agentType と端末の agentIdentity が一致しない",
                target=terminal["handle"],
            )
        branch = row["branch"]
        if branch.startswith(BRANCH_PREFIX):
            branch = branch[len(BRANCH_PREFIX) :]
        candidates.append(
            Candidate(
                channel="orca",
                target=terminal["handle"],
                repo=row["repo"],
                worktree=row["path"],
                branch=branch,
                agent_kind=terminal["agentIdentity"],
                state=STATE_UNKNOWN,
            )
        )
        details[terminal["handle"]] = {
            "unlinked": _worktree_unlinked(row),
            "pane_key": terminal["paneKey"],
            "recorded_state": row["agent_states"].get(terminal["paneKey"]),
        }
    return candidates, details


def parse_status(text):
    """orca status --json の出力が、実行基盤に到達できると返しているか。"""
    runtime = _load_envelope(text, "orca status").get("runtime")
    if not isinstance(runtime, dict) or not isinstance(runtime.get("reachable"), bool):
        raise CrosstalkError("orca status の出力に runtime.reachable が無い")
    return runtime["reachable"]


# worktree ps の agents[].state と状態の対応。ここに無い値は推測せず unknown にする。
RECORDED_STATE_TO_STATE = {
    "done": STATE_IDLE,
    "working": STATE_WORKING,
}

# Codex の入力待ちの画面で確認できた表示（モジュール docstring を参照）
CODEX_PROMPT_PREFIX = "\u203a "  # "› "
CODEX_PROMPT_PLACEHOLDER = "Ask Codex to do anything"
CODEX_SHORTCUTS_HINT = "for shortcuts"
CODEX_TAIL_LINE_COUNT = 3

AGENT_CLAUDE = "claude"
AGENT_CODEX = "codex"


def _evidence(source, observed):
    return {"source": source, "observed": observed}


def judge_claude_state(recorded_state):
    """worktree ps の記録（agents[].state。記録が無ければ None）から (state, 根拠) を返す。"""
    source = "orca worktree ps agents[].state"
    if recorded_state is None:
        return STATE_UNKNOWN, _evidence(
            source, "対応する記録が無い、または state が文字列でない"
        )
    state = RECORDED_STATE_TO_STATE.get(recorded_state)
    if state is None:
        return STATE_UNKNOWN, _evidence(source, "未確認の値: %s" % recorded_state[:40])
    return state, _evidence(source, recorded_state)


def judge_codex_screen(text):
    """orca terminal read --screen --json の出力から (state, 根拠) を返す。

    画面から読み取れたのは入力待ちの並びだけである。それに当たらない画面（入力途中・
    未知の表示・空）は unknown にする。ただし末尾 3 行が入力待ちと同じ並びに見える画面は、
    処理中でも idle になり得る（処理中の画面は未観察。モジュールの説明の限界を参照）。
    形が期待と異なる出力も unknown とし、error にはしない
    （画面の解釈は版に依存し、判別できないことは通常の結果として扱うため）。
    """
    source = "orca terminal read --screen"
    try:
        data = json.loads(text)
        terminal = data["result"]["terminal"]
        tail = terminal["tail"]
        screen_source = terminal.get("source")
    except (ValueError, TypeError, KeyError):
        return STATE_UNKNOWN, _evidence(source, "出力の形が期待と異なる")
    if data.get("ok") is not True or not isinstance(tail, list):
        return STATE_UNKNOWN, _evidence(source, "出力の形が期待と異なる")
    if screen_source != "screen":
        return STATE_UNKNOWN, _evidence(
            source, "画面として読めていない（source: %s）" % str(screen_source)[:40]
        )
    lines = [line.strip() for line in tail if isinstance(line, str) and line.strip()]
    last = lines[-CODEX_TAIL_LINE_COUNT:]
    if len(last) < CODEX_TAIL_LINE_COUNT:
        return STATE_UNKNOWN, _evidence(source, "末尾に判定できる行が足りない")
    prompt, _footer, hint = last
    # 入力途中の文がプレースホルダと同じ語で始まっていても idle と誤判定しないよう、全文一致で判定する
    placeholder_prompt = prompt == CODEX_PROMPT_PREFIX + CODEX_PROMPT_PLACEHOLDER
    if placeholder_prompt and CODEX_SHORTCUTS_HINT in hint:
        return STATE_IDLE, _evidence(
            source, "末尾が空の入力欄（プロンプト）とショートカットのヒント行"
        )
    return STATE_UNKNOWN, _evidence(
        source, "入力待ちの並びに当たらない（処理中の表示は未確認）"
    )


def _run(args, label):
    try:
        proc = subprocess.run(
            ["orca"] + args,
            capture_output=True,
            text=True,
            timeout=COMMAND_TIMEOUT_SECONDS,
        )
    except FileNotFoundError:
        raise CrosstalkError("orca の実行ファイルが見つからない")
    except subprocess.TimeoutExpired:
        raise CrosstalkError("%s がタイムアウトした" % label)
    if proc.returncode != 0:
        # 失敗の説明が標準出力と標準エラーのどちらに出るかは未確認のため、両方を残す
        detail = (proc.stdout.strip() + " " + proc.stderr.strip()).strip()[:300]
        raise CrosstalkError(
            "%s が失敗した" % label, exit_code=proc.returncode, detail=detail
        )
    return proc.stdout


def parse_send_response(text):
    """orca terminal send --enter --wait-submit --json の標準出力（終了コード 0 のとき）から、受領の判定を返す。

    実機（Orca 1.4.221）で確認した応答の形:
      {"ok": true, "result": {"send": {"accepted": true, "prompt": {"stages": ["input_accepted", "turn_started"], ...}}, ...}}
    result.send.accepted が true で、result.send.prompt.stages（文字列の配列）に turn_started があるときだけ
    受領ありとする（受信側がターンを開始したことを観測できた）。stages が input_accepted だけのとき
    （--wait-submit の時間内にターンの開始を観測できなかった）、形が違う・JSON でない・ok が true でない
    出力は、受領を確認できなかったものとして扱う（再送しない安全側。error にはしない）。
    """
    not_observed = SendResult(False, SEND_SOURCE, RECEIPT_NOT_OBSERVED)
    try:
        data = json.loads(text)
    except (ValueError, TypeError):
        return not_observed
    if not isinstance(data, dict) or data.get("ok") is not True:
        return not_observed
    result = data.get("result")
    send = result.get("send") if isinstance(result, dict) else None
    prompt = send.get("prompt") if isinstance(send, dict) else None
    stages = prompt.get("stages") if isinstance(prompt, dict) else None
    if (
        isinstance(send, dict)
        and send.get("accepted") is True
        and isinstance(stages, list)
        and TURN_STARTED in stages
    ):
        return SendResult(True, SEND_SOURCE, TURN_STARTED)
    return not_observed


class OrcaAdapter(ChannelAdapter):
    channel = "orca"

    def __init__(self):
        self._details = {}

    def send(self, target, text):
        """orca terminal send を 1 回だけ実行する。失敗しても再試行しない。"""
        args = [
            "orca",
            "terminal",
            "send",
            "--terminal",
            target,
            "--text",
            text,
            "--enter",
            "--wait-submit",
            str(WAIT_SUBMIT_SECONDS),
            "--json",
        ]
        try:
            proc = subprocess.run(
                args,
                capture_output=True,
                text=True,
                timeout=SEND_TIMEOUT_SECONDS,
            )
        except FileNotFoundError:
            raise CrosstalkError(
                SEND_FAILED_REASON, detail="orca の実行ファイルが見つからない"
            )
        except subprocess.TimeoutExpired:
            raise CrosstalkError(
                SEND_FAILED_REASON, detail="orca terminal send がタイムアウトした"
            )
        if proc.returncode != 0:
            detail = (proc.stdout.strip() + " " + proc.stderr.strip()).strip()
            raise CrosstalkError(
                SEND_FAILED_REASON,
                exit_code=proc.returncode,
                detail=redact_text(detail, text)[:300],
            )
        return parse_send_response(proc.stdout)

    def available(self):
        if not own_terminal_handle():
            return False
        try:
            return parse_status(_run(["status", "--json"], "orca status"))
        except CrosstalkError:
            return False

    def candidates(self):
        worktrees_text = _run(["worktree", "ps", "--json"], "orca worktree ps")
        terminals_text = _run(["terminal", "list", "--json"], "orca terminal list")
        candidates, self._details = build_candidates(worktrees_text, terminals_text)
        return candidates

    def receiver_state(self, target):
        """target の受信側の状態（STATES のいずれか）。根拠は receiver_state_with_evidence。"""
        return self.receiver_state_with_evidence(target)[0]

    def receiver_state_with_evidence(self, target):
        """(状態, 根拠) を返す。根拠は {"source": 見た記録・画面, "observed": 判定に使った特徴}。

        種別は候補の agent_kind で決める。target が候補に無ければ CrosstalkError。
        claude / codex 以外の種別は判定の方法が無いので unknown。
        """
        candidates = self.candidates()
        candidate = next((c for c in candidates if c.target == target), None)
        if candidate is None:
            raise CrosstalkError("orca に指定の端末が無い", target=target)
        if candidate.agent_kind == AGENT_CLAUDE:
            return judge_claude_state(self._details[target]["recorded_state"])
        if candidate.agent_kind == AGENT_CODEX:
            text = _run(
                ["terminal", "read", "--terminal", target, "--screen", "--json"],
                "orca terminal read",
            )
            return judge_codex_screen(text)
        return STATE_UNKNOWN, _evidence(
            "agent_kind", "判定の方法が無い種別: %s" % candidate.agent_kind[:40]
        )

    def own_terminal_handle(self):
        return own_terminal_handle()

    def receipt_recheck_guide(self):
        """Orca の --retry-request による受領の再確認の案内。

        --retry-request の ID は、返信コマンドの警告が報告する通信層の ID で、crosstalk の依頼 ID とは
        別物である（送信内容と端末のプロセスに紐づくため、回答の文面を 1 文字でも変えると使えない）。
        """
        return (
            "受領の再確認が必要なときだけ、警告に表示された --retry-request の ID"
            "（crosstalk の依頼 ID とは別物）を付けて、回答の文面を 1 文字も変えずに同じコマンドを再実行してください。"
            "この再実行は受領の再確認であって、回答の再送ではありません。"
        )

    def reply_command(self, request_id):
        """受信側が回答を送り返すコマンド。送信側の端末は ORCA_TERMINAL_HANDLE から取る。"""
        handle = own_terminal_handle()
        if not handle:
            raise CrosstalkError(
                "返信先を書けない: 環境変数 ORCA_TERMINAL_HANDLE が無い（Orca の端末で実行する）"
            )
        return 'orca terminal send --terminal %s --text "%s" --enter' % (
            shlex.quote(handle),
            REPLY_PREFIX % request_id,
        )

    def is_self(self, candidate):
        """candidate が自分の端末か。ORCA_TERMINAL_HANDLE が無いときは常に False。"""
        own = own_terminal_handle()
        return bool(own) and candidate.target == own

    def is_unlinked(self, candidate):
        """candidate の worktree がリポジトリに紐づかないものか。直近の candidates() の結果に基づく。"""
        detail = self._details.get(candidate.target)
        if detail is None:
            raise CrosstalkError(
                "candidates() の結果に無い候補", target=candidate.target
            )
        return detail["unlinked"]

    def pane_key(self, candidate):
        """candidate の端末の paneKey（worktree ps の agents[].paneKey と突き合わせる値）。"""
        detail = self._details.get(candidate.target)
        if detail is None:
            raise CrosstalkError(
                "candidates() の結果に無い候補", target=candidate.target
            )
        return detail["pane_key"]
