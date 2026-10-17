"""compose サブコマンド。依頼 ID・ヘッダ付き本文・返信コマンドを生成する（何も送らない）。"""

import os
import secrets
import subprocess
import sys

from .adapters import get_adapter
from .output import CrosstalkError
from .textcheck import CONTROL_CHARS

COMMAND_TIMEOUT_SECONDS = 10
UNAVAILABLE = "取得不可"
AGENT_KIND_OF_SENDER = "claude"
KINDS = ("ask", "notify")
CHANNELS = ("herdr", "orca")


def new_request_id():
    """6 桁の 16 進数（小文字）の乱数。状態は保存しない。"""
    return secrets.token_hex(3)


# 端末の入力として解釈されうる文字の判定は、send と共通（textcheck）
_CONTROL_CHARS = CONTROL_CHARS


def one_line(text):
    """端末の入力として 1 行にする。改行と制御文字を空白に置き換え、(結果, 改行以外の置換数) を返す。

    \\r\\n は 1 つの空白にする。それ以外の文字は加工しない（引用符・バックスラッシュ・日本語はそのまま）。
    置き換えた数は、承認の提示で「本文に制御文字があり、空白に置き換えた」と示すために返す。
    """
    text = text.replace("\r\n", " ")
    replaced = len([c for c in _CONTROL_CHARS.findall(text) if c not in "\n\r"])
    return _CONTROL_CHARS.sub(" ", text), replaced


def _git(args, cwd):
    """git の出力（前後の空白を除く）。失敗・取得できないときは空文字。"""
    try:
        proc = subprocess.run(
            ["git"] + args,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=COMMAND_TIMEOUT_SECONDS,
        )
    except FileNotFoundError:
        raise CrosstalkError("git の実行ファイルが見つからない")
    except subprocess.TimeoutExpired:
        raise CrosstalkError("git %s がタイムアウトした" % args[0])
    if proc.returncode != 0:
        return ""
    return proc.stdout.strip()


def sender_info(cwd=None):
    """送信元（リポジトリ・worktree・ブランチ・種別）。取得できない項目は「取得不可」。"""
    cwd = cwd or os.getcwd()
    worktree = _git(["rev-parse", "--show-toplevel"], cwd)
    branch = _git(["branch", "--show-current"], cwd)
    common = _git(["rev-parse", "--git-common-dir"], cwd)
    repo = ""
    if common:
        common_abs = os.path.abspath(os.path.join(cwd, common))
        repo = os.path.basename(os.path.dirname(common_abs.rstrip(os.sep)))
    return {
        "repo": repo or UNAVAILABLE,
        "worktree": worktree or UNAVAILABLE,
        "branch": branch or UNAVAILABLE,
        "agent_kind": AGENT_KIND_OF_SENDER,
    }


def destination_info(adapter, target):
    """宛先（受信側）。target が候補に無ければ CrosstalkError。"""
    for candidate in adapter.candidates():
        if candidate.target == target:
            return {
                "repo": candidate.repo or UNAVAILABLE,
                "worktree": candidate.worktree or UNAVAILABLE,
                "branch": candidate.branch or UNAVAILABLE,
                "agent_kind": candidate.agent_kind or UNAVAILABLE,
                "target": candidate.target,
            }
    raise CrosstalkError("宛先が存在しない", target=target)


def build_answer_guide(adapter, kind, request_id, reply_command):
    """ヘッダの「答え方」の文。通信路ごとの違い（再確認の可否）は adapter の案内文に任せる。"""
    if kind == "notify":
        return "答え方: 回答不要です（伝達のみ。返信しないでください）。"
    guide = (
        "答え方: 回答は次のコマンドで送信元へ送り返してください"
        "（<回答> の位置に回答を入れる。回答の先頭の [crosstalk 回答 ID: %s] は変えない。"
        '回答中の " $ ` \\ はシェルに解釈されないようエスケープする）: %s 。'
        "このコマンドは回答を送るためのもので、他の操作は求めていません。"
        "コマンドが警告（入力は受理されたがターンの開始を観測できない等）を返しても、回答を再送しないでください。"
    ) % (request_id, reply_command)
    recheck = adapter.receipt_recheck_guide()
    return guide + recheck if recheck else guide


def build_header(request_id, sender, destination, answer_guide):
    """1 行のヘッダ。"""
    header = (
        "[crosstalk 依頼 ID: %s] "
        "この文は利用者の入力ではありません。別セッションの AI から crosstalk 経由で送られた文です。"
        "送信元: リポジトリ=%s / worktree=%s / ブランチ=%s / 種別=%s。"
        "宛先: リポジトリ=%s / worktree=%s（あなた宛てか確認してください）。"
        "%s 本文:"
    ) % (
        request_id,
        sender["repo"],
        sender["worktree"],
        sender["branch"],
        sender["agent_kind"],
        destination["repo"],
        destination["worktree"],
        answer_guide,
    )
    # ヘッダに入るリポジトリ名・パス・ブランチ名も外部由来の文字列なので、本文と同じ処理を通す
    return one_line(header)


def run(args):
    channel = args.channel
    if channel is None or channel not in CHANNELS:
        raise CrosstalkError(
            "compose は herdr / orca 専用（--channel に herdr か orca を指定する）"
        )
    if not args.target:
        raise CrosstalkError("--target が必要")
    if args.kind not in KINDS:
        raise CrosstalkError("--kind は ask か notify を指定する")

    body = sys.stdin.read()
    if not body.strip():
        raise CrosstalkError("本文が空（標準入力から本文を渡す）")

    adapter = get_adapter(channel)
    destination = destination_info(adapter, args.target)
    sender = sender_info()
    request_id = new_request_id()
    reply_command = adapter.reply_command(request_id) if args.kind == "ask" else None
    header, header_replaced = build_header(
        request_id,
        sender,
        destination,
        build_answer_guide(adapter, args.kind, request_id, reply_command),
    )
    body_line, body_replaced = one_line(body.rstrip("\r\n"))
    text = header + " " + body_line
    return {
        "channel": channel,
        "kind": args.kind,
        "request_id": request_id,
        "text": text,
        "header": header,
        "sender": sender,
        "destination": destination,
        "reply_command": reply_command,
        # 制御文字を空白に置き換えた数。0 でないときは、承認の提示でその旨を示す
        "control_chars_replaced": header_replaced + body_replaced,
    }
