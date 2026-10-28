#!/usr/bin/env python3
"""Logging lint: a CHANNEL nothing logs through, and push_warning at runtime.

    scripts/check-logging.py [--update|--init] [--baseline F] <project-dir>

Kinds: channel_silent (a file declares `const CHANNEL` and never calls `DotLog.`),
push_warning (any call; it staples an unsuppressible backtrace on a runtime condition).
Key `path::kind`, count = sites. Baseline: ci/efficiency/logging.tsv.
"""
import re
import sys
import effgate

CHANNEL = re.compile(r"^\s*const\s+CHANNEL\b")
LOG = re.compile(r"\bDotLog\s*\.")
WARN = re.compile(r"\bpush_warning\s*\(")


def measure(root):
    cur = {}
    for rel in effgate.gd_files(root):
        code = [effgate.code_of(l) for l in effgate.read_lines(root, rel)]
        if any(CHANNEL.match(l) for l in code) and not any(LOG.search(l) for l in code):
            cur[rel + "::channel_silent"] = 1
        n = sum(1 for l in code if WARN.search(l))
        if n:
            cur[rel + "::push_warning"] = n
    return cur


def main():
    p = effgate.make_parser(__doc__.split("\n")[0], "ci/efficiency/logging.tsv")
    a = p.parse_args()
    return effgate.run_gate(a, measure(a.dir), "logging", "sites")


if __name__ == "__main__":
    sys.exit(main())
