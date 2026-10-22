"""The validate workflow's opt-in perf input. Run: python3 -m unittest discover -s tests"""
import os
import re
import unittest

W = os.path.join(os.path.dirname(__file__), "..", ".github", "workflows", "validate.yml")


class PerfInput(unittest.TestCase):
    def setUp(self):
        self.text = open(W).read()

    def test_input_is_opt_in_boolean(self):
        m = re.search(r"\n {12}perf:\n(.*?)\n {12}\w[\w-]*:\n", self.text, re.S)
        self.assertIsNotNone(m, "no perf input")
        self.assertIn("type: boolean", m.group(1))
        self.assertIn("default: false", m.group(1))

    def test_step_runs_check_mode_only_when_enabled(self):
        m = re.search(r"- name: Perf smoke.*?\n\s+if: ([^\n]+)\n\s+run: ([^\n]+)", self.text, re.S)
        self.assertIsNotNone(m, "no perf step")
        self.assertIn("inputs.perf", m.group(1))
        self.assertIn("scripts/perf-smoke.sh project", m.group(2))
        self.assertNotRegex(m.group(2), r"--(init|update)")


if __name__ == "__main__":
    unittest.main()
