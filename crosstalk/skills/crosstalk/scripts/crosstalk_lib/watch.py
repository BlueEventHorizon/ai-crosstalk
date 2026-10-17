"""watch サブコマンド。回答の未着を見張るために、上限時間まで待って、終了時の受信側の状態を返す。

回答が届いたかどうかは確かめない。回答は別の入力として送信側へ届き、それを見た AI が
watch を止める。watch が最後まで走り切って終了したこと自体が「上限時間までに止められな
かった（未着）」の合図になる。待っている間は何も出力せず、標準出力は終了時の JSON 1 つだけ。

終了時の状態の取得に失敗したとき（宛先が無くなった、外部 CLI の出力が期待と異なる、等）は、
error にせず status は ok のまま timed_out を返し、state を unknown、evidence に失敗の理由
（state_error）を載せる。理由: ここで error にすると、上限時間まで待ったという事実が呼び出し
側に伝わらず、未着の報告ができなくなる。状態は付随情報であり、待った事実の方が主である。
一方、待つ前の引数の検証は、不正なら待たずに error を返す。
"""

import time

from .adapters import get_adapter
from .adapters.base import STATE_UNKNOWN
from .output import CrosstalkError

DEFAULT_TIMEOUT = 60
MIN_TIMEOUT = 1
MAX_TIMEOUT = 600  # 10 分。これを超える指定は受け付けない

CHANNELS = ("herdr", "orca", "csm")
ERROR_TEXT_LIMIT = 200

# 待つ処理。テストで差し替えて、実際には待たずに確かめられるようにする。
_sleep = time.sleep


def validate(args):
    """引数を検証し、(channel, target, timeout, request_id) を返す。不正なら CrosstalkError。"""
    channel = getattr(args, "channel", None)
    target = getattr(args, "target", None)
    timeout = getattr(args, "timeout", None)
    request_id = getattr(args, "request_id", None)

    if not channel:
        raise CrosstalkError(
            "--channel が指定されていない（herdr / orca / csm のいずれかを指定する）"
        )
    if channel not in CHANNELS:
        raise CrosstalkError(
            "未対応の通信路: %s（herdr / orca / csm のいずれかを指定する）"
            % str(channel)[:40]
        )
    if not target or not str(target).strip():
        raise CrosstalkError("--target が指定されていない")
    if timeout is None:
        timeout = DEFAULT_TIMEOUT
    if timeout < MIN_TIMEOUT or timeout > MAX_TIMEOUT:
        raise CrosstalkError(
            "--timeout は %d〜%d 秒で指定する（受け取った値: %d）"
            % (MIN_TIMEOUT, MAX_TIMEOUT, timeout)
        )
    if channel == "csm" and request_id is not None:
        raise CrosstalkError(
            "csm では --request-id を指定できない（CSM は依頼 ID を付けない）"
        )
    return channel, target, timeout, request_id


def run(args):
    channel, target, timeout, request_id = validate(args)

    # 回答の到着は確かめず、上限時間まで待つ。
    _sleep(timeout)

    result = {
        "channel": channel,
        "target": target,
        "timed_out": True,
        "waited_seconds": timeout,
    }
    if channel == "csm":
        # CSM は受信側の状態を返す手段を持たないので、adapter を使わず状態も含めない。
        return result

    if request_id is not None:
        result["request_id"] = request_id
    try:
        state, evidence = get_adapter(channel).receiver_state_with_evidence(target)
        result["state"] = state
        result["evidence"] = {
            "source": evidence["source"],
            "observed": evidence["observed"],
        }
    except (
        Exception
    ) as e:  # 状態が取れなくても、待った事実は失わない（モジュールの docstring 参照）
        reason = (
            e.reason
            if isinstance(e, CrosstalkError)
            else "%s: %s" % (type(e).__name__, e)
        )
        result["state"] = STATE_UNKNOWN
        result["evidence"] = {"state_error": str(reason)[:ERROR_TEXT_LIMIT]}
    return result
