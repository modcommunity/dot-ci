"""Fixtures for check-suite-checks.py. Run: python3 -m unittest discover -s tests"""
import importlib.util
import os
import sys
import tempfile
import unittest

here = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(here, "..", "scripts"))
spec = importlib.util.spec_from_file_location("sc", os.path.join(here, "..", "scripts", "check-suite-checks.py"))
sc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sc)


def run(src, total, log_newer=True):
    with tempfile.TemporaryDirectory() as d:
        script = os.path.join(d, "examples", "s.gd")
        os.makedirs(os.path.dirname(script))
        open(script, "w").write(src)
        logdir = os.path.join(d, ".godot", "test-logs")
        os.makedirs(logdir)
        log = os.path.join(logdir, "s.log")
        open(log, "w").write("%d passed, 0 failed\n" % total)
        t = os.path.getmtime(script)
        os.utime(log, (t + (10 if log_newer else -10),) * 2)
        return sc.measure(d)


class SuiteChecks(unittest.TestCase):
    def test_sum_literal(self):
        self.assertEqual(run("const CHECKS := 776 + 21\n", 797), {})

    def test_const_expression_with_other_consts(self):
        src = "const WINDOW_CHECKS := 7\nconst CHECKS := 7 + 3 * WINDOW_CHECKS + 2\n"
        self.assertEqual(run(src, 30), {})

    def test_forward_reference(self):
        self.assertEqual(run("const CHECKS := 4 + LATER\nconst LATER := 3\n", 7), {})

    def test_offset_in_comparison(self):
        src = "const CHECKS := 10\nfunc f():\n\tvar ok := _passed + _failed == CHECKS + 1\n"
        self.assertEqual(run(src, 11), {})

    def test_offset_in_report(self):
        self.assertEqual(run("const CHECKS := 10\n_report(CHECKS + 1)\n", 11), {})
        self.assertEqual(run("const CHECKS := 10\n_report_sections(a, b, S, CHECKS - 2)\n", 8), {})

    def test_true_drift(self):
        self.assertEqual(run("const CHECKS := 389\n", 392), {"examples/s.gd::checks_drift": 3})

    def test_unknown_name_skipped(self):
        self.assertEqual(run("const CHECKS := BASE + 1\n", 99), {})

    def test_runtime_offset_ignored(self):
        self.assertEqual(run("const CHECKS := 10\n_report(CHECKS - _skipped)\n", 10), {})

    def test_no_eval_of_code(self):
        self.assertEqual(run("const CHECKS := __import__('os').getpid()\n", 1), {})

    def test_negative_division_truncates(self):
        self.assertEqual(sc.evaluate("-7 / 2", {}), -3)
        self.assertEqual(sc.evaluate("7 / -2", {}), -3)
        self.assertEqual(sc.evaluate("-7 / -2", {}), 3)
        self.assertEqual(sc.evaluate("7 / 2", {}), 3)
        self.assertEqual(run("const CHECKS := -7 / 2 + 13\n", 10), {})

    def test_division_by_zero_skipped(self):
        self.assertEqual(sc.evaluate("5 / 0", {}), None)

    def test_deep_nesting_does_not_crash(self):
        self.assertIsNone(sc.evaluate("(" * 5000 + "1" + ")" * 5000, {}))
        self.assertEqual(run("const CHECKS := " + "-" * 5000 + "1\n", 99), {})

    def test_nul_byte_does_not_crash(self):
        self.assertIsNone(sc.evaluate("1 +\x00 2", {}))
        self.assertEqual(run("const CHECKS := 1 +\x00 2\n", 99), {})

    def test_stale_log_is_not_a_violation(self):
        self.assertEqual(run("const CHECKS := 389\n", 392, log_newer=False), {})


if __name__ == "__main__":
    unittest.main()
