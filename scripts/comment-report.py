#!/usr/bin/env python3
"""Comment-share report per repository, report only (never fails).

    scripts/comment-report.py [--tsv] [repo-dir ...]     (default: every ~/godot/*/ with a .git)

Per repository over tracked .gd files: lines, comment-only lines, `##` doc share, comment bytes
and the lint's findings (check-comments.py kinds, baseline ignored). Grouped addon / game
(dirs starting game-, mg-), family total last; the target is a comment share under 12%.
"""
import glob
import importlib.util
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import effgate  # noqa: E402

spec = importlib.util.spec_from_file_location("check_comments", os.path.join(HERE, "check-comments.py"))
cc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cc)

KINDS = ("long_block", "banner", "commented_code", "history")


def stats(root):
    lines = com = doc = cbytes = 0
    for rel in effgate.gd_files(root):
        for line in effgate.read_lines(root, rel):
            lines += 1
            s = line.strip()
            if s.startswith("#") and not s.startswith("#!"):
                com += 1
                cbytes += len(line) + 1
                if s.startswith("##"):
                    doc += 1
    flags = dict.fromkeys(KINDS, 0)
    for k, n in cc.measure(root).items():
        flags[k.rsplit("::", 1)[1]] += n
    return lines, com, doc, cbytes, flags


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    tsv = "--tsv" in sys.argv
    dirs = args or sorted(d.rstrip("/") for d in glob.glob(os.path.expanduser("~/godot/*/"))
                          if os.path.exists(os.path.join(d, ".git")))
    rows = []
    for d in dirs:
        d = d.rstrip("/")
        name = os.path.basename(d)
        lines, com, doc, cb, fl = stats(d)
        if lines:
            rows.append(("game" if name.startswith(("game-", "mg-")) else "addon", name, lines, com, doc, cb, fl))
    fmt = "%-6s %-28s %8s %7s %6s %6s %6s %6s %6s %6s %6s"
    head = ("kind", "repo", "lines", "cmt", "cmt%", "doc%", "block", "banner", "code", "hist", "KB")
    print("\t".join(head) if tsv else fmt % head)

    def emit(g, name, sub):
        lines, com, doc, cb = (sum(r[i] for r in sub) for i in (2, 3, 4, 5))
        fl = {k: sum(r[6][k] for r in sub) for k in KINDS}
        vals = (g, name, lines, com, "%.1f" % (100 * com / lines), "%.1f" % (100 * doc / lines),
                fl["long_block"], fl["banner"], fl["commented_code"], fl["history"], cb // 1024)
        print("\t".join(map(str, vals)) if tsv else fmt % vals)

    for g in ("addon", "game"):
        sub = sorted((r for r in rows if r[0] == g), key=lambda r: -r[3] / r[2])
        for r in sub:
            emit(g, r[1], [r])
        if sub:
            emit(g, "TOTAL " + g, sub)
    if rows:
        emit("all", "FAMILY", rows)
    return 0


if __name__ == "__main__":
    sys.exit(main())
