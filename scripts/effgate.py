"""Shared pieces of the efficiency gates (check-size.py, check-frame-hazards.py,
check-duplication.py): listing a repository's scripts, cutting a GDScript file into
functions, and the baseline ratchet.

The ratchet is the point. A baseline maps a key to the count it is allowed (lines, hazards,
duplicated lines). A run fails when a key is absent from the baseline or above its count, so
a new violation cannot land; --update only ever lowers counts and drops fixed keys, and
refuses (writes nothing) when it would have to add or raise one. --init writes a first
baseline and refuses when one exists. Baselines therefore only shrink, by construction.
"""
import argparse
import os
import re
import subprocess
import sys

SKIP_DIRS = {".git", ".godot", ".deps", "addons", ".import", "node_modules"}


def gd_files(root):
    return files_with(root, ".gd")


def files_with(root, ext):
    """Tracked files ending in ext, relative to root. git ls-files when it is a repository (linked
    addons and caches are not tracked, which is what we want), else a walk that skips them."""
    if os.path.exists(os.path.join(root, ".git")):
        r = subprocess.run(["git", "-C", root, "ls-files", "-z", "--", "*" + ext],
                           capture_output=True, text=True)
        if r.returncode == 0:
            return sorted(p for p in r.stdout.split("\0") if p and os.path.isfile(os.path.join(root, p)))
    out = []
    for d, dirs, files in os.walk(root):
        dirs[:] = [x for x in dirs if x not in SKIP_DIRS]
        for f in files:
            if f.endswith(ext):
                out.append(os.path.relpath(os.path.join(d, f), root))
    return sorted(out)


def read_lines(root, rel):
    with open(os.path.join(root, rel), encoding="utf-8", errors="replace") as fh:
        return fh.read().split("\n")


_STR = re.compile(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'')


def code_of(line):
    """The line with string contents blanked and the comment removed."""
    s = _STR.sub(lambda m: m.group(0)[0] + m.group(0)[0], line)
    i = s.find("#")
    return s if i < 0 else s[:i]


def indent_of(line):
    return len(line) - len(line.lstrip(" \t"))


_FUNC = re.compile(r"^\s*(?:static\s+)?func\s+(\w+)\s*\(")


def functions(lines):
    """[(name, first_line_index, last_line_index)] for every func, nested classes included.
    A body is every following line indented deeper than the func line (blank and comment
    lines inside it count); its length is last-first+1 with trailing blanks trimmed."""
    out = []
    n = len(lines)
    for i, line in enumerate(lines):
        m = _FUNC.match(line)
        if not m:
            continue
        base = indent_of(line)
        end = i
        j = i + 1
        while j < n:
            t = lines[j]
            if t.strip() == "":
                j += 1
                continue
            if indent_of(t) <= base and not t.lstrip().startswith("#"):
                break
            end = j
            j += 1
        out.append((m.group(1), i, end))
    return out


def load_baseline(path):
    base = {}
    if path and os.path.isfile(path):
        with open(path, encoding="utf-8") as fh:
            for ln in fh:
                ln = ln.rstrip("\n")
                if not ln or ln.startswith("#"):
                    continue
                k, _, v = ln.rpartition("\t")
                base[k] = int(v)
    return base


def write_baseline(path, data, header):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("# " + header + "\n# Baselines only shrink: scripts/<gate> --update lowers or drops entries and refuses to add.\n")
        for k in sorted(data):
            fh.write("%s\t%d\n" % (k, data[k]))


def make_parser(desc, default_baseline):
    p = argparse.ArgumentParser(description=desc)
    p.add_argument("dir", nargs="?", default=".")
    p.add_argument("--baseline", default=None, help="baseline file (default: <dir>/%s)" % default_baseline)
    p.add_argument("--update", action="store_true", help="lower counts and drop fixed entries; refuses to add")
    p.add_argument("--init", action="store_true", help="write a first baseline; refuses if one exists")
    p.add_argument("--no-baseline", action="store_true", help="ignore the baseline: list everything, fail on any")
    p.add_argument("--top", type=int, default=0, help="print the N worst entries even when passing")
    p.set_defaults(_default=default_baseline)
    return p


def run_gate(args, current, label, unit):
    """current: {key: count}. Applies --init / --update / the ratchet; returns the exit code."""
    root = args.dir
    path = args.baseline or os.path.join(root, args._default)
    if args.init:
        if os.path.exists(path):
            print("refusing --init: %s exists (use --update to shrink it)" % path, file=sys.stderr)
            return 1
        write_baseline(path, current, label)
        print("wrote %s (%d entries)" % (path, len(current)))
        return 0
    base = {} if args.no_baseline else load_baseline(path)
    if args.update:
        added = [k for k in current if k not in base]
        raised = [k for k in current if k in base and current[k] > base[k]]
        if added or raised:
            for k in added + raised:
                print("FAIL %s: %s %d (baseline %s)" % (label, k, current[k], base.get(k, "none")), file=sys.stderr)
            print("refusing --update: it would add or raise entries; fix those first", file=sys.stderr)
            return 1
        new = {k: current[k] for k in current if k in base}
        write_baseline(path, new, label)
        print("%s: baseline now %d entries (was %d)" % (label, len(new), len(base)))
        return 0
    bad = sorted(k for k in current if k not in base or current[k] > base[k])
    for k in bad:
        print("FAIL %s: %s %d %s (baseline %s)" % (label, k, current[k], unit, base.get(k, "none")), file=sys.stderr)
    stale = len([k for k in base if k not in current])
    if args.top:
        for k, v in sorted(current.items(), key=lambda kv: -kv[1])[:args.top]:
            print("  %6d  %s" % (v, k))
    print("%s: %d violations known, %d new/worse, %d baseline entries now fixed (run --update)" %
          (label, len(current), len(bad), stale))
    return 1 if bad else 0
