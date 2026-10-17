import json
import time
import types
import unittest
from unittest import mock

from crosstalk_lib import watch
from crosstalk_lib.output import CrosstalkError

from .stub_cli import StubTestCase
from .test_state import StateTestBase, load_fixture


def make_args(**kw):
    base = dict(channel="herdr", target="w1:p1", timeout=None, request_id=None)
    base.update(kw)
    return types.SimpleNamespace(**base)


class WatchTestBase(StateTestBase):
    def watch(self, *args, **env):
        started = time.monotonic()
        proc = self.run_cli("watch", *args, env=env)
        elapsed = time.monotonic() - started
        return proc, json.loads(proc.stdout), elapsed


class HerdrWatchTest(WatchTestBase):
    def test_waits_then_returns_state_of_each_pane(self):
        self.add_herdr()
        cases = (("w1:p1", "working"), ("w2:p1", "idle"), ("w4:p1", "blocked"))
        for target, expected in cases:
            with self.subTest(target=target):
                proc, out, elapsed = self.watch(
                    "--channel", "herdr", "--target", target, "--timeout", "1"
                )
                self.assertEqual(proc.returncode, 0)
                self.assertGreaterEqual(elapsed, 1.0)
                self.assertEqual(out["status"], "ok")
                self.assertTrue(out["timed_out"])
                self.assertEqual(out["waited_seconds"], 1)
                self.assertEqual(out["channel"], "herdr")
                self.assertEqual(out["target"], target)
                self.assertEqual(out["state"], expected)
                self.assertTrue(out["evidence"]["source"])
                self.assertNotIn("request_id", out)

    def test_request_id_is_accepted_and_returned(self):
        self.add_herdr()
        proc, out, _ = self.watch(
            "--channel",
            "herdr",
            "--target",
            "w2:p1",
            "--timeout",
            "1",
            "--request-id",
            "sample-id",
        )
        self.assertEqual(out["status"], "ok")
        self.assertEqual(out["request_id"], "sample-id")

    def test_state_failure_keeps_timed_out_with_unknown(self):
        self.add_herdr(stdout="", exit_code=1)
        proc, out, _ = self.watch(
            "--channel", "herdr", "--target", "w1:p1", "--timeout", "1"
        )
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(out["status"], "ok")
        self.assertTrue(out["timed_out"])
        self.assertEqual(out["state"], "unknown")
        self.assertTrue(out["evidence"]["state_error"])

    def test_missing_target_keeps_timed_out_with_unknown(self):
        self.add_herdr()
        _, out, _ = self.watch(
            "--channel", "herdr", "--target", "w9:p9", "--timeout", "1"
        )
        self.assertEqual(out["status"], "ok")
        self.assertTrue(out["timed_out"])
        self.assertEqual(out["state"], "unknown")
        self.assertIn("state_error", out["evidence"])

    def test_only_reads(self):
        self.add_herdr()
        self.watch("--channel", "herdr", "--target", "w1:p1", "--timeout", "1")
        self.assertEqual(self.stub.calls(), ["herdr agent list"])


class OrcaWatchTest(WatchTestBase):
    def test_returns_state(self):
        self.add_orca_router(read="{}")
        proc, out, elapsed = self.watch(
            "--channel", "orca", "--target", "term-0002", "--timeout", "1"
        )
        self.assertEqual(proc.returncode, 0)
        self.assertGreaterEqual(elapsed, 1.0)
        self.assertEqual(out["status"], "ok")
        self.assertTrue(out["timed_out"])
        self.assertEqual(out["channel"], "orca")
        self.assertEqual(out["state"], "idle")
        self.assertEqual(out["waited_seconds"], 1)

    def test_request_id_is_accepted_and_returned(self):
        self.add_orca_router(read="{}")
        _, out, _ = self.watch(
            "--channel",
            "orca",
            "--target",
            "term-0001",
            "--timeout",
            "1",
            "--request-id",
            "sample-id",
        )
        self.assertEqual(out["status"], "ok")
        self.assertEqual(out["request_id"], "sample-id")
        self.assertEqual(out["state"], "working")

    def test_never_sends_to_terminal(self):
        self.add_orca_router(read=load_fixture("orca_codex_screen_idle.json"))
        self.watch("--channel", "orca", "--target", "term-0003", "--timeout", "1")
        for call in self.stub.calls():
            self.assertNotIn(" send", call)
            self.assertNotIn(" prompt", call)

    def test_state_failure_keeps_timed_out_with_unknown(self):
        self.add_orca_router(read="{}")
        _, out, _ = self.watch(
            "--channel", "orca", "--target", "term-9999", "--timeout", "1"
        )
        self.assertEqual(out["status"], "ok")
        self.assertTrue(out["timed_out"])
        self.assertEqual(out["state"], "unknown")
        self.assertIn("state_error", out["evidence"])


class CsmWatchTest(WatchTestBase):
    def test_waits_without_calling_adapter_or_state(self):
        self.add_herdr()
        self.add_orca_router(read="{}")
        proc, out, elapsed = self.watch(
            "--channel", "csm", "--target", "sample-session", "--timeout", "1"
        )
        self.assertEqual(proc.returncode, 0)
        self.assertGreaterEqual(elapsed, 1.0)
        self.assertEqual(out["status"], "ok")
        self.assertTrue(out["timed_out"])
        self.assertEqual(out["channel"], "csm")
        self.assertEqual(out["target"], "sample-session")
        self.assertEqual(out["waited_seconds"], 1)
        self.assertNotIn("state", out)
        self.assertNotIn("evidence", out)
        self.assertEqual(self.stub.calls(), [])

    def test_request_id_is_error(self):
        proc, out, elapsed = self.watch(
            "--channel", "csm", "--target", "s", "--timeout", "30", "--request-id", "x"
        )
        self.assertEqual(out["status"], "error")
        self.assertNotEqual(proc.returncode, 0)
        self.assertLess(elapsed, 10)


class ValidationTest(WatchTestBase):
    def check_error_fast(self, *args):
        proc, out, elapsed = self.watch(*args)
        self.assertEqual(out["status"], "error")
        self.assertNotEqual(proc.returncode, 0)
        self.assertLess(elapsed, 10)  # 待たずに返る
        self.assertEqual(self.stub.calls(), [])
        return out

    def test_over_max_is_error_without_waiting(self):
        for value in ("601", "100000"):
            with self.subTest(timeout=value):
                self.check_error_fast(
                    "--channel", "csm", "--target", "s", "--timeout", value
                )
        self.check_error_fast(
            "--channel", "herdr", "--target", "w1:p1", "--timeout", "601"
        )

    def test_zero_and_negative_are_error(self):
        for value in ("0", "-1"):
            with self.subTest(timeout=value):
                self.check_error_fast(
                    "--channel", "csm", "--target", "s", "--timeout", value
                )

    def test_non_integer_is_error(self):
        self.check_error_fast("--channel", "csm", "--target", "s", "--timeout", "abc")

    def test_missing_or_empty_target_is_error(self):
        self.check_error_fast("--channel", "herdr", "--timeout", "1")
        self.check_error_fast("--channel", "herdr", "--target", "", "--timeout", "1")

    def test_missing_or_unsupported_channel_is_error(self):
        self.check_error_fast("--target", "t", "--timeout", "1")
        self.check_error_fast("--channel", "other", "--target", "t", "--timeout", "1")


class ValidateFunctionTest(unittest.TestCase):
    def test_default_is_60_seconds(self):
        self.assertEqual(watch.DEFAULT_TIMEOUT, 60)
        _, _, timeout, _ = watch.validate(make_args())
        self.assertEqual(timeout, 60)

    def test_600_is_accepted_and_601_is_rejected(self):
        self.assertEqual(watch.validate(make_args(timeout=600))[2], 600)
        self.assertEqual(watch.validate(make_args(timeout=1))[2], 1)
        for value in (601, 0, -5):
            with self.subTest(timeout=value):
                with self.assertRaises(CrosstalkError):
                    watch.validate(make_args(timeout=value))

    def test_request_id_rules(self):
        for channel in ("herdr", "orca"):
            _, _, _, rid = watch.validate(make_args(channel=channel, request_id="x"))
            self.assertEqual(rid, "x")
        with self.assertRaises(CrosstalkError):
            watch.validate(make_args(channel="csm", request_id="x"))

    def test_run_uses_default_without_actually_waiting(self):
        slept = []
        with mock.patch.object(watch, "_sleep", slept.append):
            out = watch.run(make_args(channel="csm", target="s"))
        self.assertEqual(slept, [60])
        self.assertEqual(out["waited_seconds"], 60)
        self.assertTrue(out["timed_out"])

    def test_run_accepts_600_without_actually_waiting(self):
        slept = []
        with mock.patch.object(watch, "_sleep", slept.append):
            out = watch.run(make_args(channel="csm", target="s", timeout=600))
        self.assertEqual(slept, [600])
        self.assertEqual(out["waited_seconds"], 600)


if __name__ == "__main__":
    unittest.main()
