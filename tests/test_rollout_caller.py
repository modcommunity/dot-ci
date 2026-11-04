"""rollout-caller.sh on a throwaway repo. Run: python3 -m unittest discover -s tests"""
import os
import subprocess
import tempfile
import unittest

script = os.path.join(os.path.dirname(__file__), "..", "scripts", "rollout-caller.sh")
CI = """name: CI
on: [push]
jobs:
    validate:
        uses: modcommunity/dot-ci/.github/workflows/validate.yml@v1
%s        secrets:
            DEPS_TOKEN: ${{ secrets.DOT_DEPS_TOKEN }}
"""


def git(d, *a):
    return subprocess.run(["git", "-C", d, *a], capture_output=True, text=True, check=True).stdout


def make(d, with_block=""):
    git(d, "init", "-q")
    os.makedirs(os.path.join(d, ".github", "workflows"))
    with open(os.path.join(d, ".github", "workflows", "ci.yml"), "w") as f:
        f.write(CI % with_block)
    with open(os.path.join(d, "a.gd"), "w") as f:
        f.write("extends Node\n")
    with open(os.path.join(d, "README.md"), "w") as f:
        f.write("# x\n")
    git(d, "add", "-A")
    git(d, "-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-q", "-m", "init")


def run(d):
    env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.com",
               GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.com")
    return subprocess.run(["bash", script, d], capture_output=True, text=True, env=env)


class Rollout(unittest.TestCase):
    def test_adds_baselines_flags_once(self):
        with tempfile.TemporaryDirectory() as d:
            make(d)
            r = run(d)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            yml = open(os.path.join(d, ".github/workflows/ci.yml")).read()
            self.assertIn("        with:\n            efficiency: true\n            hygiene: true\n        secrets:", yml)
            self.assertNotIn("perf:", yml)
            self.assertTrue(os.path.exists(os.path.join(d, "ci/efficiency/size.tsv")))
            n = git(d, "rev-list", "--count", "HEAD").strip()
            r = run(d)
            self.assertEqual(r.returncode, 0)
            self.assertIn("nothing to do", r.stdout)
            self.assertEqual(git(d, "rev-list", "--count", "HEAD").strip(), n)

    def test_existing_with_block_keeps_keys(self):
        with tempfile.TemporaryDirectory() as d:
            make(d, "        with:\n            suites: foo\n")
            self.assertEqual(run(d).returncode, 0)
            yml = open(os.path.join(d, ".github/workflows/ci.yml")).read()
            self.assertIn("            suites: foo\n            efficiency: true\n", yml)

    def test_dirty_tree_skipped(self):
        with tempfile.TemporaryDirectory() as d:
            make(d)
            open(os.path.join(d, "dirty.txt"), "w").write("x")
            r = run(d)
            self.assertEqual(r.returncode, 3)
            self.assertFalse(os.path.exists(os.path.join(d, "ci")))

    def test_never_overwrites_baseline(self):
        with tempfile.TemporaryDirectory() as d:
            make(d)
            os.makedirs(os.path.join(d, "ci/efficiency"))
            p = os.path.join(d, "ci/efficiency/size.tsv")
            open(p, "w").write("keep\n")
            git(d, "add", "-A")
            git(d, "-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-q", "-m", "b")
            run(d)
            self.assertEqual(open(p).read(), "keep\n")


if __name__ == "__main__":
    unittest.main()
