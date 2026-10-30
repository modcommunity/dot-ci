#!/usr/bin/env python3
"""Logging lint: a CHANNEL nothing logs through, and push_warning at runtime.

    scripts/check-logging.py [--update|--init] [--baseline F] <project-dir>

Kinds: print (print/print_rich in runtime code; examples/, tools/, qa/, editor/, tests and SceneTree/MainLoop scripts are program output and exempt),
channel_silent (a file declares `const CHANNEL` and never calls `DotLog.`),
push_warning (any call; it staples an unsuppressible backtrace on a runtime condition).
A base that declares CHANNEL counts a DotLog use in any subclass (extends by path or class_name).
DotLog's own file and lines marked `# check-logging: allow push_warning` / `allow print` are exempt.
Key `path::kind`, count = sites. Baseline: ci/efficiency/logging.tsv.
"""
import os
import re
import sys
import effgate

CHANNEL = re.compile(r"^\s*const\s+CHANNEL\b")
LOG = re.compile(r"\bDotLog\s*\.")
WARN = re.compile(r"\bpush_warning\s*\(")


ALLOW = "check-logging: allow push_warning"
ALLOW_PRINT = "check-logging: allow print"
PRINT = re.compile(r"(?<![\w.])print(_rich)?\s*\(")
OUTPUT_DIRS = ("examples/", "tools/", "test/", "tests/", "addons/gut/")
MAIN_LOOP = re.compile(r"^\s*extends\s+(SceneTree|MainLoop)\b")
CLASS_NAME = re.compile(r"^\s*class_name\s+(\w+)")
EXTENDS_PATH = re.compile(r"""^\s*extends\s+["']([^"']+)["']""")
EXTENDS_CLASS = re.compile(r"^\s*extends\s+([A-Za-z_]\w*)")


def parent_of(rel, code, classes):
    """The same-repo file a script extends (by path or class_name), or None."""
    for l in code:
        m = EXTENDS_PATH.match(l)
        if m:
            path = m.group(1)
            if path.startswith("res://"):
                return path[6:]
            return os.path.normpath(os.path.join(os.path.dirname(rel), path))
        m = EXTENDS_CLASS.match(l)
        if m:
            return classes.get(m.group(1))
    return None


def measure(root):
    cur = {}
    raw = {}
    code = {}
    for rel in effgate.gd_files(root):
        raw[rel] = effgate.read_lines(root, rel)
        code[rel] = [effgate.code_of(l) for l in raw[rel]]
    classes = {}
    for rel, lines in code.items():
        for l in lines:
            m = CLASS_NAME.match(l)
            if m:
                classes[m.group(1)] = rel
                break
    # A file's log use counts for every ancestor: a base that holds CHANNEL while the subclass logs.
    logs = {rel for rel, lines in code.items() if any(LOG.search(l) for l in lines)}
    for rel in list(logs):
        seen = set()
        up = parent_of(rel, raw[rel], classes)
        while up and up in code and up not in seen:
            seen.add(up)
            logs.add(up)
            up = parent_of(up, raw[up], classes)
    for rel, lines in code.items():
        if any(CHANNEL.match(l) for l in lines) and rel not in logs:
            cur[rel + "::channel_silent"] = 1
        # DotLog's own engine mirror is the one legitimate push_warning.
        own = any(CLASS_NAME.match(l) and CLASS_NAME.match(l).group(1) == "DotLog" for l in lines)
        n = sum(1 for l, r in zip(lines, raw[rel]) if WARN.search(l) and ALLOW not in r)
        if n and not own:
            cur[rel + "::push_warning"] = n
        if not rel.startswith(OUTPUT_DIRS) and "/examples/" not in rel and "/tools/" not in rel \
                and "/qa/" not in rel and "/editor/" not in rel \
                and not any(MAIN_LOOP.match(l) for l in lines):
            n = sum(1 for l, r in zip(lines, raw[rel]) if PRINT.search(l) and ALLOW_PRINT not in r)
            if n and not own:
                cur[rel + "::print"] = n
    return cur


def main():
    p = effgate.make_parser(__doc__.split("\n")[0], "ci/efficiency/logging.tsv")
    a = p.parse_args()
    return effgate.run_gate(a, measure(a.dir), "logging", "sites")


if __name__ == "__main__":
    sys.exit(main())
