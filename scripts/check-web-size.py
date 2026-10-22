#!/usr/bin/env python3
"""Web build size budget: each listed file (or glob) must stay under its byte limit.

    scripts/check-web-size.py [--update|--init] [--baseline F] <project-dir>

ci/web-budget.tsv lists `file-or-glob<TAB>max_bytes` per line (# comments allowed), relative to
the project directory. A listed file that is absent is skipped (the build was not made). An
over-budget file is a violation holding its size; the baseline (ci/efficiency/web-size.tsv)
lets existing debt stand but a larger size fails. No ci/web-budget.tsv means nothing to check.
"""
import glob
import os
import sys
import effgate

LIST = "ci/web-budget.tsv"


def measure(root):
    cur = {}
    lst = os.path.join(root, LIST)
    if not os.path.isfile(lst):
        return cur
    with open(lst, encoding="utf-8") as fh:
        for ln in fh:
            if not ln.strip() or ln.startswith("#"):
                continue
            pat, _, mx = ln.rstrip("\n").rpartition("\t")
            if not pat or not mx.strip().isdigit():
                continue
            for path in glob.glob(os.path.join(root, pat)):
                size = os.path.getsize(path)
                if size > int(mx):
                    cur[os.path.relpath(path, root)] = size
    return cur


def main():
    p = effgate.make_parser(__doc__.split("\n")[0], "ci/efficiency/web-size.tsv")
    a = p.parse_args()
    return effgate.run_gate(a, measure(a.dir), "web-size", "bytes")


if __name__ == "__main__":
    sys.exit(main())
