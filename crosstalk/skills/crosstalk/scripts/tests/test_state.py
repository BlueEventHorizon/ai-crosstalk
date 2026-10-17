import json
import os
import stat
import unittest

from .stub_cli import StubTestCase

FIXTURE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")


def load_fixture(name):
    with open(os.path.join(FIXTURE_DIR, name)) as f:
        return f.read()


class StateTestBase(StubTestCase):
    def add_herdr(self, stdout=None, exit_code=0):
        text = load_fixture("herdr_agent_list.json") if stdout is None else stdout
        self.stub.add("herdr", stdout=text, exit_code=exit_code)

    def add_orca_router(self, ps=None, tl=None, read=None):
        ps = load_fixture("orca_worktree_ps.json") if ps is None else ps
        tl = load_fixture("orca_terminal_list.json") if tl is None else tl
        path = os.path.join(self.stub.dir, "orca")
        with open(path, "w") as f:
            f.write("#!/bin/sh\n")
            f.write('echo "orca $*" >> "%s"\n' % self.stub.log)
            if read is not None:
                f.write(
                    'if [ "$1" = "terminal" ] && [ "$2" = "read" ]; then\n'
                    "cat <<'STUB_EOF'\n%s\nSTUB_EOF\nexit 0\nfi\n" % read
                )
            f.write(
                'if [ "$1" = "worktree" ]; then\ncat <<\'STUB_EOF\'\n%s\nSTUB_EOF\nexit 0\nfi\n'
                % ps
            )
            f.write(
                'if [ "$1" = "terminal" ] && [ "$2" = "list" ]; then\ncat <<\'STUB_EOF\'\n%s\nSTUB_EOF\nexit 0\nfi\n'
                % tl
            )
            f.write("exit 2\n")
        os.chmod(path, os.stat(path).st_mode | stat.S_IXUSR)

    def state(self, channel, target, **env):
        proc = self.run_cli("state", "--channel", channel, "--target", target, env=env)
        return proc, json.loads(proc.stdout)


class HerdrStateTest(StateTestBase):
    def test_states_of_each_pane(self):
        self.add_herdr()
        cases = (
            ("w1:p1", "working", "working"),
            ("w2:p1", "idle", "idle"),
            ("w3:p1", "idle", "done"),
            ("w4:p1", "blocked", "blocked"),
        )
        for target, expected, observed in cases:
            with self.subTest(target=target):
                proc, out = self.state("herdr", target)
                self.assertEqual(proc.returncode, 0)
                self.assertEqual(out["status"], "ok")
                self.assertEqual(out["channel"], "herdr")
                self.assertEqual(out["target"], target)
                self.assertEqual(out["state"], expected)
                self.assertTrue(out["evidence"]["source"])
                # 対応づけ前の生の値が残る（done は idle に対応づけられても done のまま）
                self.assertEqual(out["evidence"]["observed"], observed)

    def test_missing_target_is_error(self):
        self.add_herdr()
        proc, out = self.state("herdr", "w9:p9")
        self.assertEqual(proc.returncode, 1)
        self.assertEqual(out["status"], "error")
        self.assertNotIn("state", out)

    def test_unknown_agent_status_is_error(self):
        data = json.loads(load_fixture("herdr_agent_list.json"))
        data["result"]["agents"][0]["agent_status"] = "sample-other"
        self.add_herdr(stdout=json.dumps(data))
        proc, out = self.state("herdr", "w1:p1")
        self.assertEqual(out["status"], "error")

    def test_command_failure_is_error(self):
        self.add_herdr(stdout="", exit_code=1)
        proc, out = self.state("herdr", "w1:p1")
        self.assertEqual(out["status"], "error")

    def test_broken_output_is_error(self):
        self.add_herdr(stdout="{not json")
        proc, out = self.state("herdr", "w1:p1")
        self.assertEqual(out["status"], "error")

    def test_only_reads_agent_list(self):
        self.add_herdr()
        self.state("herdr", "w1:p1")
        self.assertEqual(self.stub.calls(), ["herdr agent list"])

    def test_ignores_environment_of_caller(self):
        self.add_herdr()
        _, out = self.state("herdr", "w2:p1", HERDR_ENV="1", HERDR_PANE_ID="w1:p1")
        self.assertEqual(out["state"], "idle")


class OrcaStateTest(StateTestBase):
    def test_claude_done_is_idle(self):
        self.add_orca_router(read="{}")
        proc, out = self.state("orca", "term-0002")
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(out["state"], "idle")
        self.assertEqual(out["channel"], "orca")
        self.assertEqual(out["target"], "term-0002")
        self.assertEqual(out["evidence"]["observed"], "done")
        self.assertIn("worktree ps", out["evidence"]["source"])

    def test_claude_working_is_working(self):
        self.add_orca_router(read="{}")
        _, out = self.state("orca", "term-0001")
        self.assertEqual(out["state"], "working")
        self.assertEqual(out["evidence"]["observed"], "working")

    def test_codex_idle_screen_is_idle(self):
        self.add_orca_router(read=load_fixture("orca_codex_screen_idle.json"))
        _, out = self.state("orca", "term-0003")
        self.assertEqual(out["status"], "ok")
        self.assertEqual(out["state"], "idle")
        self.assertIn("terminal read", out["evidence"]["source"])
        self.assertTrue(out["evidence"]["observed"])

    def test_codex_unrecognized_screens_are_unknown(self):
        for name in ("orca_codex_screen_draft.json", "orca_codex_screen_other.json"):
            with self.subTest(fixture=name):
                self.add_orca_router(read=load_fixture(name))
                _, out = self.state("orca", "term-0003")
                self.assertEqual(out["status"], "ok")
                self.assertEqual(out["state"], "unknown")
                self.assertTrue(out["evidence"]["observed"])

    def test_unreadable_screen_is_unknown(self):
        self.add_orca_router(read="{not json")
        _, out = self.state("orca", "term-0003")
        self.assertEqual(out["state"], "unknown")

    def test_claude_without_record_is_unknown(self):
        ps = json.loads(load_fixture("orca_worktree_ps.json"))
        ps["result"]["worktrees"][0]["agents"] = []
        self.add_orca_router(ps=json.dumps(ps), read="{}")
        _, out = self.state("orca", "term-0001")
        self.assertEqual(out["state"], "unknown")

    def test_missing_target_is_error(self):
        self.add_orca_router(read="{}")
        proc, out = self.state("orca", "term-9999")
        self.assertEqual(proc.returncode, 1)
        self.assertEqual(out["status"], "error")
        self.assertNotIn("state", out)

    def test_never_sends_to_terminal(self):
        self.add_orca_router(read=load_fixture("orca_codex_screen_idle.json"))
        for target in ("term-0001", "term-0002", "term-0003"):
            self.state("orca", target)
        for call in self.stub.calls():
            self.assertNotIn(" send", call)
            self.assertNotIn(" prompt", call)


class ArgumentTest(StateTestBase):
    def check_error(self, *args):
        proc = self.run_cli("state", *args)
        out = json.loads(proc.stdout)
        self.assertEqual(out["status"], "error")
        self.assertNotEqual(proc.returncode, 0)
        return out

    def test_missing_channel_is_error(self):
        self.check_error("--target", "t")

    def test_missing_target_is_error(self):
        self.check_error("--channel", "herdr")

    def test_unsupported_channel_is_error(self):
        for channel in ("csm", "other", ""):
            with self.subTest(channel=channel):
                self.check_error("--channel", channel, "--target", "t")

    def test_unsupported_channel_does_not_call_external_cli(self):
        self.check_error("--channel", "csm", "--target", "t")
        self.assertEqual(self.stub.calls(), [])


if __name__ == "__main__":
    unittest.main()
