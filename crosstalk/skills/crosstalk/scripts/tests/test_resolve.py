import json
import os
import shutil
import stat
import subprocess
import tempfile

from .stub_cli import StubTestCase

FIXTURE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")


def load_fixture(name):
    with open(os.path.join(FIXTURE_DIR, name)) as f:
        return f.read()


def herdr_list(agents):
    return json.dumps(
        {"id": "cli:agent:list", "result": {"type": "agent_list", "agents": agents}}
    )


def herdr_agent(pane, cwd, kind="claude", status="idle"):
    return {"agent": kind, "agent_status": status, "cwd": cwd, "pane_id": pane}


class ResolveTestBase(StubTestCase):
    def resolve(self, *args, env=None):
        proc = self.run_cli("resolve", *args, env=env)
        return proc, json.loads(proc.stdout)

    def add_orca_router(self, ps, tl):
        path = os.path.join(self.stub.dir, "orca")
        with open(path, "w") as f:
            f.write("#!/bin/sh\n")
            for sub, out in (("worktree", ps), ("terminal", tl)):
                f.write(
                    'if [ "$1" = "%s" ]; then\ncat <<\'STUB_EOF\'\n%s\nSTUB_EOF\nexit 0\nfi\n'
                    % (sub, out)
                )
            f.write("exit 2\n")
        os.chmod(path, os.stat(path).st_mode | stat.S_IXUSR)


class HerdrResolveTest(ResolveTestBase):
    def setUp(self):
        super().setUp()
        self.tmp = tempfile.mkdtemp(prefix="crosstalk-resolve-")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        # 本物の git リポジトリ 2 つ（一時ディレクトリ配下でも除外されないことの確認を兼ねる）と、git でないディレクトリ
        self.alpha = os.path.join(self.tmp, "Alpha-Project")
        self.beta = os.path.join(self.tmp, "beta-project")
        self.plain = os.path.join(self.tmp, "plain-dir")
        for path in (self.alpha, self.beta, self.plain):
            os.mkdir(path)
        for path in (self.alpha, self.beta):
            subprocess.run(["git", "init", "-q", path], check=True)
        agents = [
            herdr_agent("w3:p1", self.beta, "codex"),
            herdr_agent("w2:p1", self.alpha, "codex"),
            herdr_agent("w1:p1", self.alpha, "claude"),
            herdr_agent("w4:p1", self.plain, "claude"),
        ]
        self.stub.add("herdr", stdout=herdr_list(agents))
        self.env = {"HERDR_ENV": "1"}

    def targets(self, data):
        return [c["target"] for c in data["candidates"]]

    def test_unlinked_directory_is_excluded_with_reason(self):
        proc, data = self.resolve("--channel", "herdr", env=self.env)
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["channel"], "herdr")
        self.assertEqual(data["count"], 3)
        self.assertEqual(len(data["excluded"]), 1)
        excluded = data["excluded"][0]
        self.assertEqual(excluded["candidate"]["target"], "w4:p1")
        self.assertTrue(excluded["reason"])

    def test_temp_directory_git_repo_is_not_excluded(self):
        _, data = self.resolve("--channel", "herdr", env=self.env)
        self.assertIn("w1:p1", self.targets(data))

    def test_self_pane_is_excluded(self):
        env = dict(self.env, HERDR_PANE_ID="w1:p1")
        _, data = self.resolve("--channel", "herdr", env=env)
        self.assertNotIn("w1:p1", self.targets(data))
        reasons = {e["candidate"]["target"]: e["reason"] for e in data["excluded"]}
        self.assertIn("w1:p1", reasons)
        self.assertIn("w4:p1", reasons)
        self.assertNotEqual(reasons["w1:p1"], reasons["w4:p1"])

    def test_filtered_out_candidates_are_not_in_excluded(self):
        _, data = self.resolve(
            "--channel", "herdr", "--agent-kind", "codex", env=self.env
        )
        self.assertEqual(data["count"], 2)
        self.assertEqual(
            [e["candidate"]["target"] for e in data["excluded"]], ["w4:p1"]
        )

    def test_repo_matches_working_directory_path(self):
        # herdr は repo を返さないので、作業ディレクトリのパスに部分一致させる。大文字小文字は区別しない
        _, data = self.resolve(
            "--channel", "herdr", "--repo", "alpha-PROJECT", env=self.env
        )
        self.assertEqual(sorted(self.targets(data)), ["w1:p1", "w2:p1"])

    def test_worktree_and_agent_kind_filters_are_anded(self):
        _, data = self.resolve(
            "--channel",
            "herdr",
            "--worktree",
            "alpha",
            "--agent-kind",
            "CODEX",
            env=self.env,
        )
        self.assertEqual(self.targets(data), ["w2:p1"])

    def test_no_match_is_count_zero(self):
        proc, data = self.resolve("--channel", "herdr", "--repo", "zzz", env=self.env)
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(data["count"], 0)
        self.assertEqual(data["candidates"], [])

    def test_sorted_by_repo_worktree_kind_target(self):
        _, data = self.resolve("--channel", "herdr", env=self.env)
        # repo は全て空なので worktree（Alpha < beta）、次に種別、次に target の順
        self.assertEqual(self.targets(data), ["w1:p1", "w2:p1", "w3:p1"])

    def test_output_is_identical_across_runs(self):
        first = self.run_cli("resolve", "--channel", "herdr", env=self.env).stdout
        second = self.run_cli("resolve", "--channel", "herdr", env=self.env).stdout
        self.assertEqual(first, second)

    def test_repo_and_branch_unavailable_and_no_state(self):
        _, data = self.resolve("--channel", "herdr", env=self.env)
        for c in data["candidates"] + [e["candidate"] for e in data["excluded"]]:
            self.assertEqual(c["unavailable"], ["repo", "branch"])
            self.assertNotIn("state", c)


class OrcaResolveTest(ResolveTestBase):
    def setUp(self):
        super().setUp()
        self.add_orca_router(
            load_fixture("orca_worktree_ps.json"),
            load_fixture("orca_terminal_list.json"),
        )

    def test_self_and_tmp_worktree_are_excluded(self):
        _, data = self.resolve(
            "--channel", "orca", env={"ORCA_TERMINAL_HANDLE": "term-0002"}
        )
        self.assertEqual(data["status"], "ok")
        self.assertEqual(
            [c["target"] for c in data["candidates"]], ["term-0001", "term-0003"]
        )
        reasons = {e["candidate"]["target"]: e["reason"] for e in data["excluded"]}
        self.assertEqual(sorted(reasons), ["term-0002", "term-0004"])
        self.assertNotEqual(reasons["term-0002"], reasons["term-0004"])

    def test_repo_filter_uses_repo_field(self):
        _, data = self.resolve("--channel", "orca", "--repo", "REPO-a")
        self.assertEqual(
            [c["target"] for c in data["candidates"]], ["term-0001", "term-0002"]
        )
        _, data = self.resolve("--channel", "orca", "--repo", "repo-b")
        self.assertEqual([c["target"] for c in data["candidates"]], ["term-0003"])

    def test_repo_filter_does_not_match_worktree_path_when_repo_present(self):
        # repo が空でない候補は、repo に対してだけ判定する（パスの "sample-a" には一致しない）
        _, data = self.resolve("--channel", "orca", "--repo", "/work")
        self.assertEqual(data["count"], 0)

    def test_sorted_by_repo_then_worktree(self):
        _, data = self.resolve("--channel", "orca")
        self.assertEqual(
            [c["target"] for c in data["candidates"]],
            ["term-0001", "term-0002", "term-0003"],
        )

    def test_only_branch_is_available_info(self):
        _, data = self.resolve("--channel", "orca")
        for c in data["candidates"]:
            self.assertEqual(c["unavailable"], [])
            self.assertNotIn("state", c)

    def test_output_is_identical_across_runs(self):
        first = self.run_cli("resolve", "--channel", "orca").stdout
        second = self.run_cli("resolve", "--channel", "orca").stdout
        self.assertEqual(first, second)


class ChannelArgumentTest(ResolveTestBase):
    def test_missing_channel_is_error(self):
        proc, data = self.resolve()
        self.assertNotEqual(proc.returncode, 0)
        self.assertEqual(data["status"], "error")

    def test_unsupported_channel_is_error(self):
        proc, data = self.resolve("--channel", "csm")
        self.assertNotEqual(proc.returncode, 0)
        self.assertEqual(data["status"], "error")
