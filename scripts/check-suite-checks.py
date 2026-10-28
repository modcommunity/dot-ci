#!/usr/bin/env python3
"""Suite lint: a `const CHECKS` that differs from the total the suite's last run reported.

    scripts/check-suite-checks.py [--update|--init] [--baseline F] <project-dir>

The expected count cannot be known statically (sections loop), so the gate compares each
suite's constant, plus the offset in its `_report(CHECKS + k)` call, with the "N passed, M
failed" total in `.godot/test-logs/<suite>.log` (N+M). A suite with no log is skipped, so
the gate only bites where a test run has happened (the nightly runner, a developer's tree);
CI without logs passes. Key `path::checks_drift`, count = absolute difference.
Baseline: ci/efficiency/suite-checks.tsv.
"""
import os
import re
import sys
import effgate

CONST = re.compile(r"^\s*const\s+(?:EXPECTED_)?CHECKS\s*(?::=|=|:\s*int\s*=)\s*(\d+)")
REPORT = re.compile(r"\b_report\(\s*(?:EXPECTED_)?CHECKS\s*(?:([+-])\s*(\d+))?\s*\)")
TOTAL = re.compile(r"(\d+) (?:passed|checks), (\d+) failed")


def log_total(root, rel):
    log = os.path.join(root, ".godot", "test-logs", os.path.splitext(os.path.basename(rel))[0] + ".log")
    if not os.path.isfile(log):
        return None
    last = None
    for l in effgate.read_lines(os.path.dirname(log), os.path.basename(log)):
        m = TOTAL.search(l)
        if m:
            last = int(m.group(1)) + int(m.group(2))
    return last


def measure(root):
    cur = {}
    for rel in effgate.gd_files(root):
        lines = effgate.read_lines(root, rel)
        const = next((int(m.group(1)) for m in map(CONST.match, lines) if m), None)
        if const is None:
            continue
        reported = log_total(root, rel)
        if reported is None:
            continue
        off = 0
        for m in map(REPORT.search, lines):
            if m and m.group(2):
                off = int(m.group(2)) * (-1 if m.group(1) == "-" else 1)
        diff = abs(const + off - reported)
        if diff:
            cur[rel + "::checks_drift"] = diff
    return cur


def main():
    p = effgate.make_parser(__doc__.split("\n")[0], "ci/efficiency/suite-checks.tsv")
    a = p.parse_args()
    return effgate.run_gate(a, measure(a.dir), "suite-checks", "checks")


if __name__ == "__main__":
    sys.exit(main())
