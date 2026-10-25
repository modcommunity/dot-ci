#!/usr/bin/env python3
"""Which consumers, and which of their suites, a change in one repository can break.

    scripts/affected.sh [REPO] [--since REV | --staged | --files A B ...] [--root DIR]
                        [--json | --cmds] [--all-suites]

REPO is a directory name under the workspace root (the directory holding every clone) or a path;
default the current directory. The change is `git diff HEAD` plus untracked files unless --since
(`REV..HEAD`, for example HEAD~1 for the last commit) or --staged says otherwise.

A consumer is a sibling repository holding a symlink that resolves into REPO (a game's
`addons/dot_net`, a map repository's `maps/imported`). For each, the changed files' names (class_name,
file basename) are searched for in the consumer's own code, and the search is followed through the
files that reference them, three hops, until it reaches a suite (`examples/X.gd` or `X.tscn`). Output
per consumer: the suites to run, `all` when the change is used but no suite is reached by name
(conservative: run them all), or `parse` when nothing in the consumer names it, so the parse pass is
enough. Documentation-only changes affect nobody.
"""
import argparse
import json
import os
import re
import subprocess
import sys

DOC_ONLY = re.compile(r"(^|/)(docs?/|README|CLAUDE\.md|LICENSE|.*\.md$|.*\.import$|.*\.uid$)")
CLASS_NAME = re.compile(r"^\s*class_name\s+(\w+)", re.M)
HOPS = 3
SKIP_DIRS = {".git", ".godot", ".deps", "node_modules", "screenshots", "__pycache__"}
TEXT_EXT = (".gd", ".tscn", ".tres", ".gdshader", ".json", ".yml", ".cfg")


def git(repo, *args):
    r = subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True)
    return r.stdout if r.returncode == 0 else ""


def changed_files(repo, since, staged, files):
    if files:
        return files
    if since:
        out = git(repo, "diff", "--name-only", f"{since}..HEAD")
    elif staged:
        out = git(repo, "diff", "--name-only", "--cached")
    else:
        out = git(repo, "diff", "--name-only", "HEAD") + git(repo, "ls-files", "--others", "--exclude-standard")
    return sorted({f for f in out.splitlines() if f})


def old_or_new_text(repo, path, since):
    p = os.path.join(repo, path)
    if os.path.isfile(p):
        return open(p, errors="replace").read()
    return git(repo, "show", f"{(since + '~1') if since else 'HEAD'}:{path}")


def names_of(repo, files, since):
    names = set()
    for f in files:
        base = os.path.basename(f)
        stem = os.path.splitext(base)[0]
        if base.endswith(".gd"):
            names.update(CLASS_NAME.findall(old_or_new_text(repo, f, since)))
            names.add(stem)
        elif base.endswith(TEXT_EXT + (".res", ".png", ".ogg", ".glb", ".wav")):
            names.add(base)
    return {n for n in names if len(n) > 3}


def consumers(root, repo):
    """Sibling repositories with a symlink (depth 3) that resolves into repo."""
    real = os.path.realpath(repo)
    found = {}
    for name in sorted(os.listdir(root)):
        d = os.path.join(root, name)
        if os.path.realpath(d) == real or not os.path.isdir(os.path.join(d, ".git")):
            continue
        base_depth = d.count(os.sep)
        for cur, dirs, files in os.walk(d):
            dirs[:] = [x for x in dirs if x not in SKIP_DIRS and os.path.join(cur, x).count(os.sep) - base_depth < 3]
            for x in list(dirs) + files:
                p = os.path.join(cur, x)
                if os.path.islink(p):
                    tgt = os.path.realpath(p)
                    if tgt == real or tgt.startswith(real + os.sep):
                        found.setdefault(name, []).append(os.path.relpath(p, d))
                        if x in dirs:
                            dirs.remove(x)
    return found


def own_files(consumer):
    """Text files of the consumer itself: symlinks are not followed, so linked addons are not its code."""
    out = {}
    for cur, dirs, files in os.walk(consumer):
        dirs[:] = [x for x in dirs if x not in SKIP_DIRS and not os.path.islink(os.path.join(cur, x))]
        for f in files:
            p = os.path.join(cur, f)
            if f.endswith(TEXT_EXT) and not os.path.islink(p):
                try:
                    out[os.path.relpath(p, consumer)] = open(p, errors="replace").read()
                except OSError:
                    pass
    return out


def suites_of(consumer):
    gs = os.path.join(consumer, "game.sh")
    if os.path.isfile(gs):
        m = re.search(r'^SUITES="([^"]*)"', open(gs, errors="replace").read(), re.M)
        if m:
            return m.group(1).split()
    ex = os.path.join(consumer, "examples")
    if os.path.isdir(ex):
        return sorted(f[:-5] for f in os.listdir(ex) if f.endswith(".tscn"))
    return []


def refs(files, names):
    pats = [re.compile(r"(?<![A-Za-z0-9_])" + re.escape(n) + r"(?![A-Za-z0-9_])") for n in names]
    return {p for p, t in files.items() if any(r.search(t) for r in pats)}


def analyse(root, repo, names, all_suites):
    out = []
    for cons, links in consumers(root, repo).items():
        cdir = os.path.join(root, cons)
        suites = suites_of(cdir)
        files = own_files(cdir)
        hit, frontier, seen = set(), set(names), set(names)
        for _ in range(HOPS):
            new = refs(files, frontier) - hit
            hit |= new
            frontier = set()
            for p in new:
                stem = os.path.splitext(os.path.basename(p))[0]
                frontier |= set(CLASS_NAME.findall(files[p])) | {stem}
            frontier = {n for n in frontier if len(n) > 3} - seen
            seen |= frontier
            if not frontier:
                break
        reached = [s for s in suites if f"examples/{s}.gd" in hit or f"examples/{s}.tscn" in hit]
        if all_suites and suites:
            plan, why = suites, "all (--all-suites)"
        elif reached:
            plan, why = reached, "reached by name"
        elif hit and suites:
            plan, why = suites, "all (used, no suite reached by name)"
        elif hit:
            plan, why = [], "used, repository has no suites"
        else:
            plan, why = [], "parse"
        direct = sorted(p for p in hit if p in refs(files, names))[:6]
        out.append({"consumer": cons, "via": sorted(links)[:3], "suites": plan, "why": why,
                    "files_using": len(hit), "sample": direct, "has_game_sh": os.path.isfile(os.path.join(cdir, "game.sh"))})
    return out


def command(c):
    d = c["consumer"]
    if c["suites"] and c["has_game_sh"]:
        return f"cd {d} && heavy -- timeout 1800 ./game.sh --no-parse test {' '.join(c['suites'])}"
    if c["suites"]:
        return f"cd {d} && # run examples: {' '.join(c['suites'])}"
    return f"cd {d} && # parse pass only (find . -name '*.gd' ... --check-only)"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("repo", nargs="?", default=".")
    ap.add_argument("--since")
    ap.add_argument("--staged", action="store_true")
    ap.add_argument("--files", nargs="+")
    ap.add_argument("--root")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--cmds", action="store_true")
    ap.add_argument("--all-suites", action="store_true")
    a = ap.parse_args()
    repo = a.repo
    if not os.path.isdir(repo):
        repo = os.path.join(a.root or os.path.expanduser("~/godot"), a.repo)
    repo = os.path.realpath(repo)
    if not os.path.isdir(os.path.join(repo, ".git")):
        sys.exit(f"affected: {repo} is not a repository")
    root = a.root or os.path.dirname(repo)
    files = changed_files(repo, a.since, a.staged, a.files)
    code = [f for f in files if not DOC_ONLY.search(f)]
    result = {"repo": os.path.basename(repo), "changed": len(files), "code_changed": len(code), "consumers": []}
    names = names_of(repo, code, a.since)
    if code:
        result["consumers"] = analyse(root, repo, names, a.all_suites)
    result["names"] = sorted(names)[:40]
    if a.json:
        print(json.dumps(result, indent=1))
    elif a.cmds:
        for c in result["consumers"]:
            print(command(c))
    else:
        print(f"{result['repo']}: {len(files)} files changed, {len(code)} code; {len(names)} names to look for")
        if not code:
            print("  documentation or metadata only: nothing to run")
        for c in result["consumers"]:
            print(f"  {c['consumer']:<22} {c['why']:<42} {' '.join(c['suites']) or '-'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
