"""Fixtures for check-logging.py. Run: python3 -m unittest discover -s tests"""
import importlib.util
import os
import sys
import tempfile
import unittest

here = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(here, "..", "scripts"))
spec = importlib.util.spec_from_file_location("cl", os.path.join(here, "..", "scripts", "check-logging.py"))
cl = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cl)


def run(files):
    with tempfile.TemporaryDirectory() as d:
        for rel, txt in files.items():
            os.makedirs(os.path.dirname(os.path.join(d, rel)) or d, exist_ok=True)
            with open(os.path.join(d, rel), "w") as fh:
                fh.write(txt)
        return cl.measure(d)


BASE = 'extends RefCounted\nconst CHANNEL := "x"\n'


class Logging(unittest.TestCase):
    def test_silent_alone(self):
        self.assertEqual(run({"a.gd": BASE}), {"a.gd::channel_silent": 1})

    def test_subclass_by_path_logs(self):
        r = run({"c/base.gd": BASE, "c/sub.gd": 'extends "base.gd"\nfunc f():\n\tDotLog.info(CHANNEL, "m")\n'})
        self.assertEqual(r, {})

    def test_subclass_by_class_name_logs(self):
        r = run({"base.gd": "class_name Base\n" + BASE, "s.gd": "extends Base\nfunc f():\n\tDotLog.info(CHANNEL, 'm')\n"})
        self.assertEqual(r, {})

    def test_subclass_silent_too(self):
        r = run({"base.gd": "class_name Base\n" + BASE, "s.gd": "extends Base\n"})
        self.assertEqual(r, {"base.gd::channel_silent": 1})

    def test_dotlog_own_file_exempt(self):
        self.assertEqual(run({"l.gd": "class_name DotLog\nfunc f():\n\tpush_warning(x)\n"}), {})

    def test_other_push_warning_counts(self):
        self.assertEqual(run({"o.gd": "func f():\n\tpush_warning(x)\n"}), {"o.gd::push_warning": 1})

    def test_allow_marker(self):
        self.assertEqual(run({"o.gd": "func f():\n\tpush_warning(x) # check-logging: allow push_warning\n"}), {})


if __name__ == "__main__":
    unittest.main()
