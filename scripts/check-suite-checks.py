#!/usr/bin/env python3
"""Suite lint: a `const CHECKS` that differs from the total the suite's last run reported.

    scripts/check-suite-checks.py [--update|--init] [--baseline F] <project-dir>

The expected count cannot be known statically (sections loop), so the gate compares each
suite's constant, plus the offset in its `_report(CHECKS + k)` call, with the "N passed, M
failed" total in `.godot/test-logs/<suite>.log` (N+M). A suite with no log is skipped, so
the gate only bites where a test run has happened (the nightly runner, a developer's tree);
CI without logs passes. `const CHECKS` may be an expression over ints and other consts
in the file (safe AST arithmetic, no eval); anything else is skipped with a note. A log older than
the script is skipped ("log older than script, rerun"). Key `path::checks_drift`, count = absolute difference.
Baseline: ci/efficiency/suite-checks.tsv.
"""
import ast
import os
import re
import sys
import effgate

CONST_RE = re.compile(r"^\s*const\s+([A-Za-z_]\w*)\s*(?::\s*int\s*=|:=|=)\s*(.+?)\s*(?:#.*)?$")
TOTAL = re.compile(r"(\d+) (?:passed|checks), (\d+) failed")
OPS = {ast.Add: lambda a, b: a + b, ast.Sub: lambda a, b: a - b, ast.Mult: lambda a, b: a * b,
       ast.Div: lambda a, b: a // b, ast.FloorDiv: lambda a, b: a // b}


def evaluate(expr, consts, depth=0):
    """Integer value of a constant expression, or None when it is not one (unknown name, call, ternary)."""
    try:
        tree = ast.parse(expr.strip(), mode="eval").body
    except SyntaxError:
        return None

    def ev(n, depth):
        if depth > 20:
            return None
        if isinstance(n, ast.Constant) and type(n.value) is int:
            return n.value
        if isinstance(n, ast.Name):
            return evaluate(consts[n.id], consts, depth + 1) if n.id in consts else None
        if isinstance(n, ast.UnaryOp) and isinstance(n.op, (ast.USub, ast.UAdd)):
            v = ev(n.operand, depth)
            return None if v is None else (-v if isinstance(n.op, ast.USub) else v)
        if isinstance(n, ast.BinOp) and type(n.op) in OPS:
            l, r = ev(n.left, depth), ev(n.right, depth)
            if l is None or r is None or (r == 0 and not isinstance(n.op, (ast.Add, ast.Sub, ast.Mult))):
                return None
            return OPS[type(n.op)](l, r)
        return None

    return ev(tree, depth)


def call_args(line, start):
    """Top-level comma-separated arguments of the call whose '(' is at `start`, or None if unbalanced."""
    depth, args, cur = 0, [], ""
    for ch in line[start:]:
        if ch == "(":
            depth += 1
            if depth == 1:
                continue
        elif ch == ")":
            depth -= 1
            if depth == 0:
                args.append(cur)
                return args
        elif ch == "," and depth == 1:
            args.append(cur)
            cur = ""
            continue
        cur += ch
    return None


def report_exprs(line):
    """Expressions the suite compares its CHECKS against: _report(E), _report_sections(..., E), `== E`, `!= E`."""
    out = []
    for m in re.finditer(r"\b_report(_sections)?\(", line):
        args = call_args(line, m.end() - 1)
        if args:
            out.append(args[-1])
    for m in re.finditer(r"[!=]=\s*([^:]+?)\s*:?\s*$", line):
        if "CHECKS" in m.group(1):
            out.append(m.group(1))
    return out


def log_total(root, rel):
    """(total, log path) of the suite's last run, or None."""
    log = os.path.join(root, ".godot", "test-logs", os.path.splitext(os.path.basename(rel))[0] + ".log")
    if not os.path.isfile(log):
        return None
    last = None
    for l in effgate.read_lines(os.path.dirname(log), os.path.basename(log)):
        m = TOTAL.search(l)
        if m:
            last = int(m.group(1)) + int(m.group(2))
    return None if last is None else (last, log)


def note(msg):
    print("note: " + msg, file=sys.stderr)


def measure(root):
    cur = {}
    for rel in effgate.gd_files(root):
        lines = effgate.read_lines(root, rel)
        consts = {}
        for m in map(CONST_RE.match, lines):
            if m:
                consts[m.group(1)] = m.group(2)
        name = next((n for n in ("CHECKS", "EXPECTED_CHECKS") if n in consts), None)
        if name is None:
            continue
        got = log_total(root, rel)
        if got is None:
            continue
        reported, log = got
        const = evaluate(consts[name], consts)
        if const is None:
            note("%s: %s is not a constant expression (%s), skipped" % (rel, name, consts[name]))
            continue
        if os.path.getmtime(log) < os.path.getmtime(os.path.join(root, rel)):
            note("%s: log older than script, rerun" % rel)
            continue
        off = 0
        for line in lines:
            for e in report_exprs(line):
                v = evaluate(e, dict(consts, **{"CHECKS": consts[name]}))
                if v is not None and name in e:
                    off = v - const
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
