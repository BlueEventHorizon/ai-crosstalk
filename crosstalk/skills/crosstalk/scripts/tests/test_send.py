import json
import os
import shutil
import stat
import sys

from .stub_cli import StubTestCase

FIXTURE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")

# 本文。compose が作る 1 行の本文の形に似せた匿名の文字列（引用符・バックスラッシュ・日本語を含む）。
BODY = '[crosstalk 依頼 ID: a1b2c3] 本文の例 "quoted" back\\slash $HOME `x` 終わり'


def fixture(name):
    with open(os.path.join(FIXTURE_DIR, name)) as f:
        return f.read()


# 実機（Orca 1.4.221）で確認した応答の形（tests/fixtures/orca_send_response.json。値は匿名）。
# turn_started を含む形と、含まない形（input_accepted だけ。--wait-submit の時間内にターンの開始を観測できない形）。
ORCA_WITH_TURN_STARTED = fixture("orca_send_response.json")
_without = json.loads(ORCA_WITH_TURN_STARTED)
_without["result"]["send"]["prompt"]["stages"] = ["input_accepted"]
ORCA_WITHOUT_TURN_STARTED = json.dumps(_without)

# route の stub。argv を JSON の 1 行で calls.log に追記し、最初の 2 つの引数で出力を選ぶ。
STUB_TEMPLATE = """#!{python}
import json, sys
NAME = {name!r}
LOG = {log!r}
ROUTES = {routes!r}
args = sys.argv[1:]
with open(LOG, "a") as f:
    f.write(json.dumps([NAME] + args, ensure_ascii=False) + "\\n")
route = ROUTES.get(" ".join(args[:2]))
if route is None:
    sys.exit(2)
sys.stdout.write(route[0])
sys.stderr.write(route[2])
sys.exit(route[1])
"""

SEND_COMMANDS = {"herdr": ("agent", "prompt"), "orca": ("terminal", "send")}


class SendTestBase(StubTestCase):
    def setUp(self):
        super().setUp()
        self.herdr_send = ("", 0, "")
        self.orca_send = ("", 0, "")
        self.install()

    def install(self):
        """この stub は、送信コマンドの引数を calls.log に残す。送信コマンドの出力は各テストが決める。"""
        herdr_routes = {
            "agent list": (fixture("herdr_agent_list.json"), 0, ""),
            "agent prompt": self.herdr_send,
        }
        orca_routes = {
            "worktree ps": (fixture("orca_worktree_ps.json"), 0, ""),
            "terminal list": (fixture("orca_terminal_list.json"), 0, ""),
            "terminal send": self.orca_send,
        }
        for name, routes in (("herdr", herdr_routes), ("orca", orca_routes)):
            path = os.path.join(self.stub.dir, name)
            with open(path, "w") as f:
                f.write(
                    STUB_TEMPLATE.format(
                        python=sys.executable,
                        name=name,
                        log=self.stub.log,
                        routes=routes,
                    )
                )
            os.chmod(path, os.stat(path).st_mode | stat.S_IXUSR)

    def assert_stub_first_on_path(self):
        # 送る前に、PATH 先頭の stub が実際の orca / herdr より先に解決されることを検査する。
        # 先頭でなければ、実際のセッションへ送ってしまうため、送る前にテストを失敗させる。
        path = self.stub.env()["PATH"]
        self.assertEqual(path.split(os.pathsep)[0], self.stub.dir)
        for tool in ("orca", "herdr"):
            resolved = shutil.which(tool, path=path)
            self.assertTrue(
                resolved and resolved.startswith(self.stub.dir),
                "%s が stub でない" % tool,
            )

    def send(self, channel, target, agent_kind, body=BODY, request_id=None, extra=None):
        self.assert_stub_first_on_path()
        argv = ["send", "--channel", channel, "--target", target]
        if agent_kind is not None:
            argv += ["--agent-kind", agent_kind]
        if request_id is not None:
            argv += ["--request-id", request_id]
        argv += extra or []
        proc = self.run_cli(*argv, stdin=body)
        self.assertEqual(proc.stdout.count("\n"), 1, "標準出力は JSON 1 つだけ")
        return proc, json.loads(proc.stdout)

    def calls(self):
        return [json.loads(line) for line in self.stub.calls()]

    def send_calls(self):
        out = []
        for call in self.calls():
            name, args = call[0], call[1:]
            if tuple(args[:2]) == SEND_COMMANDS[name]:
                out.append(call)
        return out

    def reinstall(self, herdr_send=None, orca_send=None):
        if herdr_send is not None:
            self.herdr_send = herdr_send
        if orca_send is not None:
            self.orca_send = orca_send
        self.install()


class DestinationCheckTest(SendTestBase):
    def test_missing_target_sends_nothing(self):
        for channel in ("herdr", "orca"):
            with self.subTest(channel=channel):
                proc, out = self.send(channel, "no-such-target", "claude")
                self.assertNotEqual(proc.returncode, 0)
                self.assertEqual(out["status"], "error")
                self.assertEqual(self.send_calls(), [])

    def test_kind_mismatch_sends_nothing(self):
        # herdr の w2:p1 と Orca の term-0001 は claude。codex を期待すると一致しない
        for channel, target in (("herdr", "w2:p1"), ("orca", "term-0001")):
            with self.subTest(channel=channel):
                proc, out = self.send(channel, target, "codex")
                self.assertNotEqual(proc.returncode, 0)
                self.assertEqual(out["status"], "error")
                self.assertEqual(self.send_calls(), [])

    def test_candidates_are_fetched_before_send(self):
        self.reinstall(herdr_send=(fixture("herdr_prompt_response.json"), 0, ""))
        self.send("herdr", "w2:p1", "claude")
        names = [call[1:3] for call in self.calls()]
        self.assertEqual(names, [["agent", "list"], ["agent", "prompt"]])


class HerdrSendTest(SendTestBase):
    def test_receipt_confirmed(self):
        self.reinstall(herdr_send=(fixture("herdr_prompt_response.json"), 0, ""))
        proc, out = self.send("herdr", "w2:p1", "claude", request_id="a1b2c3")
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(out["status"], "ok")
        self.assertEqual(out["channel"], "herdr")
        self.assertEqual(out["target"], "w2:p1")
        self.assertEqual(out["agent_kind"], "claude")
        self.assertTrue(out["receipt"]["confirmed"])
        self.assertEqual(out["receipt"]["evidence"]["observed"], "agent_prompted")
        self.assertEqual(len(self.send_calls()), 1)

    def test_command_args_and_body_are_identical(self):
        self.reinstall(herdr_send=(fixture("herdr_prompt_response.json"), 0, ""))
        self.send("herdr", "w2:p1", "claude")
        # herdr agent prompt <pane> <本文>。--wait などは付けない。本文は標準入力と完全に同一
        self.assertEqual(
            self.send_calls(), [["herdr", "agent", "prompt", "w2:p1", BODY]]
        )

    def test_receipt_not_confirmed_is_ok_and_sent_once(self):
        for stdout in ('{"id":"x","result":{"type":"other"}}', "{}", "not json", ""):
            with self.subTest(stdout=stdout):
                self.reinstall(herdr_send=(stdout, 0, ""))
                open(self.stub.log, "w").close()
                proc, out = self.send("herdr", "w2:p1", "claude")
                self.assertEqual(proc.returncode, 0)
                self.assertEqual(out["status"], "ok")
                self.assertFalse(out["receipt"]["confirmed"])
                self.assertEqual(out["receipt"]["evidence"]["observed"], "確認できない")
                self.assertIn("再送しない", out["note"])
                self.assertEqual(len(self.send_calls()), 1)

    def test_send_failure_is_error_and_not_retried(self):
        self.reinstall(herdr_send=("", 1, "agent_blocked"))
        proc, out = self.send("herdr", "w2:p1", "claude")
        self.assertNotEqual(proc.returncode, 0)
        self.assertEqual(out["status"], "error")
        self.assertIn("再送しない", out["reason"])
        self.assertEqual(len(self.send_calls()), 1)


class OrcaSendTest(SendTestBase):
    def test_receipt_confirmed(self):
        self.reinstall(orca_send=(ORCA_WITH_TURN_STARTED, 0, ""))
        proc, out = self.send("orca", "term-0003", "codex", request_id="a1b2c3")
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(out["status"], "ok")
        self.assertEqual(out["target"], "term-0003")
        self.assertEqual(out["agent_kind"], "codex")
        self.assertTrue(out["receipt"]["confirmed"])
        self.assertEqual(out["receipt"]["evidence"]["observed"], "turn_started")
        self.assertEqual(len(self.send_calls()), 1)

    def test_command_args_and_body_are_identical(self):
        self.reinstall(orca_send=(ORCA_WITH_TURN_STARTED, 0, ""))
        self.send("orca", "term-0003", "codex")
        self.assertEqual(
            self.send_calls(),
            [
                [
                    "orca",
                    "terminal",
                    "send",
                    "--terminal",
                    "term-0003",
                    "--text",
                    BODY,
                    "--enter",
                    "--wait-submit",
                    "10",
                    "--json",
                ]
            ],
        )

    def test_receipt_not_confirmed_is_ok_and_sent_once(self):
        cases = (
            ORCA_WITHOUT_TURN_STARTED,
            json.dumps({"ok": False, "result": {"stages": ["turn_started"]}}),
            "{}",
            "not json",
            "",
        )
        for stdout in cases:
            with self.subTest(stdout=stdout):
                self.reinstall(orca_send=(stdout, 0, ""))
                open(self.stub.log, "w").close()
                proc, out = self.send("orca", "term-0003", "codex")
                self.assertEqual(proc.returncode, 0)
                self.assertEqual(out["status"], "ok")
                self.assertFalse(out["receipt"]["confirmed"])
                self.assertIn("再送しない", out["note"])
                self.assertEqual(len(self.send_calls()), 1)

    def test_send_failure_is_error_and_not_retried(self):
        self.reinstall(orca_send=("", 1, "boom"))
        proc, out = self.send("orca", "term-0003", "codex")
        self.assertNotEqual(proc.returncode, 0)
        self.assertEqual(out["status"], "error")
        self.assertIn("再送しない", out["reason"])
        self.assertEqual(len(self.send_calls()), 1)

    def test_send_failure_does_not_echo_body_in_output(self):
        # 外部 CLI がエラーに引数（本文）をエコーしても、出力には本文を載せない
        echo = "error: invalid --text " + BODY
        for channel, target, kind in (
            ("herdr", "w2:p1", "claude"),
            ("orca", "term-0003", "codex"),
        ):
            with self.subTest(channel=channel):
                self.reinstall(herdr_send=("", 1, echo), orca_send=("", 1, echo))
                proc, out = self.send(channel, target, kind)
                self.assertEqual(out["status"], "error")
                self.assertNotIn(BODY, proc.stdout)
                self.assertIn("<本文>", out["detail"])


class BodyAndArgsTest(SendTestBase):
    def test_trailing_newline_of_stdin_is_ignored_and_body_is_sent_unchanged(self):
        # heredoc や echo は入力の終端に改行を付ける。それだけは無視し、本文は変えずに 1 回だけ送る
        self.reinstall(
            herdr_send=(fixture("herdr_prompt_response.json"), 0, ""),
            orca_send=(ORCA_WITH_TURN_STARTED, 0, ""),
        )
        for channel, target, kind in (
            ("herdr", "w2:p1", "claude"),
            ("orca", "term-0003", "codex"),
        ):
            for ending in ("\n", "\r\n"):
                with self.subTest(channel=channel, ending=repr(ending)):
                    before = len(self.send_calls())
                    proc, out = self.send(channel, target, kind, body=BODY + ending)
                    self.assertEqual(proc.returncode, 0)
                    self.assertEqual(out["status"], "ok")
                    calls = self.send_calls()
                    self.assertEqual(len(calls), before + 1)
                    self.assertIn(BODY, calls[-1])

    def test_control_chars_in_body_send_nothing(self):
        samples = {
            "LF": "a\nb",
            "CR": "a\rb",
            "inner LF with trailing LF": BODY + "\n" + BODY + "\n",
            "NUL": "a\x00b",
            "ESC": "a\x1bb",
            "ETX": "a\x03b",
            "DEL": "a\x7fb",
            "C1": "a\x85b",
            "LS": "a b",
            "PS": "a b",
        }
        for label, body in samples.items():
            for channel, target, kind in (
                ("herdr", "w2:p1", "claude"),
                ("orca", "term-0003", "codex"),
            ):
                with self.subTest(label=label, channel=channel):
                    proc, out = self.send(channel, target, kind, body=body)
                    self.assertNotEqual(proc.returncode, 0)
                    self.assertEqual(out["status"], "error")
                    self.assertEqual(self.send_calls(), [])

    def test_empty_body_is_error(self):
        for body in ("", "   "):
            with self.subTest(body=body):
                proc, out = self.send("herdr", "w2:p1", "claude", body=body)
                self.assertNotEqual(proc.returncode, 0)
                self.assertEqual(out["status"], "error")
                self.assertEqual(self.send_calls(), [])

    def test_body_starting_with_hyphen_sends_nothing(self):
        proc, out = self.send("herdr", "w2:p1", "claude", body="--wait x")
        self.assertEqual(out["status"], "error")
        self.assertEqual(self.send_calls(), [])

    def test_request_id_is_accepted_and_returned(self):
        self.reinstall(herdr_send=(fixture("herdr_prompt_response.json"), 0, ""))
        proc, out = self.send("herdr", "w2:p1", "claude", request_id="a1b2c3")
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(out["request_id"], "a1b2c3")

    def test_request_id_is_omitted_when_not_given(self):
        self.reinstall(herdr_send=(fixture("herdr_prompt_response.json"), 0, ""))
        proc, out = self.send("herdr", "w2:p1", "claude")
        self.assertEqual(proc.returncode, 0)
        self.assertNotIn("request_id", out)

    def test_request_id_does_not_change_the_sent_command(self):
        self.reinstall(herdr_send=(fixture("herdr_prompt_response.json"), 0, ""))
        self.send("herdr", "w2:p1", "claude", request_id="a1b2c3")
        self.assertEqual(
            self.send_calls(), [["herdr", "agent", "prompt", "w2:p1", BODY]]
        )

    def test_missing_agent_kind_is_error(self):
        proc, out = self.send("herdr", "w2:p1", None)
        self.assertNotEqual(proc.returncode, 0)
        self.assertEqual(out["status"], "error")
        self.assertEqual(self.send_calls(), [])

    def test_missing_target_option_is_error(self):
        self.assert_stub_first_on_path()
        proc = self.run_cli(
            "send", "--channel", "herdr", "--agent-kind", "claude", stdin=BODY
        )
        self.assertNotEqual(proc.returncode, 0)
        self.assertEqual(json.loads(proc.stdout)["status"], "error")
        self.assertEqual(self.send_calls(), [])

    def test_csm_channel_is_error(self):
        for channel in ("csm", "bogus"):
            with self.subTest(channel=channel):
                proc, out = self.send(channel, "x", "claude")
                self.assertNotEqual(proc.returncode, 0)
                self.assertEqual(out["status"], "error")
        self.assertEqual(self.calls(), [])

    def test_missing_channel_is_error(self):
        self.assert_stub_first_on_path()
        proc = self.run_cli(
            "send", "--target", "x", "--agent-kind", "claude", stdin=BODY
        )
        self.assertNotEqual(proc.returncode, 0)
        self.assertEqual(self.calls(), [])

    def test_send_does_not_reach_real_cli(self):
        # stub が PATH の先頭にあるため、記録された呼び出しはすべて stub が受けたものである
        self.reinstall(herdr_send=(fixture("herdr_prompt_response.json"), 0, ""))
        self.send("herdr", "w2:p1", "claude")
        self.assertTrue(self.calls())
        for call in self.calls():
            self.assertIn(call[0], ("orca", "herdr"))


if __name__ == "__main__":
    import unittest

    unittest.main()
