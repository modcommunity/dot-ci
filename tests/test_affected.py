import json
import os
import subprocess
import sys
import tempfile
import unittest

SCRIPT = os.path.join(os.path.dirname(__file__), "..", "scripts", "affected.py")


def sh(cwd, *a):
    subprocess.run(a, cwd=cwd, check=True, capture_output=True)


class AffectedTest(unittest.TestCase):
    def test_consumer_suite_is_found_by_class_name(self):
        with tempfile.TemporaryDirectory() as root:
            lib = os.path.join(root, "lib")
            os.makedirs(os.path.join(lib, "addons", "x"))
            open(os.path.join(lib, "addons", "x", "thing.gd"), "w").write("class_name LibThing\n")
            sh(lib, "git", "init", "-q")
            for who in ("g1", "g2"):
                g = os.path.join(root, who)
                os.makedirs(os.path.join(g, "addons"))
                os.makedirs(os.path.join(g, "examples"))
                os.symlink(os.path.join(lib, "addons", "x"), os.path.join(g, "addons", "x"))
                open(os.path.join(g, "game.sh"), "w").write('SUITES="s_a s_b"\n')
                sh(g, "git", "init", "-q")
            open(os.path.join(root, "g1", "examples", "s_a.gd"), "w").write("var t = LibThing.new()\n")
            r = subprocess.run([sys.executable, "-I", SCRIPT, "lib", "--root", root, "--files", "addons/x/thing.gd", "--json"],
                               capture_output=True, text=True, check=True, cwd=root)
            by = {c["consumer"]: c for c in json.loads(r.stdout)["consumers"]}
            self.assertEqual(by["g1"]["suites"], ["s_a"])
            self.assertEqual(by["g2"]["suites"], [])
            self.assertEqual(by["g2"]["why"], "parse")


if __name__ == "__main__":
    unittest.main()
