"""通信路ごとの adapter。外部 CLI の呼び出しと出力の正規化を担う。"""

from ..output import CrosstalkError
from .herdr import HerdrAdapter
from .orca import OrcaAdapter

# 判定の順序でもある。herdr を先に判定する。
ADAPTERS = {
    "herdr": HerdrAdapter,
    "orca": OrcaAdapter,
}


def get_adapter(channel):
    """通信路の名前から adapter を返す。herdr / orca 以外は CrosstalkError。"""
    cls = ADAPTERS.get(channel)
    if cls is None:
        raise CrosstalkError(
            "未対応の通信路: %s（herdr / orca のどちらかを指定する）"
            % str(channel)[:40]
        )
    return cls()
