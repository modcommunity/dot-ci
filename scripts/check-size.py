#!/usr/bin/env python3
"""Size budgets: a .gd file over 800 lines, a function over 80 lines.

    scripts/check-size.py [--update|--init] [--baseline F] [--top N] <project-dir>

Keys are `path` and `path::func` (a repeated name in one file gets `#2`), counts are lines.
A violation must be in the baseline (ci/efficiency/size.tsv) at no more than its recorded
size, so a long function can be neither added nor grown. See effgate.py.
"""
import sys
import effgate

MAX_FILE = 800
MAX_FUNC = 80


def measure(root):
    cur = {}
    for rel in effgate.gd_files(root):
        lines = effgate.read_lines(root, rel)
        n = len(lines) - (1 if lines and lines[-1] == "" else 0)
        if n > MAX_FILE:
            cur[rel] = n
        seen = {}
        for name, a, b in effgate.functions(lines):
            ln = b - a + 1
            seen[name] = seen.get(name, 0) + 1
            if ln > MAX_FUNC:
                k = "%s::%s" % (rel, name) + ("#%d" % seen[name] if seen[name] > 1 else "")
                cur[k] = ln
    return cur


def main():
    p = effgate.make_parser(__doc__.split("\n")[0], "ci/efficiency/size.tsv")
    a = p.parse_args()
    return effgate.run_gate(a, measure(a.dir), "size", "lines")


if __name__ == "__main__":
    sys.exit(main())
