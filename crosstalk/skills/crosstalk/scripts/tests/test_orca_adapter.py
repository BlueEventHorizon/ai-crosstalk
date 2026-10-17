import copy
import json
import os
import shutil
import unittest
from unittest import mock

from crosstalk_lib.adapters.base import STATE_IDLE, STATE_UNKNOWN, STATE_WORKING
from crosstalk_lib.adapters.orca import (
    OrcaAdapter,
    build_candidates,
    judge_claude_state,
    judge_codex_screen,
    parse_send_response,
    parse_status,
    parse_terminals,
    parse_worktrees,
)
from crosstalk_lib.output import CrosstalkError

from .stub_cli import StubCli, anonymity_problems

FIXTURE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")
SCREEN_FIXTURES = (
    "orca_codex_screen_idle.json",
    "orca_codex_screen_draft.json",
    "orca_codex_screen_other.json",
)
FIXTURE_NAMES = (
    "orca_status.json",
    "orca_worktree_ps.json",
    "orca_terminal_list.json",
) + SCREEN_FIXTURES


def load_fixture(name):
    with open(os.path.join(FIXTURE_DIR, name)) as f:
        return f.read()


def ps_text():
    return load_fixture("orca_worktree_ps.json")


def tl_text():
    return load_fixture("orca_terminal_list.json")


def ps_with(mutate):
    data = json.loads(ps_text())
    mutate(data["result"]["worktrees"])
    return json.dumps(data)


def tl_with(mutate):
    data = json.loads(tl_text())
    mutate(data["result"]["terminals"])
    return json.dumps(data)


class BuildCandidatesTest(unittest.TestCase):
    def setUp(self):
        self.cands, self.details = build_candidates(ps_text(), tl_text())
        self.by_target = {c.target: c for c in self.cands}

    def test_only_terminals_with_agents_are_candidates(self):
        self.assertEqual(
            [c.target for c in self.cands],
            ["term-0001", "term-0002", "term-0003", "term-0004"],
        )

    def test_fields_match_fixture(self):
        first = self.by_target["term-0001"]
        self.assertEqual(first.channel, "orca")
        self.assertEqual(first.repo, "sample-repo-a")
        self.assertEqual(first.worktree, "/work/sample-a")
        self.assertEqual(first.branch, "feature-one")
        self.assertEqual(first.agent_kind, "claude")
        self.assertEqual(self.by_target["term-0002"].branch, "feature-two")
        self.assertEqual(self.by_target["term-0002"].worktree, "/work/sample-a-wt")

    def test_codex_without_agent_record_is_a_candidate(self):
        c = self.by_target["term-0003"]
        self.assertEqual(c.agent_kind, "codex")
        self.assertEqual(c.repo, "sample-repo-b")
        self.assertEqual(c.branch, "main")

    def test_state_is_not_decided(self):
        for c in self.cands:
            self.assertEqual(c.state, STATE_UNKNOWN)

    def test_detached_branch_is_empty(self):
        self.assertEqual(self.by_target["term-0004"].branch, "")

    def test_unlinked_worktree_identified(self):
        flags = {t: d["unlinked"] for t, d in self.details.items()}
        self.assertEqual(
            flags,
            {
                "term-0001": False,
                "term-0002": False,
                "term-0003": False,
                "term-0004": True,
            },
        )

    def test_unlinked_candidate_is_kept_not_dropped(self):
        self.assertIn("term-0004", self.by_target)

    def test_pane_key_kept(self):
        self.assertEqual(self.details["term-0001"]["pane_key"], "tab-1:leaf-1")

    def test_unlinked_by_missing_repo_link(self):
        for field in ("repo", "repoId"):
            with self.subTest(field=field):

                def mutate(rows):
                    rows[0][field] = ""

                _, details = build_candidates(ps_with(mutate), tl_text())
                self.assertTrue(details["term-0001"]["unlinked"])

    def test_unlinked_by_empty_project_id(self):
        def mutate(rows):
            rows[0]["projectId"] = ""

        _, details = build_candidates(ps_with(mutate), tl_text())
        self.assertTrue(details["term-0001"]["unlinked"])

    def test_missing_project_id_field_is_not_unlinked(self):
        self.assertNotIn("projectId", json.loads(ps_text())["result"]["worktrees"][0])
        self.assertFalse(self.details["term-0001"]["unlinked"])

    def test_unlinked_by_non_git_kind(self):
        def mutate(rows):
            rows[0]["workspaceKind"] = "folder"

        _, details = build_candidates(ps_with(mutate), tl_text())
        self.assertTrue(details["term-0001"]["unlinked"])

    def test_unlinked_by_temp_path_even_with_repo_id(self):
        for prefix in (
            "/tmp/x",
            "/private/tmp/x",
            "/var/folders/ab/x",
            "/private/var/folders/ab/x",
        ):
            with self.subTest(prefix=prefix):

                def mutate(rows):
                    rows[0]["path"] = prefix

                _, details = build_candidates(ps_with(mutate), tl_text())
                self.assertTrue(details["term-0001"]["unlinked"])

    def test_path_merely_containing_tmp_is_not_unlinked(self):
        def mutate(rows):
            rows[0]["path"] = "/work/tmp/x"

        _, details = build_candidates(ps_with(mutate), tl_text())
        self.assertFalse(details["term-0001"]["unlinked"])


class ErrorTest(unittest.TestCase):
    def test_broken_json_is_error(self):
        for text in ("", "{not json", "null", '"x"', "[]"):
            with self.subTest(text=text):
                with self.assertRaises(CrosstalkError):
                    parse_worktrees(text)
                with self.assertRaises(CrosstalkError):
                    parse_terminals(text)
                with self.assertRaises(CrosstalkError):
                    parse_status(text)

    def test_unexpected_structure_is_error(self):
        for text in (
            '{"ok":true}',
            '{"ok":true,"result":{}}',
            '{"ok":true,"result":{"worktrees":"x"}}',
            '{"ok":false,"error":{"code":"x"}}',
        ):
            with self.subTest(text=text):
                with self.assertRaises(CrosstalkError):
                    parse_worktrees(text)
                with self.assertRaises(CrosstalkError):
                    parse_terminals(text)

    def test_truncated_is_error(self):
        data = json.loads(ps_text())
        data["result"]["truncated"] = True
        with self.assertRaises(CrosstalkError):
            parse_worktrees(json.dumps(data))
        data = json.loads(tl_text())
        data["result"]["truncated"] = True
        with self.assertRaises(CrosstalkError):
            parse_terminals(json.dumps(data))

    def test_missing_worktree_field_is_error(self):
        for field in (
            "worktreeId",
            "repo",
            "repoId",
            "path",
            "branch",
            "workspaceKind",
            "agents",
        ):
            with self.subTest(field=field):

                def mutate(rows):
                    del rows[0][field]

                with self.assertRaises(CrosstalkError):
                    parse_worktrees(ps_with(mutate))

    def test_missing_terminal_field_is_error(self):
        for field in ("handle", "worktreeId", "tabId", "leafId"):
            with self.subTest(field=field):

                def mutate(rows):
                    del rows[0][field]

                with self.assertRaises(CrosstalkError):
                    parse_terminals(tl_with(mutate))

    def test_non_object_items_are_error(self):
        with self.assertRaises(CrosstalkError):
            parse_worktrees(ps_with(lambda rows: rows.append("x")))
        with self.assertRaises(CrosstalkError):
            parse_terminals(tl_with(lambda terminals: terminals.append("x")))

    def test_bad_agent_identity_is_error(self):
        def mutate(rows):
            rows[0]["agentIdentity"] = 7

        with self.assertRaises(CrosstalkError):
            parse_terminals(tl_with(mutate))

    def test_terminal_without_worktree_is_error(self):
        def mutate(rows):
            del rows[0]

        with self.assertRaises(CrosstalkError):
            build_candidates(ps_with(mutate), tl_text())

    def test_duplicate_worktree_is_error(self):
        def mutate(rows):
            rows.append(copy.deepcopy(rows[0]))

        with self.assertRaises(CrosstalkError):
            parse_worktrees(ps_with(mutate))

    def test_agent_kind_mismatch_is_error(self):
        def mutate(rows):
            rows[0]["agents"][0]["agentType"] = "codex"

        with self.assertRaises(CrosstalkError):
            build_candidates(ps_with(mutate), tl_text())

    def test_status_without_reachable_is_error(self):
        with self.assertRaises(CrosstalkError):
            parse_status('{"ok":true,"result":{"runtime":{}}}')
        with self.assertRaises(CrosstalkError):
            parse_status('{"ok":true,"result":{}}')


class StatusTest(unittest.TestCase):
    def test_fixture_is_reachable(self):
        self.assertTrue(parse_status(load_fixture("orca_status.json")))

    def test_unreachable(self):
        data = json.loads(load_fixture("orca_status.json"))
        data["result"]["runtime"]["reachable"] = False
        self.assertFalse(parse_status(json.dumps(data)))


class FixtureTest(unittest.TestCase):
    def test_fixtures_are_anonymous(self):
        for name in FIXTURE_NAMES + ("orca_send_response.json",):
            with self.subTest(fixture=name):
                self.assertEqual(anonymity_problems(load_fixture(name)), [])


class AdapterBase(unittest.TestCase):
    def setUp(self):
        self.stub = StubCli()
        self.addCleanup(self.stub.cleanup)

    def patch_env(self, **extra):
        env = self.stub.env(extra)
        for key in ("ORCA_TERMINAL_HANDLE",):
            if key not in extra:
                env.pop(key, None)
        patcher = mock.patch.dict(os.environ, env, clear=True)
        patcher.start()
        self.addCleanup(patcher.stop)

    def add_orca(self, stdout="", exit_code=0, stderr=""):
        self.stub.add("orca", stdout=stdout, exit_code=exit_code, stderr=stderr)

    def add_orca_router(self, status=None, ps=None, tl=None, exit_code=0, read=None):
        """サブコマンドごとに出力を変える stub。read は terminal read の出力。"""
        import stat

        path = os.path.join(self.stub.dir, "orca")
        outputs = {"status": status, "worktree": ps, "terminal": tl}
        with open(path, "w") as f:
            f.write("#!/bin/sh\n")
            f.write('echo "orca $*" >> "%s"\n' % self.stub.log)
            if read is not None:
                f.write(
                    'if [ "$1" = "terminal" ] && [ "$2" = "read" ]; then\ncat <<\'STUB_EOF\'\n%s\nSTUB_EOF\nexit 0\nfi\n'
                    % read
                )
            for sub, out in outputs.items():
                if out is None:
                    continue
                f.write(
                    'if [ "$1" = "%s" ]; then\ncat <<\'STUB_EOF\'\n%s\nSTUB_EOF\nexit %d\nfi\n'
                    % (sub, out, exit_code)
                )
            f.write("exit 2\n")
        os.chmod(path, os.stat(path).st_mode | stat.S_IXUSR)


class AdapterTest(AdapterBase):
    def test_available_with_env_and_reachable(self):
        self.add_orca(stdout=load_fixture("orca_status.json"))
        self.patch_env(ORCA_TERMINAL_HANDLE="term-0001")
        self.assertTrue(OrcaAdapter().available())
        self.assertEqual(self.stub.calls(), ["orca status --json"])

    def test_not_available_without_env(self):
        self.add_orca(stdout=load_fixture("orca_status.json"))
        self.patch_env()
        self.assertFalse(OrcaAdapter().available())
        self.assertEqual(self.stub.calls(), [])

    def test_not_available_when_unreachable(self):
        data = json.loads(load_fixture("orca_status.json"))
        data["result"]["runtime"]["reachable"] = False
        self.add_orca(stdout=json.dumps(data))
        self.patch_env(ORCA_TERMINAL_HANDLE="term-0001")
        self.assertFalse(OrcaAdapter().available())

    def test_not_available_when_status_fails(self):
        self.add_orca(stdout="", exit_code=1)
        self.patch_env(ORCA_TERMINAL_HANDLE="term-0001")
        self.assertFalse(OrcaAdapter().available())

    def test_not_available_when_status_is_broken(self):
        self.add_orca(stdout="{not json")
        self.patch_env(ORCA_TERMINAL_HANDLE="term-0001")
        self.assertFalse(OrcaAdapter().available())

    def test_not_available_without_executable(self):
        self.patch_env(ORCA_TERMINAL_HANDLE="term-0001")
        with mock.patch.dict(os.environ, {"PATH": self.stub.dir}):
            self.assertFalse(OrcaAdapter().available())

    def test_candidates_calls_both_commands(self):
        self.add_orca_router(ps=ps_text(), tl=tl_text())
        self.patch_env()
        cands = OrcaAdapter().candidates()
        self.assertEqual(len(cands), 4)
        self.assertEqual(
            self.stub.calls(), ["orca worktree ps --json", "orca terminal list --json"]
        )

    def test_command_failure_is_error_with_stdout_and_stderr(self):
        self.add_orca(stdout="out-text", exit_code=1, stderr="err-text")
        self.patch_env()
        with self.assertRaises(CrosstalkError) as ctx:
            OrcaAdapter().candidates()
        self.assertIn("out-text", ctx.exception.extra["detail"])
        self.assertIn("err-text", ctx.exception.extra["detail"])

    def test_broken_output_is_error(self):
        self.add_orca_router(ps="{not json", tl=tl_text())
        self.patch_env()
        with self.assertRaises(CrosstalkError):
            OrcaAdapter().candidates()

    def test_missing_executable_is_error(self):
        self.patch_env()
        with mock.patch.dict(os.environ, {"PATH": self.stub.dir}):
            with self.assertRaises(CrosstalkError):
                OrcaAdapter().candidates()

    def test_self_terminal_identified(self):
        self.add_orca_router(ps=ps_text(), tl=tl_text())
        self.patch_env(ORCA_TERMINAL_HANDLE="term-0002")
        adapter = OrcaAdapter()
        self.assertEqual(adapter.own_terminal_handle(), "term-0002")
        flags = [adapter.is_self(c) for c in adapter.candidates()]
        self.assertEqual(flags, [False, True, False, False])

    def test_no_self_without_env(self):
        self.add_orca_router(ps=ps_text(), tl=tl_text())
        self.patch_env()
        adapter = OrcaAdapter()
        self.assertEqual(adapter.own_terminal_handle(), "")
        self.assertFalse(any(adapter.is_self(c) for c in adapter.candidates()))

    def test_unlinked_identified_through_adapter(self):
        self.add_orca_router(ps=ps_text(), tl=tl_text())
        self.patch_env()
        adapter = OrcaAdapter()
        flags = [adapter.is_unlinked(c) for c in adapter.candidates()]
        self.assertEqual(flags, [False, False, False, True])

    def test_is_unlinked_before_candidates_is_error(self):
        cands, _ = build_candidates(ps_text(), tl_text())
        with self.assertRaises(CrosstalkError):
            OrcaAdapter().is_unlinked(cands[0])

    def test_pane_key_through_adapter(self):
        self.add_orca_router(ps=ps_text(), tl=tl_text())
        self.patch_env()
        adapter = OrcaAdapter()
        cands = adapter.candidates()
        self.assertEqual(adapter.pane_key(cands[1]), "tab-2:leaf-2")


class JudgeClaudeTest(unittest.TestCase):
    def test_done_is_idle(self):
        state, evidence = judge_claude_state("done")
        self.assertEqual(state, STATE_IDLE)
        self.assertEqual(evidence["observed"], "done")

    def test_working_is_working(self):
        self.assertEqual(judge_claude_state("working")[0], STATE_WORKING)

    def test_unconfirmed_value_is_unknown_with_value_in_evidence(self):
        state, evidence = judge_claude_state("sample-other")
        self.assertEqual(state, STATE_UNKNOWN)
        self.assertIn("sample-other", evidence["observed"])

    def test_missing_record_is_unknown(self):
        self.assertEqual(judge_claude_state(None)[0], STATE_UNKNOWN)


class JudgeCodexScreenTest(unittest.TestCase):
    def test_empty_prompt_is_idle(self):
        state, evidence = judge_codex_screen(
            load_fixture("orca_codex_screen_idle.json")
        )
        self.assertEqual(state, STATE_IDLE)
        self.assertIn("orca terminal read", evidence["source"])
        self.assertTrue(evidence["observed"])

    def test_draft_in_prompt_is_unknown(self):
        self.assertEqual(
            judge_codex_screen(load_fixture("orca_codex_screen_draft.json"))[0],
            STATE_UNKNOWN,
        )

    def test_draft_starting_with_placeholder_words_is_unknown(self):
        # 入力途中の文がプレースホルダと同じ語で始まっていても、idle にしない
        data = json.loads(load_fixture("orca_codex_screen_idle.json"))
        data["result"]["terminal"]["tail"][-3] = "› Ask Codex to do anything else"
        self.assertEqual(judge_codex_screen(json.dumps(data))[0], STATE_UNKNOWN)

    def test_unrecognized_screen_is_unknown_never_working(self):
        # 処理中の表示は実機で未確認のため、working は返さない
        state, evidence = judge_codex_screen(
            load_fixture("orca_codex_screen_other.json")
        )
        self.assertEqual(state, STATE_UNKNOWN)
        self.assertTrue(evidence["observed"])

    def test_broken_or_unexpected_output_is_unknown(self):
        data = json.loads(load_fixture("orca_codex_screen_idle.json"))
        not_screen = copy.deepcopy(data)
        not_screen["result"]["terminal"]["source"] = "screen-unavailable"
        not_ok = copy.deepcopy(data)
        not_ok["ok"] = False
        empty_tail = copy.deepcopy(data)
        empty_tail["result"]["terminal"]["tail"] = []
        short_tail = copy.deepcopy(data)
        short_tail["result"]["terminal"]["tail"] = ["x", "y"]
        bad_tail = copy.deepcopy(data)
        bad_tail["result"]["terminal"]["tail"] = "x"
        for text in (
            "",
            "{not json",
            "null",
            "[]",
            "{}",
            json.dumps(not_screen),
            json.dumps(not_ok),
            json.dumps(empty_tail),
            json.dumps(short_tail),
            json.dumps(bad_tail),
        ):
            with self.subTest(text=text[:30]):
                self.assertEqual(judge_codex_screen(text)[0], STATE_UNKNOWN)

    def test_blank_trailing_lines_are_ignored(self):
        data = json.loads(load_fixture("orca_codex_screen_idle.json"))
        data["result"]["terminal"]["tail"] += ["", "   "]
        self.assertEqual(judge_codex_screen(json.dumps(data))[0], STATE_IDLE)

    def test_idle_requires_shortcuts_hint(self):
        data = json.loads(load_fixture("orca_codex_screen_idle.json"))
        data["result"]["terminal"]["tail"][-1] = "  sample hint only"
        self.assertEqual(judge_codex_screen(json.dumps(data))[0], STATE_UNKNOWN)


class ReceiverStateTest(AdapterBase):
    def adapter_with_screen(self, screen_name=None, screen_text=None):
        text = screen_text if screen_text is not None else load_fixture(screen_name)
        self.add_orca_router(ps=ps_text(), tl=tl_text(), read=text)
        self.patch_env()
        return OrcaAdapter()

    def test_claude_done_is_idle(self):
        adapter = self.adapter_with_screen("orca_codex_screen_idle.json")
        state, evidence = adapter.receiver_state_with_evidence("term-0002")
        self.assertEqual(state, STATE_IDLE)
        self.assertEqual(evidence["observed"], "done")
        self.assertIn("agents[].state", evidence["source"])

    def test_claude_working_is_working(self):
        adapter = self.adapter_with_screen("orca_codex_screen_idle.json")
        self.assertEqual(adapter.receiver_state("term-0001"), STATE_WORKING)

    def test_claude_does_not_read_terminal(self):
        adapter = self.adapter_with_screen("orca_codex_screen_idle.json")
        adapter.receiver_state("term-0001")
        self.assertFalse(
            any(c.startswith("orca terminal read") for c in self.stub.calls())
        )

    def test_claude_matched_by_pane_key_not_by_position(self):
        # term-0001 の記録だけ done にして、term-0002 の記録と取り違えないことを確かめる
        def mutate(rows):
            rows[0]["agents"][0]["state"] = "done"
            rows[1]["agents"][0]["state"] = "working"

        self.add_orca_router(ps=ps_with(mutate), tl=tl_text(), read="{}")
        self.patch_env()
        adapter = OrcaAdapter()
        self.assertEqual(adapter.receiver_state("term-0001"), STATE_IDLE)
        self.assertEqual(adapter.receiver_state("term-0002"), STATE_WORKING)

    def test_claude_without_record_is_unknown(self):
        def mutate(rows):
            rows[0]["agents"] = []

        self.add_orca_router(ps=ps_with(mutate), tl=tl_text(), read="{}")
        self.patch_env()
        self.assertEqual(OrcaAdapter().receiver_state("term-0001"), STATE_UNKNOWN)

    def test_claude_unconfirmed_state_value_is_unknown(self):
        def mutate(rows):
            rows[0]["agents"][0]["state"] = "sample-other"

        self.add_orca_router(ps=ps_with(mutate), tl=tl_text(), read="{}")
        self.patch_env()
        self.assertEqual(OrcaAdapter().receiver_state("term-0001"), STATE_UNKNOWN)

    def test_codex_idle_screen_is_idle_and_read_is_read_only_call(self):
        adapter = self.adapter_with_screen("orca_codex_screen_idle.json")
        state, evidence = adapter.receiver_state_with_evidence("term-0003")
        self.assertEqual(state, STATE_IDLE)
        self.assertIn("screen", evidence["source"])
        reads = [c for c in self.stub.calls() if c.startswith("orca terminal")]
        self.assertIn("orca terminal read --terminal term-0003 --screen --json", reads)
        self.assertFalse(any(" send" in c or " prompt" in c for c in self.stub.calls()))

    def test_codex_unrecognized_screens_are_unknown(self):
        for name in ("orca_codex_screen_draft.json", "orca_codex_screen_other.json"):
            with self.subTest(fixture=name):
                adapter = self.adapter_with_screen(name)
                self.assertEqual(adapter.receiver_state("term-0003"), STATE_UNKNOWN)

    def test_codex_read_failure_is_error_with_stdout_and_stderr(self):
        import stat

        self.add_orca_router(ps=ps_text(), tl=tl_text())
        path = os.path.join(self.stub.dir, "orca")
        with open(path) as f:
            body = f.read()
        with open(path, "w") as f:
            f.write(
                "#!/bin/sh\n"
                'if [ "$1" = "terminal" ] && [ "$2" = "read" ]; then echo out-text; echo err-text >&2; exit 1; fi\n'
                + body.split("\n", 1)[1]
            )
        os.chmod(path, os.stat(path).st_mode | stat.S_IXUSR)
        self.patch_env()
        with self.assertRaises(CrosstalkError) as ctx:
            OrcaAdapter().receiver_state("term-0003")
        self.assertIn("out-text", ctx.exception.extra["detail"])
        self.assertIn("err-text", ctx.exception.extra["detail"])

    def test_unknown_target_is_error(self):
        adapter = self.adapter_with_screen("orca_codex_screen_idle.json")
        with self.assertRaises(CrosstalkError):
            adapter.receiver_state("term-9999")

    def test_other_agent_kind_is_unknown(self):
        def mutate(terminals):
            terminals[2]["agentIdentity"] = "sample-agent"

        self.add_orca_router(ps=ps_text(), tl=tl_with(mutate), read="{}")
        self.patch_env()
        self.assertEqual(OrcaAdapter().receiver_state("term-0003"), STATE_UNKNOWN)


class ReplyCommandTest(AdapterBase):
    def test_reply_command_uses_own_terminal(self):
        self.patch_env(ORCA_TERMINAL_HANDLE="term-self")
        self.assertEqual(
            OrcaAdapter().reply_command("a1b2c3"),
            'orca terminal send --terminal term-self --text "[crosstalk 回答 ID: a1b2c3] <回答>" --enter',
        )

    def test_missing_own_terminal_is_error(self):
        self.patch_env()
        with self.assertRaises(CrosstalkError):
            OrcaAdapter().reply_command("a1b2c3")


# 実機（Orca 1.4.221）で確認した応答の形（tests/fixtures/orca_send_response.json。値は匿名）に基づく。
# 受領ありは、ok が true・result.send.accepted が true・result.send.prompt.stages に turn_started がある形だけ。
def _send_response(mutate=None):
    data = json.loads(load_fixture("orca_send_response.json"))
    if mutate:
        mutate(data)
    return data


def _set(path, value):
    def mutate(data):
        node = data
        for key in path[:-1]:
            node = node[key]
        node[path[-1]] = value

    return mutate


SEND_WITH_TURN_STARTED = (_send_response(),)
SEND_WITHOUT_TURN_STARTED = (
    # ターンの開始を観測できなかった形（--wait-submit の時間内に input_accepted だけ）
    _send_response(_set(["result", "send", "prompt", "stages"], ["input_accepted"])),
    _send_response(_set(["result", "send", "prompt", "stages"], [])),
    # 受理されていない・失敗
    _send_response(_set(["result", "send", "accepted"], False)),
    _send_response(_set(["ok"], False)),
    # 形が違う（stages が配列でない、段階が別の場所にしか無い、必要なキーが無い）
    _send_response(_set(["result", "send", "prompt", "stages"], "turn_started")),
    _send_response(
        _set(["result", "send", "prompt", "stages"], {"turn_started": True})
    ),
    _send_response(
        _set(
            ["result", "send", "prompt", "stages"],
            [{"name": "turn_started", "status": "timeout"}],
        )
    ),
    _send_response(lambda d: d["result"]["send"]["prompt"].pop("stages")),
    _send_response(lambda d: d["result"]["send"].pop("prompt")),
    _send_response(lambda d: d["result"].pop("send")),
    # turn_started が、送信結果とは別の場所（期待値・未達・保留など）にだけ現れる形
    _send_response(
        lambda d: (
            d["result"]["send"]["prompt"].update({"stages": ["input_accepted"]}),
            d.update(
                {
                    "pending": ["turn_started"],
                    "expected": ["input_accepted", "turn_started"],
                }
            ),
        )
    ),
    {"ok": True, "result": {}},
    {"result": {"send": {"accepted": True, "prompt": {"stages": ["turn_started"]}}}},
    ["turn_started"],
)


class ParseSendResponseTest(unittest.TestCase):
    def test_real_shape_with_turn_started_is_confirmed(self):
        for data in SEND_WITH_TURN_STARTED:
            with self.subTest(data=data):
                result = parse_send_response(json.dumps(data))
                self.assertTrue(result.confirmed)
                self.assertEqual(result.observed, "turn_started")

    def test_fixture_file_is_confirmed(self):
        self.assertTrue(
            parse_send_response(load_fixture("orca_send_response.json")).confirmed
        )

    def test_without_turn_started_is_not_confirmed(self):
        for data in SEND_WITHOUT_TURN_STARTED:
            with self.subTest(data=data):
                self.assertFalse(parse_send_response(json.dumps(data)).confirmed)

    def test_broken_output_is_not_confirmed(self):
        for text in ("", "not json", "null", '"turn_started"'):
            with self.subTest(text=text):
                self.assertFalse(parse_send_response(text).confirmed)


class SendTest(AdapterBase):
    def patch_env_checked(self):
        # 出力を指定しないテストでも、PATH 先頭に stub があるようにする
        if not os.path.exists(os.path.join(self.stub.dir, "orca")):
            self.add_orca()
        self.patch_env()
        # 送る前に、PATH 先頭の stub が実際の orca より先に解決されることを検査する
        resolved = shutil.which("orca")
        self.assertTrue(resolved and resolved.startswith(self.stub.dir))

    def test_send_runs_terminal_send_once_with_exact_args(self):
        self.add_orca(stdout=json.dumps(SEND_WITH_TURN_STARTED[0]))
        self.patch_env_checked()
        result = OrcaAdapter().send("term-0003", "[x] 本文")
        self.assertTrue(result.confirmed)
        self.assertEqual(
            self.stub.calls(),
            [
                "orca terminal send --terminal term-0003 --text [x] 本文"
                " --enter --wait-submit 10 --json"
            ],
        )

    def test_unconfirmed_output_is_a_result_not_an_error(self):
        self.add_orca(stdout=json.dumps(SEND_WITHOUT_TURN_STARTED[0]))
        self.patch_env_checked()
        result = OrcaAdapter().send("term-0003", "x")
        self.assertFalse(result.confirmed)
        self.assertEqual(len(self.stub.calls()), 1)

    def test_nonzero_exit_is_error_without_retry(self):
        self.add_orca(stdout="out-text", exit_code=1, stderr="err-text")
        self.patch_env_checked()
        with self.assertRaises(CrosstalkError) as ctx:
            OrcaAdapter().send("term-0003", "[crosstalk 依頼 ID: a1b2c3] 本文の例")
        self.assertIn("再送しない", ctx.exception.reason)
        self.assertIn("out-text", ctx.exception.extra["detail"])
        self.assertIn("err-text", ctx.exception.extra["detail"])
        self.assertEqual(len(self.stub.calls()), 1)

    def test_timeout_is_error_without_retry(self):
        import subprocess

        self.patch_env_checked()
        with mock.patch(
            "crosstalk_lib.adapters.orca.subprocess.run",
            side_effect=subprocess.TimeoutExpired("orca", 30),
        ) as run:
            with self.assertRaises(CrosstalkError) as ctx:
                OrcaAdapter().send("term-0003", "x")
        self.assertIn("再送しない", ctx.exception.reason)
        self.assertEqual(run.call_count, 1)
        self.assertEqual(self.stub.calls(), [])

    def test_missing_executable_is_error(self):
        self.patch_env()
        with mock.patch.dict(os.environ, {"PATH": self.stub.dir}):
            with self.assertRaises(CrosstalkError):
                OrcaAdapter().send("term-0003", "x")

    def test_run_uses_list_args_with_timeout_longer_than_wait_submit(self):
        import subprocess

        self.patch_env_checked()
        completed = subprocess.CompletedProcess([], 0, stdout="{}", stderr="")
        with mock.patch(
            "crosstalk_lib.adapters.orca.subprocess.run", return_value=completed
        ) as run:
            OrcaAdapter().send("term-0003", "a b; c")
        args, kwargs = run.call_args
        self.assertEqual(
            args[0],
            [
                "orca",
                "terminal",
                "send",
                "--terminal",
                "term-0003",
                "--text",
                "a b; c",
                "--enter",
                "--wait-submit",
                "10",
                "--json",
            ],
        )
        self.assertGreater(kwargs["timeout"], 10)
        self.assertFalse(kwargs.get("shell", False))


if __name__ == "__main__":
    unittest.main()
