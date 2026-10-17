"""本文の文字の検査に使う共通部品。compose（置き換え）と send（拒否）が同じ判定を使う。"""

import re

# 端末の入力として解釈されうる文字。改行のほか、Ctrl-C・EOF・ESC（エスケープシーケンスの開始）、
# DEL、C1 制御文字、Unicode の行・段落区切りを含む。外部データ由来の本文に混ざると、受信側の
# ターンを中断したり、貼り付け区間を抜けて後続の文字をキー入力にしたりしうる。
CONTROL_CHARS = re.compile("[\x00-\x1f\x7f-\x9f  ]")


def has_control_chars(text):
    """text に、改行を含む端末入力として解釈されうる文字が 1 つでもあるか。"""
    return CONTROL_CHARS.search(text) is not None
