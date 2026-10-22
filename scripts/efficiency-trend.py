#!/usr/bin/env python3
"""Nightly trend of the efficiency report: append totals to a history file and print the change.

    scripts/efficiency-report.sh | scripts/efficiency-trend.py [--history F] [--strict] [--no-append]

Reads the table efficiency-report.sh prints on stdin. The history is one JSON line per run
(default ~/.local/state/dot-ci/efficiency-history.jsonl). Output is a few lines for the nightly
panel: each total, its previous value and the delta. With --strict the exit code is 1 when size
or hazards grew since the last run, so a regression is a failed check rather than a number.
"""
import argparse
import json
import os
import re
import sys
import time

DEFAULT = os.path.expanduser("~/.local/state/dot-ci/efficiency-history.jsonl")
ROW = re.compile(r"^(\S+)\s+(\d+)\s+(\d+)\s+(\d+)\s+([\d.]+)%\s*$")
DUP = re.compile(r"(\d+)\s+(?:duplicate\s+)?clusters?", re.I)
LOWER_IS_BETTER = ("size", "hazards", "dup_clusters")


def parse(text):
    t = {"repos": 0, "size": 0, "hazards": 0, "lines": 0, "dup_clusters": 0}
    com = 0.0
    for line in text.splitlines():
        m = ROW.match(line.strip())
        if m:
            t["repos"] += 1
            t["size"] += int(m.group(2))
            t["hazards"] += int(m.group(3))
            t["lines"] += int(m.group(4))
            com += float(m.group(5)) * int(m.group(4))
        elif line.startswith("duplication"):
            d = DUP.search(line)
            if d:
                t["dup_clusters"] = int(d.group(1))
    t["comment_pct"] = round(com / t["lines"], 2) if t["lines"] else 0.0
    return t


def last(path):
    try:
        with open(path, encoding="utf-8") as fh:
            rows = [l for l in fh if l.strip()]
        return json.loads(rows[-1]) if rows else None
    except (OSError, ValueError):
        return None


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--history", default=DEFAULT)
    p.add_argument("--strict", action="store_true")
    p.add_argument("--no-append", action="store_true")
    a = p.parse_args()
    cur = parse(sys.stdin.read())
    if not cur["repos"]:
        print("efficiency-trend: no report rows on stdin")
        return 2
    prev = last(a.history)
    worse = []
    for k in ("repos", "lines", "comment_pct", "size", "hazards", "dup_clusters"):
        old = prev.get(k) if prev else None
        delta = "" if old is None else " (%+g)" % round(cur[k] - old, 2)
        print("%-13s %s%s" % (k, cur[k], delta))
        if old is not None and k in LOWER_IS_BETTER and cur[k] > old:
            worse.append(k)
    if not a.no_append:
        os.makedirs(os.path.dirname(a.history), exist_ok=True)
        with open(a.history, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(dict(cur, ts=int(time.time()))) + "\n")
    if worse:
        print("REGRESSED: " + ", ".join(worse))
        return 1 if a.strict else 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
