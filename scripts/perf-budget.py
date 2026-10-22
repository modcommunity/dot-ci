#!/usr/bin/env python3
"""Compare one perf-smoke result with its budget file. Used by perf-smoke.sh.

    perf-budget.py check|init|update <budget.json> <tolerance-pct> '<result json>'

Lower is better for every metric. Timed metrics get 2.5x the tolerance (run-to-run noise). `check` fails when a metric exceeds budget by more than the
tolerance; `update` lowers budgets and never raises one, the same ratchet as the other gates.
"""
import json
import os
import sys

METRICS = ("load_ms", "frame_ms", "nodes", "mem_mb")
# Timings move 30% between identical runs on a loaded box; counts and memory do not.
TIMED = ("load_ms", "frame_ms")
TIMED_FACTOR = 2.5


def main():
    mode, path, tol, raw = sys.argv[1], sys.argv[2], float(sys.argv[3]), sys.argv[4]
    cur = json.loads(raw)
    new = {k: cur[k] for k in ("scene",) + METRICS}
    if mode == "init":
        if os.path.exists(path):
            print("perf-smoke: %s exists; use --update" % path)
            return 1
        os.makedirs(os.path.dirname(path), exist_ok=True)
        json.dump(new, open(path, "w"), indent=2)
        print("wrote %s: %s" % (path, json.dumps(new)))
        return 0
    try:
        bud = json.load(open(path))
    except OSError:
        print("perf-smoke: no budget at %s (run --init); this run: %s" % (path, raw))
        return 1
    bad = []
    for k in METRICS:
        limit = bud[k] * (1 + tol * (TIMED_FACTOR if k in TIMED else 1) / 100.0)
        print("%-9s %9s  budget %9s  limit %9.3f" % (k, cur[k], bud[k], limit))
        if cur[k] > limit:
            bad.append(k)
    if mode == "update":
        for k in METRICS:
            bud[k] = min(bud[k], cur[k])
        json.dump(bud, open(path, "w"), indent=2)
        print("updated %s" % path)
    if bad:
        print("perf-smoke: REGRESSED %s (> %g%% over budget)" % (", ".join(bad), tol))
        return 1
    print("perf-smoke: ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
