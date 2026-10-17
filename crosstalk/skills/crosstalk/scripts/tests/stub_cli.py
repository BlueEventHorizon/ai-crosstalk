"""テスト用の共通部品。stub の orca / herdr を PATH の先頭に置いて外部 CLI を置き換える。"""

import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest

SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CROSSTALK = os.path.join(SCRIPTS_DIR, "crosstalk.py")

# fixture に実在の名前・パス・ID が混ざっていないことを検査する。禁止語の一覧は、それ自体が実在の
# 名前を配布物に書くことになるので持たず、許可する匿名の形だけを通す。
ANON_PATH_PREFIXES = ("/work/sample", "/tmp/sample", "/sample")
_PATH_TOKEN = re.compile(r"(?:/[A-Za-z0-9._\-]+)+")
_UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
_REAL_HANDLE = re.compile(r"term_[0-9a-f]{6,}|\bw[A-Z]:p[0-9]")


def anonymity_problems(text):
    """fixture の文字列が、匿名の形でない箇所を返す（空なら匿名）。"""
    problems = []
    # git のブランチの参照名（refs/heads/...）はパスではない
    for token in _PATH_TOKEN.findall(text.replace("refs/heads/", "refs-heads-")):
        if not token.startswith(ANON_PATH_PREFIXES):
            problems.append("匿名でないパス: %s" % token)
    for pattern, label in (
        (_UUID, "UUID"),
        (_REAL_HANDLE, "実在の形の端末・pane の ID"),
    ):
        for m in pattern.findall(text):
            problems.append("%s: %s" % (label, m))
    try:
        data = json.loads(text)
    except ValueError:
        return problems
    stack = [data]
    while stack:
        node = stack.pop()
        if isinstance(node, dict):
            for key, value in node.items():
                if key in ("repo", "branch") and isinstance(value, str) and value:
                    if not value.replace("refs/heads/", "").startswith(
                        ("sample-", "feature-", "main")
                    ):
                        problems.append("匿名でない %s: %s" % (key, value))
                stack.append(value)
        elif isinstance(node, list):
            stack.extend(node)
    return problems


# 実行環境に由来する値。テストでは、明示した値だけを使う。
ISOLATED_ENV_KEYS = (
    "HERDR_ENV",
    "HERDR_PANE_ID",
    "ORCA_TERMINAL_HANDLE",
    "ORCA_PANE_KEY",
)


class StubCli:
    """一時ディレクトリに stub 実行ファイルを作る。呼び出しは calls.log に追記される。"""

    def __init__(self):
        self.dir = tempfile.mkdtemp(prefix="crosstalk-stub-")
        self.log = os.path.join(self.dir, "calls.log")
        open(self.log, "w").close()

    def add(self, name, stdout="", exit_code=0, stderr=""):
        path = os.path.join(self.dir, name)
        with open(path, "w") as f:
            f.write("#!/bin/sh\n")
            f.write('echo "%s $*" >> "%s"\n' % (name, self.log))
            if stderr:
                f.write("cat >&2 <<'STUB_EOF'\n%s\nSTUB_EOF\n" % stderr)
            f.write("cat <<'STUB_EOF'\n%s\nSTUB_EOF\n" % stdout)
            f.write("exit %d\n" % exit_code)
        os.chmod(path, os.stat(path).st_mode | stat.S_IXUSR)

    def calls(self):
        with open(self.log) as f:
            return [line.rstrip("\n") for line in f if line.strip()]

    def env(self, extra=None):
        env = dict(os.environ)
        # テストを実行している環境が herdr / Orca の管理下でも、結果が変わらないようにする
        for key in ISOLATED_ENV_KEYS:
            env.pop(key, None)
        env["PATH"] = self.dir + os.pathsep + env.get("PATH", "")
        env.update(extra or {})
        return env

    def cleanup(self):
        shutil.rmtree(self.dir, ignore_errors=True)


class StubTestCase(unittest.TestCase):
    """stub の orca / herdr を PATH 先頭に置いた状態で crosstalk.py を実行する基底クラス。"""

    def setUp(self):
        self.stub = StubCli()
        self.stub.add("orca")
        self.stub.add("herdr")
        self.addCleanup(self.stub.cleanup)

    def run_cli(self, *args, stdin="", env=None):
        proc = subprocess.run(
            [sys.executable, CROSSTALK] + list(args),
            input=stdin,
            capture_output=True,
            text=True,
            env=self.stub.env(env),
        )
        return proc
