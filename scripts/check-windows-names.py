#!/usr/bin/env python3
"""Fails a repository whose tracked paths cannot be checked out on Windows.

    scripts/check-windows-names.py <project-dir>      # paths from git ls-files
    scripts/check-windows-names.py --stdin            # one path per line

Flags: any of * ? : " < > | or a backslash; a component ending in a dot or space; a
reserved device name (CON, PRN, AUX, NUL, COM1-9, LPT1-9, with or without extension);
two paths that differ only by case.
"""
import re
import subprocess
import sys

BAD_CHARS = re.compile(r'[*?:"<>|\\\x00-\x1f]')
RESERVED = re.compile(r"^(con|prn|aux|nul|com[1-9]|lpt[1-9])(\..*)?$", re.I)


def problems(paths):
    out = []
    seen = {}
    for p in paths:
        for part in p.split("/"):
            if BAD_CHARS.search(part):
                out.append(f"{p}: forbidden character in '{part}'")
            elif part.endswith((".", " ")):
                out.append(f"{p}: '{part}' ends in a dot or space")
            elif RESERVED.match(part):
                out.append(f"{p}: '{part}' is a reserved device name")
        key = p.lower()
        if key in seen and seen[key] != p:
            out.append(f"{p}: differs only by case from {seen[key]}")
        seen.setdefault(key, p)
    return out


def main(argv):
    if argv[1:] == ["--stdin"]:
        paths = [l.rstrip("\n") for l in sys.stdin if l.strip()]
    else:
        d = argv[1] if len(argv) > 1 else "."
        r = subprocess.run(["git", "-C", d, "ls-files", "-z"], capture_output=True)
        if r.returncode:
            print(f"git ls-files failed in {d}", file=sys.stderr)
            return 2
        paths = [x for x in r.stdout.decode("utf-8", "surrogateescape").split("\0") if x]
    bad = problems(paths)
    if bad:
        print("FAIL paths that cannot be checked out on Windows:", file=sys.stderr)
        print("\n".join(bad), file=sys.stderr)
        return 1
    print(f"windows names ok ({len(paths)} paths)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
