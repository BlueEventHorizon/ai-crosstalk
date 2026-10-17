"""detect サブコマンド。使える通信路（herdr / Orca / none）を判定する。"""

import os

from . import adapters
from .adapters import herdr, orca


def _env_present(channel):
    """判定に使う環境変数が有効な値で設定されているか。"""
    if channel == "herdr":
        return os.environ.get(herdr.AVAILABLE_ENV) == herdr.AVAILABLE_ENV_VALUE
    return bool(os.environ.get(orca.AVAILABLE_ENV))


def _env_name(channel):
    return herdr.AVAILABLE_ENV if channel == "herdr" else orca.AVAILABLE_ENV


def _condition(channel, env_present, available):
    env = _env_name(channel)
    if channel == "herdr":
        need = "環境変数 %s=%s かつ herdr agent list が成功する" % (
            env,
            herdr.AVAILABLE_ENV_VALUE,
        )
    else:
        need = "環境変数 %s が設定され、orca status で実行環境に到達できる" % env
    if available:
        return "%s: 満たした" % need
    if env_present:
        return "環境変数 %s はあるが接続できない（%s）" % (env, need)
    return "環境変数 %s が無い（%s）" % (env, need)


def run(args):
    evidence = []
    channel = "none"
    # ADAPTERS の順（herdr が先）に判定し、有効な最初の通信路で止める
    for name in adapters.ADAPTERS:
        env_present = _env_present(name)
        available = adapters.get_adapter(name).available()
        evidence.append(
            {
                "channel": name,
                "env": _env_name(name),
                "env_present": env_present,
                "available": available,
                "condition": _condition(name, env_present, available),
            }
        )
        if available:
            channel = name
            break
    return {"channel": channel, "evidence": evidence}
