#!/usr/bin/env python3
"""Per-frame hazards inside _process / _physics_process and the functions they call by name
in the same file (transitively).

    scripts/check-frame-hazards.py [--update|--init] [--baseline F] [--top N] <project-dir>

Kinds: node_lookup ($Path, get_node*), find_children (find_child/find_children),
group_lookup (get_nodes_in_group, get_first_node_in_group), load (load() and
ResourceLoader.load; preload is resolved at compile time, so it is not a cost),
alloc_array / alloc_dict (a var initialised from a literal), string_build (+ or += with
a string, str(), .format(), "..." % x), duplicate (.duplicate()), connect_unguarded
(.connect( in a function with no is_connected). Key `path::func::kind`, count = sites.
It is a text scan with no types, so it is a ratchet for new code, not a proof; calls on
other objects (`x.update()`) are not followed, only bare `name(` and `self.name(`.
"""
import re
import sys
import effgate

ROOTS = {"_process", "_physics_process"}

PATTERNS = [
    ("node_lookup", re.compile(r"\$[\w\"'/%]|\bget_node(?:_or_null)?\s*\(")),
    ("find_children", re.compile(r"\bfind_childre?n?\s*\(")),
    ("group_lookup", re.compile(r"\bget_(?:first_)?nodes?_in_group\s*\(")),
    ("load", re.compile(r"(?<![\w.])load\s*\(|\bResourceLoader\.load\s*\(")),
    ("alloc_array", re.compile(r"\bvar\s+\w+\s*(?::\s*[\w\[\]]+\s*)?:?=\s*\[")),
    ("alloc_dict", re.compile(r"\bvar\s+\w+\s*(?::\s*[\w\[\],\s]+\s*)?:?=\s*\{")),
    ("string_build", re.compile(r"\+=?\s*(?:\"|')|(?:\"|')\s*\+|\bstr\s*\(|\.format\s*\(|(?:\"|')\s*%\s*[\w\[(]")),
    ("duplicate", re.compile(r"\.duplicate\s*\(")),
]
CONNECT = re.compile(r"\.connect\s*\(")


def frame_functions(lines):
    funcs = effgate.functions(lines)
    by_name = {}
    for f in funcs:
        by_name.setdefault(f[0], []).append(f)
    calls = {}
    names = set(by_name)
    call_re = re.compile(r"(?<![\w.])(?:self\.)?(\w+)\s*\(")
    for name, a, b in funcs:
        c = calls.setdefault(name, set())
        for i in range(a + 1, b + 1):
            for m in call_re.finditer(effgate.code_of(lines[i])):
                if m.group(1) in names and m.group(1) != name:
                    c.add(m.group(1))
    reach = set(n for n in names if n in ROOTS)
    todo = list(reach)
    while todo:
        for c in calls.get(todo.pop(), ()):
            if c not in reach:
                reach.add(c)
                todo.append(c)
    return [f for f in funcs if f[0] in reach]


def measure(root):
    cur = {}
    for rel in effgate.gd_files(root):
        lines = effgate.read_lines(root, rel)
        if not any(l.lstrip().startswith(("func _process", "func _physics_process")) for l in lines):
            continue
        for name, a, b in frame_functions(lines):
            body = [effgate.code_of(l) for l in lines[a + 1:b + 1]]
            for kind, rx in PATTERNS:
                n = sum(1 for l in body if rx.search(l))
                if n:
                    cur["%s::%s::%s" % (rel, name, kind)] = n
            conn = sum(1 for l in body if CONNECT.search(l))
            if conn and not any("is_connected" in l for l in body):
                cur["%s::%s::connect_unguarded" % (rel, name)] = conn
    return cur


def main():
    p = effgate.make_parser(__doc__.split("\n")[0], "ci/efficiency/frame-hazards.tsv")
    a = p.parse_args()
    return effgate.run_gate(a, measure(a.dir), "frame-hazards", "sites")


if __name__ == "__main__":
    sys.exit(main())
