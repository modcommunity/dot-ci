"""Fixtures for check-no-js-eval.py. Run: python3 -m unittest discover -s tests"""
import importlib.util
import os
import unittest

spec = importlib.util.spec_from_file_location(
    "ne", os.path.join(os.path.dirname(__file__), "..", "scripts", "check-no-js-eval.py"))
ne = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ne)


class NoJsEval(unittest.TestCase):
    def test_bad(self):
        for path, line in [("a.gd", 'var x = JavaScriptBridge.eval("1", true)'),
                           ("a.gd", 'DotWeb.eval("window.x")'),
                           ("a.gd", 'b.call("eval", code)'),
                           ("a.js", "eval('1')"), ("a.html", "x = new Function('return 1')")]:
            self.assertTrue(ne.problems(path, line), line)

    def test_good(self):
        for path, line in [("a.gd", "# JavaScriptBridge.eval throws under the CSP"),
                           ("a.gd", "var x = DotWeb.query_param('a')"),
                           ("a.gd", 'JavaScriptBridge.eval("1") # js-eval: allow test harness'),
                           ("a.js", "page.evaluate(() => 1)"), ("a.js", "// eval('x')"),
                           ("a.js", "obj.eval(1)"), ("a.md", "JavaScriptBridge.eval")]:
            self.assertEqual(ne.problems(path, line), [], line)

    def test_block_comment(self):
        self.assertEqual(ne.problems("a.html", "/*\n it is a JavaScript eval(x)\n*/\nfoo()"), [])
