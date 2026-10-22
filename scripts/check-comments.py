#!/usr/bin/env python3
"""Comment lint: comment blocks over 3 lines, section banners, commented-out code, history.

    scripts/check-comments.py [--update|--init] [--baseline F] [--top N] <project-dir>

Kinds: long_block (a run of more than 3 full-line comments; counts blocks), banner
(`# ----`, `# ==== Title ====`), commented_code (a single-# line shaped like a statement),
history (a date, "found by", "used to", "formerly", "previously"). Key `path::kind`, count =
sites. A text scan, so it is a ratchet for new comments, not a verdict. Baseline:
ci/efficiency/comments.tsv.
"""
import re
import sys
import effgate

MAX_BLOCK = 3
BANNER = re.compile(r"^#+\s*(?:[-=*~_#]{4,}|.*[-=*~_]{4,}\s*$)")
HISTORY = re.compile(r"\b20\d\d-\d\d-\d\d\b|\bfound by\b|\bused to\b|\bformerly\b|\bpreviously\b", re.I)
CODE = [
    re.compile(r"^(?:if|elif|for|while|match|func|class)\b.*:\s*$"),
    re.compile(r"^else\s*:\s*$"),
    re.compile(r"^(?:var|const|signal|extends|class_name)\s+\w+"),
    re.compile(r"^[\w.]+\(.*\)\s*$"),
    re.compile(r"^[\w.\[\]\"']+\s*(?:[-+*/|&]|:)?=\s*[^=\s]"),
    re.compile(r"^return\b.*[()=\[]"),
]


def measure(root):
    cur = {}

    def bump(rel, kind, n=1):
        k = "%s::%s" % (rel, kind)
        cur[k] = cur.get(k, 0) + n

    for rel in effgate.gd_files(root):
        run = 0
        for line in effgate.read_lines(root, rel) + [""]:
            s = line.strip()
            if not s.startswith("#") or s.startswith("#!"):
                if run > MAX_BLOCK:
                    bump(rel, "long_block")
                run = 0
                continue
            run += 1
            if BANNER.match(s):
                bump(rel, "banner")
            if HISTORY.search(s):
                bump(rel, "history")
            if not s.startswith(("##", "#:", "#region", "#endregion")):
                body = s.lstrip("#").strip()
                if body and any(rx.match(body) for rx in CODE):
                    bump(rel, "commented_code")
    return cur


def main():
    p = effgate.make_parser(__doc__.split("\n")[0], "ci/efficiency/comments.tsv")
    a = p.parse_args()
    return effgate.run_gate(a, measure(a.dir), "comments", "sites")


if __name__ == "__main__":
    sys.exit(main())
