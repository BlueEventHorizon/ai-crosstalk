"""JSON 出力とエラーの共通部品。標準出力には JSON を 1 つだけ出す。"""

import json
import sys


class CrosstalkError(Exception):
    """サブコマンドが error として終了するときの例外。reason が JSON に載る。"""

    def __init__(self, reason, **extra):
        super().__init__(reason)
        self.reason = reason
        self.extra = extra


def not_implemented(name):
    raise CrosstalkError("未実装", subcommand=name)


def emit(payload, stream=None):
    """payload を JSON 1 つとして標準出力へ書く。"""
    stream = stream or sys.stdout
    stream.write(json.dumps(payload, ensure_ascii=False) + "\n")
    stream.flush()


def ok_payload(data):
    payload = {"status": "ok"}
    payload.update(data or {})
    payload["status"] = "ok"
    return payload


def error_payload(reason, **extra):
    payload = dict(extra)
    payload["status"] = "error"
    payload["reason"] = str(reason)
    return payload
