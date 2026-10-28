"""Fixtures for the efficiency gates. Run: python3 -m unittest discover -s tests"""
import os
import subprocess
import sys
import tempfile
import unittest

S = os.path.join(os.path.dirname(__file__), "..", "scripts")


def run(script, *args):
    r = subprocess.run([sys.executable, os.path.join(S, script), *args], capture_output=True, text=True)
    return r.returncode, r.stdout + r.stderr


def project(files):
    d = tempfile.mkdtemp()
    for name, body in files.items():
        p = os.path.join(d, name)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w") as fh:
            fh.write(body)
    return d


def long_func(name, n):
    return "func %s():\n" % name + "".join("\tvar a%d = %d\n" % (i, i) for i in range(n)) + "\n"


class Size(unittest.TestCase):
    def test_ratchet(self):
        d = project({"a.gd": long_func("big", 90) + long_func("ok", 10)})
        code, out = run("check-size.py", d)
        self.assertEqual(code, 1)
        self.assertIn("a.gd::big", out)
        self.assertNotIn("a.gd::ok", out)
        self.assertEqual(run("check-size.py", "--init", d)[0], 0)
        self.assertEqual(run("check-size.py", d)[0], 0)
        self.assertEqual(run("check-size.py", "--init", d)[0], 1)  # never overwrites
        # Growing a known violation fails; a new one fails; --update refuses to add.
        with open(os.path.join(d, "a.gd"), "w") as fh:
            fh.write(long_func("big", 95) + long_func("new", 85))
        self.assertEqual(run("check-size.py", d)[0], 1)
        self.assertEqual(run("check-size.py", "--update", d)[0], 1)
        # Shrinking: --update drops the fixed one and lowers the other.
        with open(os.path.join(d, "a.gd"), "w") as fh:
            fh.write(long_func("big", 85))
        self.assertEqual(run("check-size.py", "--update", d)[0], 0)
        tsv = open(os.path.join(d, "ci/efficiency/size.tsv")).read()
        self.assertIn("a.gd::big\t86", tsv)

    def test_file_budget(self):
        d = project({"b.gd": "var x = 1\n" * 801})
        self.assertIn("b.gd", run("check-size.py", d)[1])
        d = project({"b.gd": "var x = 1\n" * 800})
        self.assertEqual(run("check-size.py", d)[0], 0)


HAZ = """extends Node
func _process(delta):
\tvar n = $Label
\tvar l = get_nodes_in_group("x")
\tvar a = []
\ttext = "a" + str(delta)
\thelper()
\tsignal_thing.connect(_f)
\tvar ok = "# not $Comment"  # get_node("x")

func helper():
\tvar r = load("res://a.tres")
\tget_node("B")

func cold():
\tvar n = $Label
\tvar r = preload("res://a.tres")

func other():
\tif not s.is_connected(_f):
\t\ts.connect(_f)
"""


class Hazards(unittest.TestCase):
    def test_kinds_and_reach(self):
        d = project({"h.gd": HAZ})
        code, out = run("check-frame-hazards.py", d)
        self.assertEqual(code, 1)
        for k in ("_process::node_lookup", "_process::group_lookup", "_process::alloc_array",
                  "_process::string_build", "_process::connect_unguarded", "helper::load", "helper::node_lookup"):
            self.assertIn(k, out)
        self.assertNotIn("cold", out)
        self.assertNotIn("other", out)
        self.assertIn("_process::node_lookup 1 ", out)  # the comment and the string are not counted

    def test_baseline(self):
        d = project({"h.gd": HAZ})
        self.assertEqual(run("check-frame-hazards.py", "--init", d)[0], 0)
        self.assertEqual(run("check-frame-hazards.py", d)[0], 0)
        with open(os.path.join(d, "h.gd"), "a") as fh:
            fh.write("\nfunc _physics_process(d):\n\tfind_children(\"*\")\n")
        self.assertEqual(run("check-frame-hazards.py", d)[0], 1)


BLOCK = "".join("\tprint(%d)\n\tx = %d + y\n" % (i, i) for i in range(20))


class Duplication(unittest.TestCase):
    def test_copy_detected_and_ratchet(self):
        d = project({"a.gd": "func f():\n" + BLOCK, "b.gd": "# other\nfunc g():\n\t\t" + BLOCK.replace("\t", "  ").strip() + "\n",
                     "c.gd": "func h():\n\tprint(1)\n"})
        code, out = run("check-duplication.py", d)
        self.assertEqual(code, 1)
        self.assertIn("a.gd", out)
        self.assertIn("b.gd", out)
        self.assertNotIn("c.gd", out)
        self.assertEqual(run("check-duplication.py", "--init", d)[0], 0)
        self.assertEqual(run("check-duplication.py", d)[0], 0)
        with open(os.path.join(d, "c.gd"), "w") as fh:
            fh.write("func h():\n" + BLOCK)
        self.assertEqual(run("check-duplication.py", d)[0], 1)

    def test_repeating_table_is_not_a_copy(self):
        d = project({"t.gd": "var t = [\n" + "\t1,\n" * 100 + "]\n"})
        self.assertEqual(run("check-duplication.py", d)[0], 0)

    def test_cross(self):
        a = project({"a.gd": "func f():\n" + BLOCK})
        b = project({"z.gd": "func f():\n" + BLOCK})
        code, out = run("check-duplication.py", "--cross", a, b)
        self.assertEqual(code, 0)
        self.assertIn("1 span repositories", out)


COMMENTS = """extends Node
# one
# two
# three
# four
var a = 1
# ---- Section ----
## A doc line.
# var x = 5
# print(x)
# fixed 2026-10-01, used to crash
# plain prose about the player
func f():
\tpass
"""


class Comments(unittest.TestCase):
    def test_kinds(self):
        d = project({"c.gd": COMMENTS})
        code, out = run("check-comments.py", d)
        self.assertEqual(code, 1)
        for k in ("long_block", "banner", "commented_code 2", "history 1"):
            self.assertIn(k, out)
        self.assertNotIn("plain prose", out)

    def test_three_lines_is_fine(self):
        d = project({"c.gd": "# a\n# b\n# c\nvar x = 1\n"})
        self.assertEqual(run("check-comments.py", d)[0], 0)

    def test_ratchet(self):
        d = project({"c.gd": COMMENTS})
        self.assertEqual(run("check-comments.py", "--init", d)[0], 0)
        self.assertEqual(run("check-comments.py", d)[0], 0)
        with open(os.path.join(d, "c.gd"), "a") as fh:
            fh.write("# ====\n")
        self.assertEqual(run("check-comments.py", d)[0], 1)


class Logging(unittest.TestCase):
    BAD = 'const CHANNEL := "x"\nfunc f():\n\tpush_warning("w")\n'
    GOOD = 'const CHANNEL := "x"\nfunc f():\n\tDotLog.info(CHANNEL, "ok")\n\t# push_warning("no")\n'

    def test_bad_fails_and_clean_passes(self):
        code, out = run("check-logging.py", project({"a.gd": self.BAD}))
        self.assertEqual(code, 1)
        self.assertIn("channel_silent", out)
        self.assertIn("push_warning", out)
        self.assertEqual(run("check-logging.py", project({"a.gd": self.GOOD}))[0], 0)

    def test_ratchet(self):
        d = project({"a.gd": self.BAD})
        self.assertEqual(run("check-logging.py", "--init", d)[0], 0)
        self.assertEqual(run("check-logging.py", d)[0], 0)
        with open(os.path.join(d, "a.gd"), "a") as fh:
            fh.write("\tpush_warning(\"again\")\n")
        self.assertEqual(run("check-logging.py", d)[0], 1)


class MarkdownWrap(unittest.TestCase):
    BAD = "# T\n\nfirst line of a paragraph\nsecond line of it\n\nok single line\n"
    GOOD = ("---\na: b\nc: d\n---\n# T\n\none line\n\n- item one\n  continues\n- item two\n\n"
            "| a | b |\n| - | - |\n\n```\ncode one\ncode two\n```\n")

    def test_bad_fails_and_clean_passes(self):
        code, out = run("check-markdown-wrap.py", project({"a.md": self.BAD}))
        self.assertEqual(code, 1)
        self.assertIn("a.md::hard_wrap 1", out)
        self.assertEqual(run("check-markdown-wrap.py", project({"a.md": self.GOOD}))[0], 0)

    def test_ratchet(self):
        d = project({"a.md": self.BAD})
        self.assertEqual(run("check-markdown-wrap.py", "--init", d)[0], 0)
        self.assertEqual(run("check-markdown-wrap.py", d)[0], 0)
        with open(os.path.join(d, "a.md"), "a") as fh:
            fh.write("\nanother\nwrapped one\n")
        self.assertEqual(run("check-markdown-wrap.py", d)[0], 1)


class SuiteChecks(unittest.TestCase):
    SUITE = "const CHECKS := 10\nfunc _ready():\n\t_report(CHECKS + 1)\n"

    def tree(self, total):
        return project({"examples/s.gd": self.SUITE,
                        ".godot/test-logs/s.log": "ok\n\n%d passed, 0 failed\n" % total})

    def test_drift_fails_and_match_passes(self):
        code, out = run("check-suite-checks.py", self.tree(13))
        self.assertEqual(code, 1)
        self.assertIn("s.gd::checks_drift 2", out)
        self.assertEqual(run("check-suite-checks.py", self.tree(11))[0], 0)

    def test_no_log_is_skipped(self):
        self.assertEqual(run("check-suite-checks.py", project({"examples/s.gd": self.SUITE}))[0], 0)

    def test_ratchet(self):
        d = self.tree(13)
        self.assertEqual(run("check-suite-checks.py", "--init", d)[0], 0)
        self.assertEqual(run("check-suite-checks.py", d)[0], 0)
        with open(os.path.join(d, ".godot/test-logs/s.log"), "a") as fh:
            fh.write("20 passed, 0 failed\n")
        self.assertEqual(run("check-suite-checks.py", d)[0], 1)


class Generated(unittest.TestCase):
    def test_drift(self):
        d = project({"out.txt": "old\n", "ci/generated.tsv": "out.txt\techo new > out.txt\n"})
        code, out = run("check-generated.py", d)
        self.assertEqual(code, 1)
        self.assertIn("out.txt", out)
        self.assertEqual(open(os.path.join(d, "out.txt")).read(), "old\n")  # restored
        self.assertEqual(run("check-generated.py", "--init", d)[0], 0)  # debt is accepted
        self.assertEqual(run("check-generated.py", d)[0], 0)

    def test_in_sync_and_no_list(self):
        d = project({"out.txt": "same\n", "ci/generated.tsv": "out.txt\techo same > out.txt\n"})
        self.assertEqual(run("check-generated.py", d)[0], 0)
        self.assertEqual(run("check-generated.py", project({"a.gd": ""}))[0], 0)

    def test_failing_generator(self):
        d = project({"out.txt": "x\n", "ci/generated.tsv": "out.txt\tfalse\n"})
        self.assertEqual(run("check-generated.py", d)[0], 1)


class WebSize(unittest.TestCase):
    def test_budget(self):
        d = project({"build/a.wasm": "x" * 100, "build/b.pck": "y" * 10,
                     "ci/web-budget.tsv": "# f\tmax\nbuild/a.wasm\t50\nbuild/b.pck\t50\nbuild/none\t1\n"})
        code, out = run("check-web-size.py", d)
        self.assertEqual(code, 1)
        self.assertIn("build/a.wasm 100", out)
        self.assertNotIn("b.pck", out)
        self.assertEqual(run("check-web-size.py", "--init", d)[0], 0)
        self.assertEqual(run("check-web-size.py", d)[0], 0)
        with open(os.path.join(d, "build/a.wasm"), "w") as fh:
            fh.write("x" * 120)
        self.assertEqual(run("check-web-size.py", d)[0], 1)

    def test_no_list(self):
        self.assertEqual(run("check-web-size.py", project({"a.gd": ""}))[0], 0)


class CrossWrapper(unittest.TestCase):
    def test_prints_clusters_and_never_fails(self):
        a = project({"a.gd": "func f():\n" + BLOCK})
        b = project({"z.gd": "func f():\n" + BLOCK})
        r = subprocess.run(["bash", os.path.join(S, "duplication-cross.sh"), "--top", "3", a, b],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0)
        self.assertIn("1 span repositories", r.stdout)
        self.assertIn("lines x2", r.stdout)

class Trend(unittest.TestCase):
    REPORT = "repo size hazards lines comment%%\na %d %d 1000 10.0%%\nb 0 0 1000 20.0%%\nduplication (cross): %d clusters\n"

    def go(self, hist, report, *extra):
        r = subprocess.run([sys.executable, os.path.join(S, "efficiency-trend.py"), "--history", hist, *extra],
                           input=report, capture_output=True, text=True)
        return r.returncode, r.stdout

    def test_regression_fails_strict(self):
        hist = os.path.join(tempfile.mkdtemp(), "h.jsonl")
        self.assertEqual(self.go(hist, self.REPORT % (2, 1, 3), "--strict")[0], 0)
        code, out = self.go(hist, self.REPORT % (2, 1, 3), "--strict")
        self.assertEqual(code, 0)
        self.assertIn("comment_pct   15.0", out)
        code, out = self.go(hist, self.REPORT % (3, 1, 3), "--strict")  # the deliberately bad run
        self.assertEqual(code, 1)
        self.assertIn("REGRESSED: size", out)
        self.assertEqual(self.go(hist, self.REPORT % (1, 0, 2), "--strict")[0], 0)  # shrinking is fine

    def test_empty_report(self):
        self.assertEqual(self.go(os.path.join(tempfile.mkdtemp(), "h"), "nothing\n")[0], 2)


class GateSelfTest(unittest.TestCase):
    """The done-when: a clean baselined project stays green, then a deliberately added
    duplicate fails the duplication gate and a per-frame allocation fails the hazard gate."""

    def clean(self):
        d = project({"a.gd": "extends Node\nfunc _process(delta):\n\tpass\n", "b.gd": "func f():\n" + BLOCK})
        for s in ("check-duplication.py", "check-frame-hazards.py", "check-size.py"):
            self.assertEqual(run(s, "--init", d)[0], 0)
            self.assertEqual(run(s, d)[0], 0)
        return d

    def test_added_duplicate_fails(self):
        d = self.clean()
        with open(os.path.join(d, "dup.gd"), "w") as fh:
            fh.write("func copy():\n" + BLOCK)
        self.assertEqual(run("check-duplication.py", d)[0], 1)

    def test_added_per_frame_allocation_fails(self):
        d = self.clean()
        with open(os.path.join(d, "a.gd"), "w") as fh:
            fh.write("extends Node\nfunc _process(delta):\n\tvar tmp = []\n\tvar n = get_node(\"X\")\n")
        code, out = run("check-frame-hazards.py", d)
        self.assertEqual(code, 1)
        self.assertIn("alloc_array", out)


class PerfBudget(unittest.TestCase):
    RES = '{"scene":"res://m.tscn","load_ms":1000,"frame_ms":2,"nodes":%d,"mem_mb":100}'

    def go(self, mode, path, res):
        return run("perf-budget.py", mode, path, "20", res)

    def test_ratchet(self):
        path = os.path.join(tempfile.mkdtemp(), "ci", "perf", "smoke.json")
        self.assertEqual(self.go("init", path, self.RES % 1000)[0], 0)
        self.assertEqual(self.go("init", path, self.RES % 1000)[0], 1)  # never overwrites
        self.assertEqual(self.go("check", path, self.RES % 1190)[0], 0)  # inside 20%
        code, out = self.go("check", path, self.RES % 1300)  # the deliberate regression
        self.assertEqual(code, 1)
        self.assertIn("REGRESSED nodes", out)
        self.assertEqual(self.go("update", path, self.RES % 900)[0], 0)
        self.assertEqual(self.go("check", path, self.RES % 1100)[0], 1)  # budget fell to 900
        self.assertEqual(self.go("update", path, self.RES % 2000)[0], 1)  # and never rises


if __name__ == "__main__":
    unittest.main()
