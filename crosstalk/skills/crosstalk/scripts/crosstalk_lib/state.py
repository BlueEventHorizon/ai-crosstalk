"""state サブコマンド。宛先の受信側が今どういう状態かを、通信路の adapter に問い合わせて返す。

通信路ごとの判定は adapter が持つ。ここでは分岐せず、adapter の返した状態と根拠をそのまま出す。
宛先が存在しない・外部 CLI の出力が期待と異なるときは、adapter が出す CrosstalkError を
そのまま error として返す（推測で idle 等を返さない）。
"""

from .adapters import get_adapter
from .output import CrosstalkError


def run(args):
    channel = getattr(args, "channel", None)
    target = getattr(args, "target", None)
    if not channel:
        raise CrosstalkError(
            "--channel が指定されていない（herdr / orca のどちらかを指定する）"
        )
    if not target:
        raise CrosstalkError("--target が指定されていない")
    adapter = get_adapter(channel)
    state, evidence = adapter.receiver_state_with_evidence(target)
    return {
        "channel": channel,
        "target": target,
        "state": state,
        "evidence": {
            "source": evidence["source"],
            "observed": evidence["observed"],
        },
    }
