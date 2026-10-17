import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
from unittest import mock

from .stub_cli import CROSSTALK, StubTestCase

FIXTURE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")

HEX6 = re.compile(r"^[0-9a-f]{6}$")


def load_fixture(name):
    with open(os.path.join(FIXTURE_DIR, name)) as f:
        return f.read()


def herdr_list(agents):
    return json.dumps(
        {"id": "cli:agent:list", "result": {"type": "agent_list", "agents": agents}}
    )


def herdr_agent(pane, cwd, kind="claude", status="idle"):
    return {"agent": kind, "agent_status": status, "cwd": cwd, "pane_id": pane}


def git_env():
    """テストの git が、実行した人の git 設定（署名・hook・テンプレート等）に影響されないようにする。"""
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env["GIT_CONFIG_GLOBAL"] = os.devnull
    env["GIT_CONFIG_NOSYSTEM"] = "1"
    env["GIT_AUTHOR_NAME"] = env["GIT_COMMITTER_NAME"] = "test"
    env["GIT_AUTHOR_EMAIL"] = env["GIT_COMMITTER_EMAIL"] = "test@example.com"
    return env


class ComposeTestBase(StubTestCase):
    def setUp(self):
        super().setUp()
        self.tmp = tempfile.mkdtemp(prefix="crosstalk-compose-")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        # このテストが起動する git（テスト内の git init / commit と、compose の中の git）の設定を隔離する
        patcher = mock.patch.dict(os.environ, git_env(), clear=True)
        patcher.start()
        self.addCleanup(patcher.stop)
        # 送信側の作業ディレクトリとなる git リポジトリ（ブランチ名を持つ）
        self.repo = os.path.join(self.tmp, "sender-repo")
        os.mkdir(self.repo)
        subprocess.run(
            ["git", "init", "-q", "-b", "sender-branch", self.repo], check=True
        )
        # git の作業ツリーでないディレクトリ
        self.plain = os.path.join(self.tmp, "plain-dir")
        os.mkdir(self.plain)

    def compose(self, *args, stdin="本文", env=None, cwd=None):
        proc = subprocess.run(
            [sys.executable, CROSSTALK, "compose"] + list(args),
            input=stdin,
            capture_output=True,
            text=True,
            env=self.stub.env(env),
            cwd=cwd or self.repo,
        )
        return proc, json.loads(proc.stdout)

    def add_orca_router(self, ps, tl):
        path = os.path.join(self.stub.dir, "orca")
        with open(path, "w") as f:
            f.write("#!/bin/sh\n")
            f.write('echo "orca $*" >> "%s"\n' % self.stub.log)
            for sub, out in (("worktree", ps), ("terminal", tl)):
                f.write(
                    'if [ "$1" = "%s" ]; then\ncat <<\'STUB_EOF\'\n%s\nSTUB_EOF\nexit 0\nfi\n'
                    % (sub, out)
                )
            f.write("exit 2\n")
        os.chmod(path, os.stat(path).st_mode | stat.S_IXUSR)


class HerdrComposeTest(ComposeTestBase):
    def setUp(self):
        super().setUp()
        self.stub.add(
            "herdr",
            stdout=herdr_list([herdr_agent("w2:p1", "/work/receiver", "codex")]),
        )
        self.env = {"HERDR_ENV": "1", "HERDR_PANE_ID": "w1:p1"}
        self.args = ("--channel", "herdr", "--target", "w2:p1", "--kind", "ask")

    def test_request_id_is_six_hex_digits(self):
        proc, data = self.compose(*self.args, env=self.env)
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(data["status"], "ok")
        self.assertRegex(data["request_id"], HEX6)

    def test_request_ids_differ_between_calls(self):
        ids = {
            self.compose(*self.args, env=self.env)[1]["request_id"] for _ in range(5)
        }
        self.assertGreater(len(ids), 1)

    def test_header_is_single_line_and_has_all_items(self):
        _, data = self.compose(*self.args, env=self.env)
        header = data["header"]
        self.assertNotRegex(header, r"[\r\n]")
        self.assertIn(data["request_id"], header)
        self.assertIn("sender-repo", header)  # 送信元のリポジトリ
        self.assertIn("sender-branch", header)  # 送信元のブランチ
        self.assertIn("claude", header)  # 送信元の種別
        self.assertIn("/work/receiver", header)  # 宛先の worktree
        self.assertIn("利用者の入力ではありません", header)
        self.assertIn("答え方", header)
        self.assertIn(data["reply_command"], header)
        self.assertTrue(data["text"].startswith(header))

    def test_sender_is_taken_from_git(self):
        _, data = self.compose(*self.args, env=self.env)
        sender = data["sender"]
        self.assertEqual(sender["repo"], "sender-repo")
        self.assertEqual(
            os.path.realpath(sender["worktree"]), os.path.realpath(self.repo)
        )
        self.assertEqual(sender["branch"], "sender-branch")
        self.assertEqual(sender["agent_kind"], "claude")

    def test_destination_repo_is_marked_unavailable(self):
        _, data = self.compose(*self.args, env=self.env)
        self.assertEqual(data["destination"]["repo"], "取得不可")
        self.assertEqual(data["destination"]["worktree"], "/work/receiver")

    def test_reply_command_points_to_own_pane(self):
        _, data = self.compose(*self.args, env=self.env)
        expected = (
            'herdr agent prompt w1:p1 "[crosstalk 回答 ID: %s] <回答>"'
            % data["request_id"]
        )
        self.assertEqual(data["reply_command"], expected)

    def test_answer_guide_has_no_resend_and_no_recheck(self):
        _, data = self.compose(*self.args, env=self.env)
        self.assertIn("再送しないでください", data["header"])
        self.assertNotIn("--retry-request", data["header"])
        self.assertNotIn("再確認", data["header"])

    def test_notify_has_no_reply_command(self):
        args = ("--channel", "herdr", "--target", "w2:p1", "--kind", "notify")
        _, data = self.compose(*args, env=self.env)
        self.assertEqual(data["status"], "ok")
        self.assertIsNone(data["reply_command"])
        self.assertIn("回答不要", data["header"])
        self.assertNotIn("herdr agent prompt", data["header"])
        self.assertIn(data["request_id"], data["header"])

    def test_notify_does_not_need_own_pane(self):
        args = ("--channel", "herdr", "--target", "w2:p1", "--kind", "notify")
        proc, data = self.compose(*args, env={"HERDR_ENV": "1"})
        self.assertEqual(proc.returncode, 0)
        self.assertIsNone(data["reply_command"])

    def test_body_with_quotes_newlines_backslash_japanese(self):
        body = "こんにちは \"quoted\" 'single' $HOME `cmd` \\ back\r\nline2\nline3\rline4\n"
        _, data = self.compose(*self.args, stdin=body, env=self.env)
        self.assertEqual(data["status"], "ok")
        self.assertNotRegex(data["header"], r"[\r\n]")
        self.assertNotRegex(data["text"], r"[\r\n]")
        self.assertTrue(data["text"].startswith(data["header"]))
        self.assertTrue(
            data["text"].endswith(
                "こんにちは \"quoted\" 'single' $HOME `cmd` \\ back line2 line3 line4"
            )
        )

    def test_does_not_send_anything(self):
        self.compose(*self.args, env=self.env)
        self.assertTrue(
            all(call.startswith("herdr agent list") for call in self.stub.calls())
        )

    def test_unknown_target_is_error(self):
        args = ("--channel", "herdr", "--target", "w9:p9", "--kind", "ask")
        proc, data = self.compose(*args, env=self.env)
        self.assertNotEqual(proc.returncode, 0)
        self.assertEqual(data["status"], "error")

    def test_missing_own_pane_is_error_for_ask(self):
        proc, data = self.compose(*self.args, env={"HERDR_ENV": "1"})
        self.assertNotEqual(proc.returncode, 0)
        self.assertEqual(data["status"], "error")
        self.assertIn("HERDR_PANE_ID", data["reason"])

    def test_invalid_kind_is_error(self):
        args = ("--channel", "herdr", "--target", "w2:p1", "--kind", "other")
        proc, data = self.compose(*args, env=self.env)
        self.assertNotEqual(proc.returncode, 0)
        self.assertEqual(data["status"], "error")

    def test_missing_kind_is_error(self):
        proc, data = self.compose(
            "--channel", "herdr", "--target", "w2:p1", env=self.env
        )
        self.assertNotEqual(proc.returncode, 0)
        self.assertEqual(data["status"], "error")

    def test_csm_channel_is_error(self):
        args = ("--channel", "csm", "--target", "x", "--kind", "ask")
        proc, data = self.compose(*args, env=self.env)
        self.assertNotEqual(proc.returncode, 0)
        self.assertEqual(data["status"], "error")

    def test_empty_body_is_error(self):
        for body in ("", "\n", "  \r\n "):
            proc, data = self.compose(*self.args, stdin=body, env=self.env)
            self.assertNotEqual(proc.returncode, 0)
            self.assertEqual(data["status"], "error")

    def test_sender_outside_git_is_marked_unavailable(self):
        proc, data = self.compose(*self.args, env=self.env, cwd=self.plain)
        self.assertEqual(proc.returncode, 0)
        sender = data["sender"]
        for field in ("repo", "worktree", "branch"):
            self.assertEqual(sender[field], "取得不可")
        self.assertIn("リポジトリ=取得不可", data["header"])
        self.assertEqual(sender["agent_kind"], "claude")

    def test_detached_head_branch_is_marked_unavailable(self):
        subprocess.run(
            [
                "git",
                "-C",
                self.repo,
                "-c",
                "user.name=t",
                "-c",
                "user.email=t@example.com",
                "commit",
                "-q",
                "--allow-empty",
                "-m",
                "x",
            ],
            check=True,
        )
        subprocess.run(
            ["git", "-C", self.repo, "checkout", "-q", "--detach"], check=True
        )
        _, data = self.compose(*self.args, env=self.env)
        self.assertEqual(data["sender"]["branch"], "取得不可")
        self.assertEqual(data["sender"]["repo"], "sender-repo")

    def test_sender_repo_name_in_linked_worktree_is_main_repo_name(self):
        subprocess.run(
            [
                "git",
                "-C",
                self.repo,
                "-c",
                "user.name=t",
                "-c",
                "user.email=t@example.com",
                "commit",
                "-q",
                "--allow-empty",
                "-m",
                "x",
            ],
            check=True,
        )
        linked = os.path.join(self.tmp, "linked-wt")
        subprocess.run(
            ["git", "-C", self.repo, "worktree", "add", "-q", "-b", "other", linked],
            check=True,
        )
        _, data = self.compose(*self.args, env=self.env, cwd=linked)
        self.assertEqual(data["sender"]["repo"], "sender-repo")
        self.assertEqual(
            os.path.realpath(data["sender"]["worktree"]), os.path.realpath(linked)
        )
        self.assertEqual(data["sender"]["branch"], "other")


class OrcaComposeTest(ComposeTestBase):
    def setUp(self):
        super().setUp()
        self.add_orca_router(
            ps=load_fixture("orca_worktree_ps.json"),
            tl=load_fixture("orca_terminal_list.json"),
        )
        self.env = {"ORCA_TERMINAL_HANDLE": "term-self"}
        self.args = ("--channel", "orca", "--target", "term-0002", "--kind", "ask")

    def test_header_has_all_items(self):
        _, data = self.compose(*self.args, env=self.env)
        self.assertEqual(data["status"], "ok")
        header = data["header"]
        self.assertNotRegex(header, r"[\r\n]")
        self.assertRegex(data["request_id"], HEX6)
        self.assertIn(data["request_id"], header)
        self.assertIn("sender-repo", header)
        self.assertIn("sample-repo-a", header)  # 宛先のリポジトリ
        self.assertIn("/work/sample-a-wt", header)  # 宛先の worktree
        self.assertIn("利用者の入力ではありません", header)
        self.assertIn(data["reply_command"], header)
        self.assertEqual(data["destination"]["branch"], "feature-two")

    def test_reply_command_points_to_own_terminal(self):
        _, data = self.compose(*self.args, env=self.env)
        expected = (
            'orca terminal send --terminal term-self --text "[crosstalk 回答 ID: %s] <回答>" --enter'
            % data["request_id"]
        )
        self.assertEqual(data["reply_command"], expected)

    def test_answer_guide_has_no_resend_and_recheck_with_retry_id(self):
        _, data = self.compose(*self.args, env=self.env)
        header = data["header"]
        self.assertIn("再送しないでください", header)
        self.assertIn("--retry-request", header)
        # --retry-request の ID は警告が示す通信層の ID で、依頼 ID とは別物であること
        self.assertIn("依頼 ID とは別物", header)
        self.assertIn("1 文字も変えず", header)
        self.assertIn("再送ではありません", header)

    def test_control_characters_in_body_are_replaced_and_counted(self):
        # Ctrl-C・EOF・ESC・DEL・C1 制御文字・Unicode の行区切りは、端末の入力として解釈されうる
        body = "a\x03b\x04c\x1b[201~d\x7fe\u0085f g h\tx"
        _, data = self.compose(*self.args, stdin=body, env=self.env)
        self.assertEqual(data["status"], "ok")
        self.assertNotRegex(data["text"], "[\x00-\x1f\x7f-\x9f  ]")
        self.assertTrue(data["text"].endswith("a b c [201~d e f g h x"))
        self.assertEqual(data["control_chars_replaced"], 8)

    def test_control_characters_in_header_values_are_replaced(self):
        # 送信元の worktree のパスなど、ヘッダに入る外部由来の文字列にも同じ処理をかける
        # （git はブランチ名に制御文字を許さないので、ディレクトリ名に ESC を含めて確かめる）
        subprocess.run(
            ["git", "-C", self.repo, "commit", "-q", "--allow-empty", "-m", "x"],
            check=True,
        )
        linked = os.path.join(self.tmp, "wt\x1b[31mx")
        subprocess.run(
            ["git", "-C", self.repo, "worktree", "add", "-q", "-b", "other", linked],
            check=True,
        )
        _, data = self.compose(*self.args, env=self.env, cwd=linked)
        self.assertEqual(data["status"], "ok")
        self.assertNotRegex(data["text"], "[\x00-\x1f\x7f-\x9f  ]")
        self.assertGreaterEqual(data["control_chars_replaced"], 1)

    def test_no_control_characters_means_zero_replaced(self):
        _, data = self.compose(
            *self.args, stdin='質問 "a" \\ $(x)\nline2', env=self.env
        )
        self.assertEqual(data["control_chars_replaced"], 0)

    def test_answer_guide_warns_about_shell_escaping(self):
        _, data = self.compose(*self.args, env=self.env)
        self.assertIn("エスケープ", data["header"])

    def test_notify_has_no_reply_command(self):
        args = ("--channel", "orca", "--target", "term-0002", "--kind", "notify")
        _, data = self.compose(*args, env={})
        self.assertEqual(data["status"], "ok")
        self.assertIsNone(data["reply_command"])
        self.assertIn("回答不要", data["header"])
        self.assertNotIn("orca terminal send", data["header"])
        self.assertIn(data["request_id"], data["header"])

    def test_body_with_special_characters_keeps_header(self):
        body = "質問 \"a\" 'b' \\ $(x)\nline2\r\nline3"
        _, data = self.compose(*self.args, stdin=body, env=self.env)
        self.assertNotRegex(data["text"], r"[\r\n]")
        self.assertTrue(data["text"].endswith("質問 \"a\" 'b' \\ $(x) line2 line3"))

    def test_unknown_target_is_error(self):
        args = ("--channel", "orca", "--target", "term-9999", "--kind", "ask")
        proc, data = self.compose(*args, env=self.env)
        self.assertNotEqual(proc.returncode, 0)
        self.assertEqual(data["status"], "error")

    def test_missing_own_terminal_is_error_for_ask(self):
        proc, data = self.compose(*self.args, env={})
        self.assertNotEqual(proc.returncode, 0)
        self.assertEqual(data["status"], "error")
        self.assertIn("ORCA_TERMINAL_HANDLE", data["reason"])

    def test_does_not_send_anything(self):
        self.compose(*self.args, env=self.env)
        self.assertFalse(
            any(c.startswith("orca terminal send") for c in self.stub.calls())
        )
