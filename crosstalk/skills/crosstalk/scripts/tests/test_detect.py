import json
import os
import unittest

from .stub_cli import StubTestCase

FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")


def fixture(name):
    with open(os.path.join(FIXTURES, name)) as f:
        return f.read().strip()


class DetectTest(StubTestCase):
    def detect(self, env):
        proc = self.run_cli("detect", env=env)
        self.assertEqual(proc.returncode, 0, proc.stdout)
        out = json.loads(proc.stdout)
        self.assertEqual(out["status"], "ok")
        return out

    def herdr_ok(self):
        self.stub.add("herdr", stdout=fixture("herdr_agent_list.json"))

    def orca_ok(self):
        self.stub.add("orca", stdout=fixture("orca_status.json"))

    def evidence(self, data, channel):
        return [e for e in data["evidence"] if e["channel"] == channel]

    def test_herdr_enabled(self):
        self.herdr_ok()
        data = self.detect({"HERDR_ENV": "1"})
        self.assertEqual(data["channel"], "herdr")

    def test_orca_enabled(self):
        self.orca_ok()
        data = self.detect({"ORCA_TERMINAL_HANDLE": "h"})
        self.assertEqual(data["channel"], "orca")

    def test_none_without_env(self):
        data = self.detect({})
        self.assertEqual(data["channel"], "none")
        self.assertEqual(len(data["evidence"]), 2)
        self.assertEqual(self.stub.calls(), [])

    def test_herdr_env_but_unreachable(self):
        self.stub.add("herdr", exit_code=1, stderr="fail")
        data = self.detect({"HERDR_ENV": "1"})
        self.assertEqual(data["channel"], "none")
        e = self.evidence(data, "herdr")[0]
        self.assertTrue(e["env_present"])
        self.assertFalse(e["available"])
        self.assertIn("接続できない", e["condition"])

    def test_orca_env_but_unreachable(self):
        status = json.loads(fixture("orca_status.json"))
        status["result"]["runtime"]["reachable"] = False
        self.stub.add("orca", stdout=json.dumps(status))
        data = self.detect({"ORCA_TERMINAL_HANDLE": "h"})
        self.assertEqual(data["channel"], "none")
        e = self.evidence(data, "orca")[0]
        self.assertTrue(e["env_present"])
        self.assertFalse(e["available"])
        self.assertIn("接続できない", e["condition"])

    def test_both_enabled_prefers_herdr(self):
        self.herdr_ok()
        self.orca_ok()
        data = self.detect({"HERDR_ENV": "1", "ORCA_TERMINAL_HANDLE": "h"})
        self.assertEqual(data["channel"], "herdr")

    def test_evidence_contains_conditions(self):
        self.herdr_ok()
        data = self.detect({"HERDR_ENV": "1"})
        e = data["evidence"][0]
        self.assertEqual(e["channel"], "herdr")
        self.assertEqual(e["env"], "HERDR_ENV")
        self.assertTrue(e["env_present"])
        self.assertTrue(e["available"])
        self.assertIn("HERDR_ENV", e["condition"])

    def test_orca_not_called_when_herdr_enabled(self):
        self.herdr_ok()
        self.orca_ok()
        self.detect({"HERDR_ENV": "1", "ORCA_TERMINAL_HANDLE": "h"})
        self.assertFalse([c for c in self.stub.calls() if c.startswith("orca")])


if __name__ == "__main__":
    unittest.main()
