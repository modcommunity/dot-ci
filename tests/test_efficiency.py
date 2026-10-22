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


if __name__ == "__main__":
    unittest.main()
