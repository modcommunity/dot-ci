#!/usr/bin/env python3
"""Duplicated code: normalised 30-line windows hashed across the files of one repository.

    scripts/check-duplication.py [--update|--init] [--baseline F] [--top N] <project-dir>
    scripts/check-duplication.py --cross <repo-dir> <repo-dir>...   (report only, run nightly)

Normalising drops blank lines, comments and indentation, so a re-indented or re-commented
copy still matches. A window is 30 consecutive normalised lines that occur at two or more
places; overlapping windows merge into one region. Per-repository gate key: the file, count:
lines of it that sit in a duplicated region, so a copy cannot be added and a file cannot get
worse. --cross lists the biggest clusters across repositories and never fails.
"""
import argparse
import sys
import effgate

WINDOW = 30


def normalised(lines):
    """[(original_line_number, text)] without blanks, comments and indentation."""
    out = []
    for i, l in enumerate(lines):
        t = effgate.code_of(l).strip()
        if t and t not in ("pass", "else:", ")", "]", "}"):
            out.append((i + 1, t))
    return out


def scan(roots):
    """roots: [(label, dir)]. Returns (per-file duplicated line sets, clusters)."""
    files = {}
    for label, root in roots:
        for rel in effgate.gd_files(root):
            norm = normalised(effgate.read_lines(root, rel))
            if len(norm) >= WINDOW:
                files[label + ":" + rel if len(roots) > 1 else rel] = norm
    seen = {}
    for f, norm in files.items():
        hs = [hash(t) for _, t in norm]
        for i in range(len(norm) - WINDOW + 1):
            # A window of mostly identical lines is a table or a run of the same call.
            if len(set(hs[i:i + WINDOW])) < WINDOW // 3:
                continue
            seen.setdefault(hash(tuple(hs[i:i + WINDOW])), []).append((f, i))
    # Overlapping hits in one file are a repeating table (a window matching itself shifted
    # by a line or two), not a copy: keep the first and skip hits closer than a window.
    for h, v in seen.items():
        keep = []
        for f, i in v:
            if not any(f == f2 and i - j < WINDOW for f2, j in keep):
                keep.append((f, i))
        seen[h] = keep
    seen = {h: v for h, v in seen.items() if len(v) > 1}
    # A run of consecutive windows whose other locations all shift by one is one copied block.
    bykey = {}
    for h, locs in seen.items():
        for f, i in locs:
            others = tuple(sorted((f2, j - i) for f2, j in locs if (f2, j) != (f, i)))
            bykey.setdefault((f, others), []).append(i)
    dup_lines = {}
    clusters = []
    for (f, others), idx in bykey.items():
        idx.sort()
        runs = [[idx[0], idx[0]]]
        for i in idx[1:]:
            if i == runs[-1][1] + 1:
                runs[-1][1] = i
            else:
                runs.append([i, i])
        for a, b in runs:
            norm = files[f]
            lines = [n for n, _ in norm[a:b + WINDOW]]
            dup_lines.setdefault(f, set()).update(lines)
            locs = [(f, a)] + [(f2, a + d) for f2, d in others]
            if (f, a) == min(locs):
                clusters.append((b - a + WINDOW, len(locs), [(g, files[g][j][0]) for g, j in locs]))
    return {f: len(s) for f, s in dup_lines.items()}, clusters


def show(clusters, n):
    for size, copies, locs in sorted(clusters, key=lambda c: -(c[0] * (c[1] - 1)))[:n]:
        print("  %4d lines x%d  %s" % (size, copies, "  ".join("%s:%d" % l for l in locs[:4]) + (" ..." if copies > 4 else "")))


def main():
    p = effgate.make_parser(__doc__.split("\n")[0], "ci/efficiency/duplication.tsv")
    p.add_argument("more", nargs="*", help="further repository directories (with --cross)")
    p.add_argument("--cross", action="store_true")
    a = p.parse_args()
    if a.cross:
        import os
        dirs = [a.dir] + a.more
        per, clusters = scan([(os.path.basename(os.path.abspath(d)), d) for d in dirs])
        xs = [c for c in clusters if len({l[0].split(":")[0] for l in c[2]}) > 1]
        print("duplication (cross): %d clusters, %d span repositories" % (len(clusters), len(xs)))
        show(xs, a.top or 20)
        return 0
    per, clusters = scan([("", a.dir)])
    if a.top:
        show(clusters, a.top)
    return effgate.run_gate(a, per, "duplication", "duplicated lines")


if __name__ == "__main__":
    sys.exit(main())
