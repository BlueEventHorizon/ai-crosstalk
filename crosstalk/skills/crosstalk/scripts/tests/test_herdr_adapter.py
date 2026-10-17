import json
import os
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

from crosstalk_lib.adapters.base import Candidate
from crosstalk_lib.adapters.herdr import (
    HerdrAdapter,
    parse_agent_list,
    parse_prompt_response,
)
from crosstalk_lib.output import CrosstalkError

from .stub_cli import StubCli, anonymity_problems

FIXTURE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")


def load_fixture(name="herdr_agent_list.json"):
    with open(os.path.join(FIXTURE_DIR, name)) as f:
        return f.read()


def list_json(agents):
    return json.dumps(
        {"id": "cli:agent:list", "result": {"type": "agent_list", "agents": agents}}
    )


def agent(status="idle", **over):
    item = {
        "agent": "claude",
        "agent_status": status,
        "cwd": "/work/x",
        "pane_id": "w9:p1",
    }
    item.update(over)
    return item


class ParseTest(unittest.TestCase):
    def test_fixture_normalized(self):
        cands = parse_agent_list(load_fixture())
        self.assertEqual(len(cands), 4)
        first = cands[0]
        self.assertEqual(first.channel, "herdr")
        self.assertEqual(first.target, "w1:p1")
        self.assertEqual(first.worktree, "/work/sample-a")
        self.assertEqual(first.agent_kind, "claude")
        self.assertEqual(first.state, "working")
        self.assertEqual(cands[2].agent_kind, "codex")

    def test_repo_and_branch_are_empty(self):
        for c in parse_agent_list(load_fixture()):
            self.assertEqual(c.repo, "")
            self.assertEqual(c.branch, "")

    def test_status_mapping(self):
        for status, expected in (
            ("idle", "idle"),
            ("done", "idle"),
            ("working", "working"),
            ("blocked", "blocked"),
        ):
            with self.subTest(status=status):
                self.assertEqual(
                    parse_agent_list(list_json([agent(status)]))[0].state, expected
                )

    def test_unknown_status_is_error(self):
        with self.assertRaises(CrosstalkError):
            parse_agent_list(list_json([agent("sleeping")]))

    def test_broken_json_is_error(self):
        for text in (
            "",
            "{not json",
            "null",
            '"x"',
            "{}",
            '{"result":{}}',
            '{"result":{"agents":"x"}}',
            # 実機で確認した形（result.agents）以外は受理しない
            '{"agents":[]}',
            "[]",
        ):
            with self.subTest(text=text):
                with self.assertRaises(CrosstalkError):
                    parse_agent_list(text)

    def test_missing_required_field_is_error(self):
        for field in ("agent", "agent_status", "cwd", "pane_id"):
            with self.subTest(field=field):
                item = agent()
                del item[field]
                with self.assertRaises(CrosstalkError):
                    parse_agent_list(list_json([item]))

    def test_non_object_item_is_error(self):
        with self.assertRaises(CrosstalkError):
            parse_agent_list(list_json(["x"]))

    def test_error_envelope_is_error(self):
        with self.assertRaises(CrosstalkError):
            parse_agent_list(
                json.dumps(
                    {"id": "cli:agent:list", "error": {"code": "x", "message": "y"}}
                )
            )

    def test_empty_list_is_zero_candidates(self):
        self.assertEqual(parse_agent_list(list_json([])), [])

    def test_fixture_is_anonymous(self):
        for name in ("herdr_agent_list.json", "herdr_prompt_response.json"):
            with self.subTest(fixture=name):
                self.assertEqual(anonymity_problems(load_fixture(name)), [])


class AdapterTest(unittest.TestCase):
    def setUp(self):
        self.stub = StubCli()
        self.addCleanup(self.stub.cleanup)

    def patch_env(self, **extra):
        env = self.stub.env(extra)
        for key in ("HERDR_ENV", "HERDR_PANE_ID"):
            if key not in extra:
                env.pop(key, None)
        patcher = mock.patch.dict(os.environ, env, clear=True)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_candidates_calls_agent_list(self):
        self.stub.add("herdr", stdout=load_fixture())
        self.patch_env()
        cands = HerdrAdapter().candidates()
        self.assertEqual(len(cands), 4)
        self.assertEqual(self.stub.calls(), ["herdr agent list"])

    def test_receiver_state(self):
        self.stub.add("herdr", stdout=load_fixture())
        self.patch_env()
        adapter = HerdrAdapter()
        self.assertEqual(adapter.receiver_state("w2:p1"), "idle")
        self.assertEqual(adapter.receiver_state("w3:p1"), "idle")
        self.assertEqual(adapter.receiver_state("w1:p1"), "working")
        self.assertEqual(adapter.receiver_state("w4:p1"), "blocked")

    def test_receiver_state_with_evidence_keeps_raw_status(self):
        self.stub.add("herdr", stdout=load_fixture())
        self.patch_env()
        adapter = HerdrAdapter()
        # done は idle に対応づけるが、根拠には herdr が返した値をそのまま残す
        state, evidence = adapter.receiver_state_with_evidence("w3:p1")
        self.assertEqual(state, "idle")
        self.assertEqual(evidence["observed"], "done")
        self.assertIn("agent_status", evidence["source"])

    def test_receiver_state_unknown_pane_is_error(self):
        self.stub.add("herdr", stdout=load_fixture())
        self.patch_env()
        with self.assertRaises(CrosstalkError):
            HerdrAdapter().receiver_state("nope")

    def test_command_failure_is_error(self):
        self.stub.add("herdr", stdout="boom", exit_code=1)
        self.patch_env()
        with self.assertRaises(CrosstalkError):
            HerdrAdapter().candidates()

    def test_command_failure_keeps_stderr_in_detail(self):
        self.stub.add("herdr", stdout="", exit_code=1, stderr="version mismatch")
        self.patch_env()
        with self.assertRaises(CrosstalkError) as ctx:
            HerdrAdapter().candidates()
        self.assertIn("version mismatch", ctx.exception.extra["detail"])

    def test_missing_executable_is_error(self):
        self.patch_env()
        with mock.patch.dict(os.environ, {"PATH": self.stub.dir}):
            with self.assertRaises(CrosstalkError):
                HerdrAdapter().candidates()

    def test_available(self):
        self.stub.add("herdr", stdout=load_fixture())
        self.patch_env(HERDR_ENV="1")
        self.assertTrue(HerdrAdapter().available())

    def test_available_even_when_output_has_unknown_status(self):
        # 出力の中身の不備（未知の agent_status）は、herdr に接続できることとは別の問題である
        self.stub.add("herdr", stdout=list_json([agent("sleeping")]))
        self.patch_env(HERDR_ENV="1")
        adapter = HerdrAdapter()
        self.assertTrue(adapter.available())
        with self.assertRaises(CrosstalkError):
            adapter.candidates()

    def test_not_available_without_env(self):
        self.stub.add("herdr", stdout=load_fixture())
        self.patch_env()
        self.assertFalse(HerdrAdapter().available())

    def test_not_available_when_cli_fails(self):
        self.stub.add("herdr", stdout="", exit_code=1)
        self.patch_env(HERDR_ENV="1")
        self.assertFalse(HerdrAdapter().available())

    def test_self_pane_identified(self):
        self.stub.add("herdr", stdout=load_fixture())
        self.patch_env(HERDR_PANE_ID="w2:p1")
        adapter = HerdrAdapter()
        self.assertEqual(adapter.own_pane_id(), "w2:p1")
        flags = [adapter.is_self(c) for c in adapter.candidates()]
        self.assertEqual(flags, [False, True, False, False])

    def test_no_self_without_env(self):
        self.stub.add("herdr", stdout=load_fixture())
        self.patch_env()
        adapter = HerdrAdapter()
        self.assertEqual(adapter.own_pane_id(), "")
        self.assertFalse(any(adapter.is_self(c) for c in adapter.candidates()))


class IsUnlinkedTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="crosstalk-unlinked-")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.repo = os.path.join(self.tmp, "repo")
        self.plain = os.path.join(self.tmp, "plain")
        os.mkdir(self.repo)
        os.mkdir(self.plain)
        subprocess.run(["git", "init", "-q", self.repo], check=True)

    def cand(self, path):
        return Candidate("herdr", "w1:p1", "", path, "", "claude", "idle")

    def test_git_work_tree_is_linked(self):
        self.assertFalse(HerdrAdapter().is_unlinked(self.cand(self.repo)))

    def test_subdirectory_of_work_tree_is_linked(self):
        sub = os.path.join(self.repo, "sub")
        os.mkdir(sub)
        self.assertFalse(HerdrAdapter().is_unlinked(self.cand(sub)))

    def test_plain_directory_is_unlinked(self):
        self.assertTrue(HerdrAdapter().is_unlinked(self.cand(self.plain)))

    def test_missing_path_is_unlinked(self):
        missing = os.path.join(self.tmp, "nope")
        self.assertTrue(HerdrAdapter().is_unlinked(self.cand(missing)))

    def test_git_dir_itself_is_unlinked(self):
        # .git の中は作業ツリーの内側ではない（rev-parse は false を返す）
        gitdir = os.path.join(self.repo, ".git")
        self.assertTrue(HerdrAdapter().is_unlinked(self.cand(gitdir)))

    def test_missing_git_is_error(self):
        empty = os.path.join(self.tmp, "empty-bin")
        os.mkdir(empty)
        with mock.patch.dict(os.environ, {"PATH": empty}):
            with self.assertRaises(CrosstalkError):
                HerdrAdapter().is_unlinked(self.cand(self.repo))

    def test_timeout_is_error(self):
        with mock.patch(
            "crosstalk_lib.adapters.herdr.subprocess.run",
            side_effect=subprocess.TimeoutExpired("git", 10),
        ):
            with self.assertRaises(CrosstalkError):
                HerdrAdapter().is_unlinked(self.cand(self.repo))


class ReplyCommandTest(unittest.TestCase):
    def test_reply_command_uses_own_pane(self):
        with mock.patch.dict(os.environ, {"HERDR_PANE_ID": "w1:p1"}):
            command = HerdrAdapter().reply_command("a1b2c3")
        self.assertEqual(
            command, 'herdr agent prompt w1:p1 "[crosstalk 回答 ID: a1b2c3] <回答>"'
        )

    def test_missing_own_pane_is_error(self):
        env = {k: v for k, v in os.environ.items() if k != "HERDR_PANE_ID"}
        with mock.patch.dict(os.environ, env, clear=True):
            with self.assertRaises(CrosstalkError):
                HerdrAdapter().reply_command("a1b2c3")


class ParsePromptResponseTest(unittest.TestCase):
    def test_agent_prompted_is_confirmed(self):
        result = parse_prompt_response(load_fixture("herdr_prompt_response.json"))
        self.assertTrue(result.confirmed)
        self.assertEqual(result.observed, "agent_prompted")

    def test_other_outputs_are_not_confirmed(self):
        for text in (
            "",
            "not json",
            "null",
            "[]",
            "{}",
            '{"result":{}}',
            '{"result":{"type":"agent_list"}}',
            '{"id":"x","error":{"code":"c","message":"m"}}',
        ):
            with self.subTest(text=text):
                self.assertFalse(parse_prompt_response(text).confirmed)

    def test_fixture_agent_matches_agent_list_item(self):
        prompt = json.loads(load_fixture("herdr_prompt_response.json"))
        listed = json.loads(load_fixture())["result"]["agents"][1]
        self.assertEqual(prompt["result"]["agent"], listed)


class SendTest(unittest.TestCase):
    def setUp(self):
        self.stub = StubCli()
        self.addCleanup(self.stub.cleanup)

    def patch_env(self):
        # 出力を指定しないテストでも、PATH 先頭に stub があるようにする
        if not os.path.exists(os.path.join(self.stub.dir, "herdr")):
            self.stub.add("herdr")
        env = self.stub.env()
        patcher = mock.patch.dict(os.environ, env, clear=True)
        patcher.start()
        self.addCleanup(patcher.stop)
        # 送る前に、PATH 先頭の stub が実際の herdr より先に解決されることを検査する
        resolved = shutil.which("herdr")
        self.assertTrue(resolved and resolved.startswith(self.stub.dir))

    def test_send_runs_prompt_once_with_exact_args(self):
        self.stub.add("herdr", stdout=load_fixture("herdr_prompt_response.json"))
        self.patch_env()
        result = HerdrAdapter().send("w2:p1", "[x] 本文")
        self.assertTrue(result.confirmed)
        self.assertEqual(self.stub.calls(), ["herdr agent prompt w2:p1 [x] 本文"])

    def test_unconfirmed_output_is_a_result_not_an_error(self):
        self.stub.add("herdr", stdout="not json")
        self.patch_env()
        result = HerdrAdapter().send("w2:p1", "x")
        self.assertFalse(result.confirmed)
        self.assertEqual(len(self.stub.calls()), 1)

    def test_nonzero_exit_is_error_without_retry(self):
        self.stub.add("herdr", stdout="out-text", exit_code=1, stderr="err-text")
        self.patch_env()
        with self.assertRaises(CrosstalkError) as ctx:
            HerdrAdapter().send("w2:p1", "[crosstalk 依頼 ID: a1b2c3] 本文の例")
        self.assertIn("再送しない", ctx.exception.reason)
        self.assertIn("out-text", ctx.exception.extra["detail"])
        self.assertIn("err-text", ctx.exception.extra["detail"])
        self.assertEqual(len(self.stub.calls()), 1)

    def test_timeout_is_error_without_retry(self):
        self.patch_env()
        with mock.patch(
            "crosstalk_lib.adapters.herdr.subprocess.run",
            side_effect=subprocess.TimeoutExpired("herdr", 30),
        ) as run:
            with self.assertRaises(CrosstalkError) as ctx:
                HerdrAdapter().send("w2:p1", "x")
        self.assertIn("再送しない", ctx.exception.reason)
        self.assertEqual(run.call_count, 1)
        self.assertEqual(self.stub.calls(), [])

    def test_missing_executable_is_error(self):
        with mock.patch.dict(os.environ, {"PATH": self.stub.dir}):
            with self.assertRaises(CrosstalkError):
                HerdrAdapter().send("w2:p1", "x")

    def test_run_uses_list_args_with_timeout_and_no_shell(self):
        self.patch_env()
        completed = subprocess.CompletedProcess([], 0, stdout="{}", stderr="")
        with mock.patch(
            "crosstalk_lib.adapters.herdr.subprocess.run", return_value=completed
        ) as run:
            HerdrAdapter().send("w2:p1", "a b; c")
        args, kwargs = run.call_args
        self.assertEqual(args[0], ["herdr", "agent", "prompt", "w2:p1", "a b; c"])
        self.assertNotIn("--wait", args[0])
        self.assertGreater(kwargs["timeout"], 0)
        self.assertFalse(kwargs.get("shell", False))


if __name__ == "__main__":
    unittest.main()
