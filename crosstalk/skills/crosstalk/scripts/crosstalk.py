#!/usr/bin/env python3
"""crosstalk の CLI。サブコマンドは detect / resolve / state / compose / send / watch。

すべてのサブコマンドは JSON を標準出力に 1 つ出す。status は ok か error で、
error のときは reason を添え、終了コードは 0 以外になる。状態は保存しない。
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from crosstalk_lib.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
