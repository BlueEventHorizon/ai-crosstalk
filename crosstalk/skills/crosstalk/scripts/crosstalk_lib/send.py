"""send サブコマンド。承認された本文を、宛先を再確認したうえで 1 回だけ送る。

送信は他のセッションへ入力を注入する、取り消せない操作である。そのため次を守る。
- 本文は加工しない。承認された文字列と送る文字列を同一にするため、改行・制御文字を含む本文は
  送らずに拒否する（compose が 1 行にして制御文字を除いているので、承認された本文は 1 行のはず）
- 送る直前に、宛先が存在し、種別が期待と一致することを再確認する。一致しなければ送らない
- 送信は 1 回だけ。失敗しても、受領を確認できなくても、再送・再試行しない
"""

import sys

from .adapters import get_adapter
from .output import CrosstalkError
from .textcheck import has_control_chars

CHANNELS = ("herdr", "orca")
NOT_RESENT_NOTE = (
    "受領を確認できなかった。再送しない（届いているかは、受信側の状態と回答で確かめる）"
)


def verify_destination(adapter, target, agent_kind):
    """送る直前の宛先の再確認。宛先が存在し、種別が agent_kind と一致する候補を返す。

    送信コマンドは呼ばない。存在しない・種別が違うときは CrosstalkError。
    """
    for candidate in adapter.candidates():
        if candidate.target == target:
            if candidate.agent_kind != agent_kind:
                raise CrosstalkError(
                    "宛先の種別が期待と一致しない。送らない",
                    target=target,
                    expected_agent_kind=agent_kind,
                    actual_agent_kind=candidate.agent_kind,
                )
            return candidate
    raise CrosstalkError("宛先が存在しない。送らない", target=target)


def check_body(body):
    """本文の検査（送る前）。送れない本文なら CrosstalkError。本文は加工しない。"""
    if not body.strip():
        raise CrosstalkError("本文が空（標準入力から本文を渡す）")
    if has_control_chars(body):
        raise CrosstalkError(
            "本文に改行・制御文字が含まれている。送らない"
            "（承認された 1 行の本文を、加工せずそのまま標準入力へ渡す。入力の終端の改行は無視する）"
        )
    if body.startswith("-"):
        # 送信コマンドが本文をオプションとして解釈しないようにする
        raise CrosstalkError(
            "本文が - で始まっている。送らない（compose が作った本文を渡す）"
        )


def run(args):
    channel = args.channel
    if channel is None or channel not in CHANNELS:
        raise CrosstalkError(
            "send は herdr / orca 専用（--channel に herdr か orca を指定する）"
        )
    if not args.target:
        raise CrosstalkError("--target が必要")
    if not args.agent_kind:
        raise CrosstalkError(
            "--agent-kind が必要（宛先の種別の期待値。claude / codex など）"
        )

    # 標準入力の終端の改行（heredoc や echo が付ける）だけを落とす。compose も本文の末尾の改行を
    # 落として text を作るので、承認された text と同じ文字列になる。本文の途中の改行は拒否する。
    body = sys.stdin.read().rstrip("\r\n")
    check_body(body)

    adapter = get_adapter(channel)
    candidate = verify_destination(adapter, args.target, args.agent_kind)
    result = adapter.send(args.target, body)

    data = {
        "channel": channel,
        "target": candidate.target,
        "agent_kind": candidate.agent_kind,
    }
    if args.request_id:
        data["request_id"] = args.request_id
    data["receipt"] = result.to_dict()
    if not result.confirmed:
        data["note"] = NOT_RESENT_NOTE
    return data
