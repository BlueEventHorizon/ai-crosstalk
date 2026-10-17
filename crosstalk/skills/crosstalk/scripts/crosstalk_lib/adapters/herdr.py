"""herdr の adapter。herdr agent list の出力を候補と状態に正規化する。"""

import json
import os
import shlex
import subprocess

from ..output import CrosstalkError
from .base import (
    RECEIPT_NOT_OBSERVED,
    SEND_FAILED_REASON,
    STATE_BLOCKED,
    STATE_IDLE,
    STATE_WORKING,
    Candidate,
    ChannelAdapter,
    SendResult,
    redact_text,
)

COMMAND_TIMEOUT_SECONDS = 10

# herdr agent prompt の実行の上限（秒）。--wait を付けないため、通常は直ちに返る。
SEND_TIMEOUT_SECONDS = 30

# 受領ありを示す応答の種別（result.type）
PROMPTED_TYPE = "agent_prompted"
PROMPT_SOURCE = "herdr agent prompt result.type"

# 回答の先頭に付ける印（%s は依頼 ID）。
REPLY_PREFIX = "[crosstalk 回答 ID: %s] <回答>"

# agent_status と状態の対応。ここに無い値は推測せず error にする。
STATUS_TO_STATE = {
    "idle": STATE_IDLE,
    "done": STATE_IDLE,
    "working": STATE_WORKING,
    "blocked": STATE_BLOCKED,
}

REQUIRED_FIELDS = ("agent", "agent_status", "cwd", "pane_id")

# herdr の管理下であることを示す環境変数（値が "1"）
AVAILABLE_ENV = "HERDR_ENV"
AVAILABLE_ENV_VALUE = "1"


def own_pane_id(env=None):
    """自分の pane の ID（環境変数 HERDR_PANE_ID）。無ければ空文字。"""
    env = os.environ if env is None else env
    return env.get("HERDR_PANE_ID", "")


def parse_agent_list(text):
    """herdr agent list の出力（JSON 文字列）を Candidate のリストにする。"""
    return [candidate for candidate, _status in _parse_agents(text)]


def _parse_agents(text):
    """(Candidate, 生の agent_status) のリストにする。生の値は、状態の根拠に使う。"""
    try:
        data = json.loads(text)
    except (ValueError, TypeError) as e:
        raise CrosstalkError("herdr agent list の出力が JSON ではない: %s" % e)

    agents = _extract_agents(data)
    candidates = []
    for index, agent in enumerate(agents):
        if not isinstance(agent, dict):
            raise CrosstalkError(
                "herdr agent list の項目がオブジェクトではない", index=index
            )
        for field in REQUIRED_FIELDS:
            value = agent.get(field)
            if not isinstance(value, str) or not value:
                raise CrosstalkError(
                    "herdr agent list の項目に必須の文字列 %s が無い" % field,
                    index=index,
                )
        status = agent["agent_status"]
        if status not in STATUS_TO_STATE:
            raise CrosstalkError("未知の agent_status: %s" % status, index=index)
        candidates.append(
            (
                Candidate(
                    channel="herdr",
                    target=agent["pane_id"],
                    repo="",
                    worktree=agent["cwd"],
                    branch="",
                    agent_kind=agent["agent"],
                    state=STATUS_TO_STATE[status],
                ),
                status,
            )
        )
    return candidates


def _extract_agents(data):
    """エンベロープを外して agent の配列を取り出す。形が合わなければ error。

    実機（herdr 0.9.3）で確認した形は {"id": ..., "result": {"agents": [...], "type": "agent_list"}}
    の 1 通りで、これ以外は受理しない。失敗時は終了コード 1 で、標準エラーに
    {"id": ..., "error": {"code": ..., "message": ...}} が出る（標準出力は空）。
    各 agent の項目のうち、必須として使うのは agent / agent_status / cwd / pane_id。
    agent_session は項目ごと無い agent がある（任意）。
    """
    if not isinstance(data, dict):
        raise CrosstalkError("herdr agent list の出力がオブジェクトではない")
    if data.get("error"):
        raise CrosstalkError(
            "herdr がエラーを返した: %s" % json.dumps(data["error"], ensure_ascii=False)
        )
    result = data.get("result")
    agents = result.get("agents") if isinstance(result, dict) else None
    if not isinstance(agents, list):
        raise CrosstalkError("herdr agent list の出力に agent の配列が無い")
    return agents


def parse_prompt_response(text):
    """herdr agent prompt の標準出力（終了コード 0 のとき）から、受領の判定を返す。

    実機（herdr 0.9.3）で確認した応答の形は
    {"id": "cli:agent:prompt", "result": {"agent": {...}, "type": "agent_prompted"}}。
    result.type が agent_prompted のときだけ受領ありとする。それ以外（JSON でない・形が違う・
    別の type）は、受領を確認できなかったものとして扱う（再送しない安全側。error にはしない）。
    """
    try:
        data = json.loads(text)
    except (ValueError, TypeError):
        return SendResult(False, PROMPT_SOURCE, RECEIPT_NOT_OBSERVED)
    result = data.get("result") if isinstance(data, dict) else None
    observed = result.get("type") if isinstance(result, dict) else None
    if observed == PROMPTED_TYPE:
        return SendResult(True, PROMPT_SOURCE, PROMPTED_TYPE)
    return SendResult(False, PROMPT_SOURCE, RECEIPT_NOT_OBSERVED)


class HerdrAdapter(ChannelAdapter):
    channel = "herdr"

    def send(self, target, text):
        """herdr agent prompt <pane> <本文> を 1 回だけ実行する。--wait は付けない。再試行しない。"""
        try:
            proc = subprocess.run(
                ["herdr", "agent", "prompt", target, text],
                capture_output=True,
                text=True,
                timeout=SEND_TIMEOUT_SECONDS,
            )
        except FileNotFoundError:
            raise CrosstalkError(
                SEND_FAILED_REASON, detail="herdr の実行ファイルが見つからない"
            )
        except subprocess.TimeoutExpired:
            raise CrosstalkError(
                SEND_FAILED_REASON, detail="herdr agent prompt がタイムアウトした"
            )
        if proc.returncode != 0:
            detail = (proc.stdout.strip() + " " + proc.stderr.strip()).strip()
            raise CrosstalkError(
                SEND_FAILED_REASON,
                exit_code=proc.returncode,
                detail=redact_text(detail, text)[:300],
            )
        return parse_prompt_response(proc.stdout)

    def _run_list(self):
        try:
            proc = subprocess.run(
                ["herdr", "agent", "list"],
                capture_output=True,
                text=True,
                timeout=COMMAND_TIMEOUT_SECONDS,
            )
        except FileNotFoundError:
            raise CrosstalkError("herdr の実行ファイルが見つからない")
        except subprocess.TimeoutExpired:
            raise CrosstalkError("herdr agent list がタイムアウトした")
        if proc.returncode != 0:
            # 失敗の説明が標準出力と標準エラーのどちらに出るかは未確認のため、両方を残す
            detail = (proc.stdout.strip() + " " + proc.stderr.strip()).strip()[:300]
            raise CrosstalkError(
                "herdr agent list が失敗した", exit_code=proc.returncode, detail=detail
            )
        return proc.stdout

    def available(self):
        """herdr の管理下で、herdr に接続できるか。

        判定は環境変数と herdr agent list の成否だけで行う。出力の中身（agent_status の未知の値など）
        の解釈は候補の取得（candidates）の責務で、ここでは使わない。中身の不備を理由に herdr を
        「使えない」と判定すると、herdr が動いているのに別の通信路へ落ちてしまう。
        """
        if os.environ.get(AVAILABLE_ENV) != AVAILABLE_ENV_VALUE:
            return False
        try:
            self._run_list()
        except CrosstalkError:
            return False
        return True

    def candidates(self):
        return parse_agent_list(self._run_list())

    def receiver_state(self, target):
        return self.receiver_state_with_evidence(target)[0]

    def receiver_state_with_evidence(self, target):
        """(状態, 根拠) を返す。根拠の observed は herdr が返した agent_status の値。"""
        for candidate, status in _parse_agents(self._run_list()):
            if candidate.target == target:
                return candidate.state, {
                    "source": "herdr agent list agent_status",
                    "observed": status,
                }
        raise CrosstalkError("herdr に指定の pane が無い", target=target)

    def own_pane_id(self):
        return own_pane_id()

    def reply_command(self, request_id):
        """受信側が回答を送り返すコマンド。送信側の pane は HERDR_PANE_ID から取る。"""
        pane = own_pane_id()
        if not pane:
            raise CrosstalkError(
                "返信先を書けない: 環境変数 HERDR_PANE_ID が無い（herdr の管理下で実行する）"
            )
        return 'herdr agent prompt %s "%s"' % (
            shlex.quote(pane),
            REPLY_PREFIX % request_id,
        )

    def is_self(self, candidate):
        """candidate が自分の pane か。HERDR_PANE_ID が無いときは常に False。"""
        own = own_pane_id()
        return bool(own) and candidate.target == own

    def is_unlinked(self, candidate):
        """candidate の作業ディレクトリが git の作業ツリーでないか。

        herdr はリポジトリとの紐づけ情報を返さないため、作業ディレクトリで
        git rev-parse --is-inside-work-tree が成功して true を返すものだけを紐づくとする。
        失敗する・存在しない・出力が true でないものは紐づかない。一時ディレクトリかどうかは見ない。
        git が無い・タイムアウトしたときは推測せず CrosstalkError。
        """
        try:
            proc = subprocess.run(
                ["git", "-C", candidate.worktree, "rev-parse", "--is-inside-work-tree"],
                capture_output=True,
                text=True,
                timeout=COMMAND_TIMEOUT_SECONDS,
            )
        except FileNotFoundError:
            raise CrosstalkError("git の実行ファイルが見つからない")
        except subprocess.TimeoutExpired:
            raise CrosstalkError(
                "git rev-parse がタイムアウトした", target=candidate.target
            )
        return not (proc.returncode == 0 and proc.stdout.strip() == "true")
