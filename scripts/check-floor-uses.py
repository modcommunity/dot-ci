#!/usr/bin/env python3
"""Fails a game whose requires.floor.json is lower than a newer addon class its code uses.

    scripts/check-floor-uses.py <project-dir> [addons-root]

An addon's `<name>_api.gd` records each level as `# N: ClassA, ClassB ...` (a class named first in a list is an introduction; `Class.member` or `Class verbs` is a change). For every addon
in the floor file, a game script naming a class introduced above the floor must also ask the
host (`build_level("<addon>")` or `level_of("<addon>")`) somewhere in the same file. File-level
only: it cannot tell which use the guard covers, nor see classes reached by string, `load` of a
path, or config. Addons are read from <project>/addons, else <addons-root>/*/addons.
"""
import glob
import json
import os
import re
import sys

SKIP = ("addons", ".godot", ".git", "imported", "examples", "tools", "tests")
LEVEL_LINE = re.compile(r"^#\s*(\d+):\s*(.*)$")
ANY = re.compile(r"\b[A-Z][A-Za-z0-9]{3,}\b")
# A name starting a list item (`A, B`, `A (...)`, `A and B`, `A.`) is introduced there; `A skips`
# or `A.member` is a change to a class that already existed.
LISTED = re.compile(r"\b([A-Z][A-Za-z0-9]{3,})\b(?=\s*(?:[,;:)(]|$)|\s+and\b|\.(?:\s|$))")


def addon_dir(project, root, name):
    for pat in (os.path.join(project, "addons", name), os.path.join(root, "*", "addons", name)):
        hit = sorted(glob.glob(pat))
        if hit:
            return hit[0]
    return None


def introduced(adir, name):
    """Class name -> lowest level whose api-file comment names it (only real class_names)."""
    api = os.path.join(adir, name + "_api.gd")
    if not os.path.isfile(api):
        return {}
    declared = set()
    for p in glob.glob(os.path.join(adir, "**", "*.gd"), recursive=True):
        with open(p, encoding="utf-8", errors="replace") as f:
            declared.update(re.findall(r"^class_name\s+(\w+)", f.read(), re.M))
    out, seen, level = {}, {}, 1
    with open(api, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line.startswith("#"):
                continue
            m = LEVEL_LINE.match(line)
            if m:
                level = int(m.group(1))
            text = m.group(2) if m else line
            for c in ANY.findall(text):
                if c in declared:
                    seen[c] = min(seen.get(c, level), level)
            for c in LISTED.findall(text):
                if c in declared:
                    out[c] = min(out.get(c, level), level)
    return {c: min(n, seen[c]) for c, n in out.items() if min(n, seen[c]) > 1}


def scripts(project):
    for dp, dns, fns in os.walk(project):
        dns[:] = [d for d in dns if d not in SKIP and not d.startswith("wt-")]
        for fn in fns:
            if fn.endswith(".gd"):
                yield os.path.join(dp, fn)


def problems(project, root):
    fpath = os.path.join(project, "requires.floor.json")
    if not os.path.isfile(fpath):
        return [], []
    with open(fpath, encoding="utf-8") as f:
        floors = json.load(f).get("addons", {})
    out, undecided = [], []
    files = {p: re.sub(r"(?m)^\s*#.*$|\s#\s.*$", "", open(p, encoding="utf-8", errors="replace").read())
             for p in scripts(project)}
    for addon, floor in floors.items():
        adir = addon_dir(project, root, addon)
        if not adir:
            undecided.append(f"{addon}: addon not found, not checked")
            continue
        classes = {c: n for c, n in introduced(adir, addon).items() if n > floor}
        guard = re.compile(r"(build_level|level_of)\(\s*[\"']%s[\"']" % re.escape(addon))
        for p, text in files.items():
            if guard.search(text):
                continue
            via = any(g and re.search(r"[\"/]%s\"" % re.escape(os.path.basename(p)), t)
                      for q, t in files.items() if guard.search(t) for g in [1])
            for c, n in classes.items():
                if re.search(r"\b%s\b" % c, text):
                    if via:
                        undecided.append(f"{os.path.relpath(p, project)}: {c} ({addon} {n}) only behind a guarded loader, not verified")
                        break
                    out.append(f"{os.path.relpath(p, project)}: {c} needs {addon} {n}, floor is {floor}, no guard in file")
    return out, undecided


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2
    project = argv[1]
    root = argv[2] if len(argv) > 2 else os.path.dirname(os.path.abspath(project))
    out, undecided = problems(project, root)
    for u in undecided:
        print("note: " + u)
    if out:
        print("FAIL requires.floor.json below the level the code uses:\n" + "\n".join(sorted(out)), file=sys.stderr)
        return 1
    print("floor uses ok")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
