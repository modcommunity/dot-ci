"""Fixtures for check-windows-names.py. Run: python3 -m unittest discover -s tests"""
import importlib.util
import os
import unittest

spec = importlib.util.spec_from_file_location(
    "wn", os.path.join(os.path.dirname(__file__), "..", "scripts", "check-windows-names.py"))
wn = importlib.util.module_from_spec(spec)
spec.loader.exec_module(wn)

GOOD = ["a.gd", "cfg/surf_%.yml", "addons/x/aux_data.gd", "console.gd", "docs/a.b.md",
        "dir/.gitignore", "Com10.txt", "nullable/x", "a b/c d.txt"]
BAD = ["surf_*.yml", "a?.txt", "a:b", 'q".x', "a<b", "a>b", "a|b", "a\\b", "dir./x",
       "dir/trail.", "dir/trail ", "CON", "con.txt", "x/Nul.tscn", "aux.gd", "COM1.md",
       "lpt9", "d/PRN.x.y"]


class WindowsNames(unittest.TestCase):
    def test_good(self):
        for p in GOOD:
            self.assertEqual(wn.problems([p]), [], p)

    def test_bad(self):
        for p in BAD:
            self.assertTrue(wn.problems([p]), p)

    def test_case_collision(self):
        self.assertTrue(wn.problems(["a/Foo.gd", "a/foo.gd"]))
        self.assertEqual(wn.problems(["a/Foo.gd", "b/foo.gd"]), [])
