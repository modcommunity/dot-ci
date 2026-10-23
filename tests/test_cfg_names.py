"""Fixtures for check-cfg-names.sh. Run: python3 -m unittest discover -s tests"""
import os
import subprocess
import tempfile
import unittest

SCRIPT = os.path.join(os.path.dirname(__file__), "..", "scripts", "check-cfg-names.sh")


def check(name):
    d = tempfile.mkdtemp()
    os.makedirs(os.path.join(d, "cfg", "game", "g", "dot_map", "map"))
    open(os.path.join(d, "cfg", "game", "g", "dot_map", "map", name), "w").close()
    return subprocess.run(["bash", SCRIPT, d], capture_output=True, text=True).returncode


class CfgNames(unittest.TestCase):
    def test_percent_passes(self):
        self.assertEqual(check("surf_%.yml"), 0)

    def test_star_fails(self):
        self.assertEqual(check("surf_*.yml"), 1)

    def test_question_fails(self):
        self.assertEqual(check("surf_?.yml"), 1)
