#!/usr/bin/env python3
"""Fails a repository that evaluates a JavaScript string from the game.

    scripts/check-no-js-eval.py <project-dir>      # files from git ls-files
    scripts/check-no-js-eval.py --stdin            # "path<TAB>line" is not read; one path per line

The web game origin's CSP has no 'unsafe-eval', so JavaScriptBridge.eval throws EvalError and the
engine swallows it: every read is null. Flags, in .gd, JavaScriptBridge.eval, DotWeb.eval and a
call("eval"; in .js/.mjs/.html, eval( and new Function(. Comment text is ignored. A line that must
keep one (a harness that runs where no CSP applies) says `js-eval: allow <reason>` in a comment.
"""
import re
import subprocess
import sys

GD = re.compile(r"""JavaScriptBridge\s*\.\s*eval\b|DotWeb\s*\.\s*eval\w*\b|call\(\s*["']eval["']""")
JS = re.compile(r"(?<![\w.$])eval\s*\(|new\s+Function\s*\(")
ALLOW = "js-eval: allow"


def code_part(line, ext):
    # A '#' or '//' inside a string is rare enough here that cutting at the first one is the honest approximation.
    marker = "#" if ext == "gd" else "//"
    i = line.find(marker)
    return line if i < 0 else line[:i]


def problems(path, text):
    ext = path.rsplit(".", 1)[-1]
    if ext not in ("gd", "js", "mjs", "html"):
        return []
    pat = GD if ext == "gd" else JS
    out = []
    in_block = False
    for n, line in enumerate(text.splitlines(), 1):
        if ALLOW in line:
            continue
        if ext != "gd":
            if in_block:
                if "*/" in line:
                    in_block = False
                    line = line.split("*/", 1)[1]
                else:
                    continue
            if "/*" in line and "*/" not in line:
                in_block = True
                line = line.split("/*", 1)[0]
        if pat.search(code_part(line, ext)):
            out.append(f"{path}:{n}: evaluates a string; the game origin's CSP refuses it ({line.strip()[:80]})")
    return out


def main(argv):
    if argv[1:] == ["--stdin"]:
        root = "."
        paths = [l.rstrip("\n") for l in sys.stdin if l.strip()]
    else:
        root = argv[1] if len(argv) > 1 else "."
        paths = subprocess.run(["git", "-C", root, "ls-files"], capture_output=True, text=True,
                               check=True).stdout.splitlines()
    bad = []
    for p in paths:
        if "/.godot/" in "/" + p or p.startswith("build/"):
            continue
        try:
            with open(f"{root}/{p}", encoding="utf-8") as f:
                bad += problems(p, f.read())
        except (OSError, UnicodeDecodeError):
            continue
    for b in bad:
        print(b)
    if bad:
        print(f"{len(bad)} JavaScript evaluation(s). Add a named function to dot-core's web/dot_web.js and call it through DotWeb.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
