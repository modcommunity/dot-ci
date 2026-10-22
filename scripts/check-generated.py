#!/usr/bin/env python3
"""Generated-file drift: run each generator and fail when its output differs from the committed file.

    scripts/check-generated.py [--update|--init] [--baseline F] <project-dir>

ci/generated.tsv lists `generated-file<TAB>command` per line (# comments allowed); the command
runs in the project directory with a 60 s cap. The file is compared before and after and always
restored, so the gate never changes the tree. A drifted file is a violation of count 1; a
generator that fails or a missing file counts too. Baseline: ci/efficiency/generated.tsv.
No ci/generated.tsv means nothing to check.
"""
import os
import subprocess
import sys
import effgate

LIST = "ci/generated.tsv"
CAP = 60


def read(path):
    try:
        with open(path, "rb") as fh:
            return fh.read()
    except OSError:
        return None


def measure(root):
    cur = {}
    lst = os.path.join(root, LIST)
    if not os.path.isfile(lst):
        return cur
    with open(lst, encoding="utf-8") as fh:
        rows = [l.rstrip("\n").split("\t", 1) for l in fh if l.strip() and not l.startswith("#")]
    for row in rows:
        if len(row) != 2:
            continue
        rel, cmd = row
        path = os.path.join(root, rel)
        before = read(path)
        try:
            r = subprocess.run(cmd, shell=True, cwd=root, capture_output=True, timeout=CAP)
            ok = r.returncode == 0
        except subprocess.TimeoutExpired:
            ok = False
        after = read(path)
        if before is None:
            if after is not None:
                os.remove(path)
        elif after != before:
            with open(path, "wb") as fh:
                fh.write(before)
        if not ok or after != before:
            cur[rel] = 1
    return cur


def main():
    p = effgate.make_parser(__doc__.split("\n")[0], "ci/efficiency/generated.tsv")
    a = p.parse_args()
    return effgate.run_gate(a, measure(a.dir), "generated", "drift")


if __name__ == "__main__":
    sys.exit(main())
