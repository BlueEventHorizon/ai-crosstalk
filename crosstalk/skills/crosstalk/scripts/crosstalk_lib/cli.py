"""サブコマンドの解釈と JSON 出力の入口。"""

import argparse
import sys

from . import compose, detect, resolve, send, state, watch
from .output import CrosstalkError, emit, error_payload, ok_payload


class JsonArgumentParser(argparse.ArgumentParser):
    """使い方エラーも JSON の error として標準出力へ出す。"""

    def error(self, message):
        emit(error_payload("引数の誤り: " + message))
        sys.exit(2)


def build_parser():
    # -h / --help は、使い方の文章を標準出力に出して終了コード 0 で終わるため無効にする
    # （標準出力は JSON 1 つだけにする）。-h は使い方の誤りとして JSON の error になる。
    parser = JsonArgumentParser(prog="crosstalk.py", add_help=False)
    sub = parser.add_subparsers(dest="subcommand", parser_class=JsonArgumentParser)

    sub.add_parser("detect", add_help=False)

    p = sub.add_parser("resolve", add_help=False)
    p.add_argument("--channel")
    p.add_argument("--repo")
    p.add_argument("--worktree")
    p.add_argument("--agent-kind")

    p = sub.add_parser("state", add_help=False)
    p.add_argument("--channel")
    p.add_argument("--target")

    p = sub.add_parser("compose", add_help=False)
    p.add_argument("--channel")
    p.add_argument("--target")
    p.add_argument("--kind")

    p = sub.add_parser("send", add_help=False)
    p.add_argument("--channel")
    p.add_argument("--target")
    p.add_argument("--agent-kind")
    p.add_argument("--request-id")

    p = sub.add_parser("watch", add_help=False)
    p.add_argument("--channel")
    p.add_argument("--target")
    p.add_argument("--timeout", type=int)
    p.add_argument("--request-id")

    return parser


HANDLERS = {
    "detect": detect.run,
    "resolve": resolve.run,
    "state": state.run,
    "compose": compose.run,
    "send": send.run,
    "watch": watch.run,
}


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.subcommand is None:
        emit(error_payload("サブコマンドが指定されていません"))
        return 2
    try:
        data = HANDLERS[args.subcommand](args)
    except CrosstalkError as e:
        emit(error_payload(e.reason, **e.extra))
        return 1
    except Exception as e:  # 想定外の失敗も推測で続行せず error で止まる
        emit(error_payload("想定外のエラー: %s: %s" % (type(e).__name__, e)))
        return 1
    emit(ok_payload(data))
    return 0
