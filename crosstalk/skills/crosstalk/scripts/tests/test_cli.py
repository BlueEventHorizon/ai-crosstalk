import importlib
import inspect
import json
import os
import re
import shutil
import sys
import unittest

from .stub_cli import SCRIPTS_DIR, StubTestCase


def is_unimplemented(name):
    """サブコマンドのモジュールが、まだ未実装の受け口か（not_implemented を呼んでいるか）。"""
    module = importlib.import_module("crosstalk_lib." + name)
    return "not_implemented(" in inspect.getsource(module.run)


SUBCOMMANDS = {
    "detect": [],
    "resolve": [
        "--channel",
        "herdr",
        "--repo",
        "r",
        "--worktree",
        "w",
        "--agent-kind",
        "claude",
    ],
    "state": ["--channel", "herdr", "--target", "t"],
    "compose": ["--channel", "orca", "--target", "t", "--kind", "ask"],
    "send": [
        "--channel",
        "orca",
        "--target",
        "t",
        "--agent-kind",
        "codex",
        "--request-id",
        "abc123",
    ],
    "watch": [
        "--channel",
        "herdr",
        "--target",
        "t",
        "--timeout",
        "1",
        "--request-id",
        "abc123",
    ],
}


class CliTest(StubTestCase):
    def parse(self, proc):
        self.assertEqual(proc.stdout.count("\n"), 1, "標準出力は JSON 1 つだけ")
        return json.loads(proc.stdout)

    def test_unknown_subcommand_is_json_error(self):
        proc = self.run_cli("bogus")
        self.assertNotEqual(proc.returncode, 0)
        out = self.parse(proc)
        self.assertEqual(out["status"], "error")
        self.assertTrue(out["reason"])

    def test_no_subcommand_is_json_error(self):
        proc = self.run_cli()
        self.assertNotEqual(proc.returncode, 0)
        self.assertEqual(self.parse(proc)["status"], "error")

    def test_usage_error_is_json_error(self):
        proc = self.run_cli("watch", "--timeout", "abc")
        self.assertNotEqual(proc.returncode, 0)
        self.assertEqual(self.parse(proc)["status"], "error")

    def test_unknown_option_is_json_error(self):
        proc = self.run_cli("detect", "--nope")
        self.assertNotEqual(proc.returncode, 0)
        self.assertEqual(self.parse(proc)["status"], "error")

    def test_help_option_is_json_error(self):
        for argv in (["-h"], ["--help"], ["detect", "-h"], ["watch", "--help"]):
            with self.subTest(argv=argv):
                proc = self.run_cli(*argv)
                self.assertNotEqual(proc.returncode, 0)
                self.assertEqual(self.parse(proc)["status"], "error")

    # 本体が未実装のサブコマンドは、JSON の error（reason「未実装」）を返す。
    # どれが未実装かは、モジュールが not_implemented を呼んでいるかで決まる。本体を実装すると、
    # そのサブコマンドは自動でこの検査の対象から外れる（そのサブコマンド自身のテストが契約を検査する）。
    def test_each_unimplemented_entry_returns_json_not_implemented(self):
        for name, extra in SUBCOMMANDS.items():
            if not is_unimplemented(name):
                continue
            with self.subTest(subcommand=name):
                proc = self.run_cli(name, *extra, stdin="本文")
                self.assertNotEqual(proc.returncode, 0)
                out = self.parse(proc)
                self.assertEqual(out["status"], "error")
                self.assertIn("未実装", out["reason"])

    def test_subcommands_run_against_stub_not_real_cli(self):
        # 全サブコマンドを実行しても、PATH 先頭の stub が実際の orca / herdr より先に解決される。
        # 送信系のコマンドを含め、実際のセッションへ何かが届く事故を、テストの側で防ぐ。
        for tool in ("orca", "herdr"):
            resolved = shutil.which(tool, path=self.stub.env()["PATH"])
            self.assertTrue(
                resolved.startswith(self.stub.dir), "%s が stub でない" % tool
            )
        for name, extra in SUBCOMMANDS.items():
            self.run_cli(name, *extra, stdin="本文")
        for call in self.stub.calls():
            self.assertTrue(call.startswith(("orca ", "herdr ")))

    def test_stub_replaces_real_cli(self):
        self.stub.add("orca", stdout="stub-orca")
        self.stub.add("herdr", stdout="stub-herdr")
        import subprocess

        for name in ("orca", "herdr"):
            out = subprocess.run(
                [name, "status"], capture_output=True, text=True, env=self.stub.env()
            ).stdout
            self.assertEqual(out.strip(), "stub-" + name)
        self.assertEqual(self.stub.calls(), ["orca status", "herdr status"])

    def test_only_standard_library_imports(self):
        stdlib = set(sys.stdlib_module_names)
        pat = re.compile(r"^\s*(?:from\s+(\S+)\s+import|import\s+(\S+))", re.M)
        for root, dirs, files in os.walk(SCRIPTS_DIR):
            dirs[:] = [d for d in dirs if d != "__pycache__"]
            for fn in files:
                if not fn.endswith(".py"):
                    continue
                with open(os.path.join(root, fn), encoding="utf-8") as f:
                    text = f.read()
                for m in pat.finditer(text):
                    mod = (m.group(1) or m.group(2)).split(".")[0].rstrip(",")
                    if mod.startswith(".") or mod in ("crosstalk_lib", "tests", ""):
                        continue
                    self.assertIn(mod, stdlib, "%s: %s" % (fn, mod))


if __name__ == "__main__":
    unittest.main()
