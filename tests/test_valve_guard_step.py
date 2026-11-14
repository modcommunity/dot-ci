"""The Valve-origin guard step in validate.yml. Run: python3 -m unittest discover -s tests"""
import os
import re
import unittest

W = os.path.join(os.path.dirname(__file__), "..", ".github", "workflows", "validate.yml")


class ValveGuardStep(unittest.TestCase):
    def setUp(self):
        self.text = open(W).read()

    def _step(self, name):
        m = re.search(r"- name: %s\n((?:(?!\n {12}- name:).*\n?)*)" % re.escape(name), self.text)
        self.assertIsNotNone(m, "no step named %r" % name)
        return m.group(1)

    def test_checkout_is_pinned_to_a_full_commit(self):
        body = self._step("Check out the Valve-origin guard")
        self.assertIn("repository: modcommunity/dot-cloud", body)
        m = re.search(r"ref: ([0-9a-f]+)\n", body)
        self.assertIsNotNone(m, "ref is not a literal commit")
        self.assertRegex(m.group(1), r"^[0-9a-f]{40}$", "pin must be a full 40-character commit, not a branch")

    def test_guard_runs_in_git_mode_on_the_project_and_is_not_conditional(self):
        body = self._step("No Valve-origin files in the tracked tree")
        self.assertIn("python3 -I dot-cloud/tools/check_valve_files.py --git project", body)
        self.assertNotIn("if:", body)

    def test_guard_runs_after_checkout(self):
        self.assertLess(self.text.index("Check out the Valve-origin guard"),
                        self.text.index("No Valve-origin files in the tracked tree"))


if __name__ == "__main__":
    unittest.main()
