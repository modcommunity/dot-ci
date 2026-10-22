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


if __name__ == "__main__":
    unittest.main()
