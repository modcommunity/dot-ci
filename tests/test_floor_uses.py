"""Fixtures for check-floor-uses.py. Run: python3 -m unittest discover -s tests"""
import json
import os
import subprocess
import tempfile
import unittest

SCRIPT = os.path.join(os.path.dirname(__file__), "..", "scripts", "check-floor-uses.py")
API = "# 1: before.\n# 2: DotOld.\n# 3: DotNew, DotOther.\n#    DotOld.member; DotNew skips x.\nconst LEVEL := 3\n"


def check(floor, code):
    d = tempfile.mkdtemp()
    a = os.path.join(d, "addons", "dot_x")
    os.makedirs(a)
    open(os.path.join(a, "dot_x_api.gd"), "w").write(API)
    open(os.path.join(a, "c.gd"), "w").write("class_name DotOld\nclass_name DotNew\n")
    os.makedirs(os.path.join(d, "game"))
    open(os.path.join(d, "game", "g.gd"), "w").write(code)
    json.dump({"format": 1, "addons": {"dot_x": floor}}, open(os.path.join(d, "requires.floor.json"), "w"))
    return subprocess.run(["python3", SCRIPT, d], capture_output=True, text=True).returncode


class FloorUses(unittest.TestCase):
    def test_floor_at_level_passes(self):
        self.assertEqual(check(3, "var a := DotNew.new()\n"), 0)

    def test_floor_below_unguarded_fails(self):
        self.assertEqual(check(2, "var a := DotNew.new()\n"), 1)

    def test_guard_in_file_passes(self):
        self.assertEqual(check(2, 'if DotAddonApi.build_level("dot_x") >= 3:\n\tDotNew.new()\n'), 0)

    def test_comment_mention_ignored(self):
        self.assertEqual(check(2, "# DotNew is newer\n"), 0)
