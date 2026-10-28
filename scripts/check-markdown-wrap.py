#!/usr/bin/env python3
"""Markdown lint: a paragraph hard-wrapped over several lines (one paragraph is one line).

    scripts/check-markdown-wrap.py [--update|--init] [--baseline F] <project-dir>

Counts, per .md file, paragraphs of two or more consecutive prose lines. Code fences, front
matter, lists and their continuations, tables, headings, quotes, HTML, indented code and
lines ending in a hard break are not prose. Key `path::hard_wrap`, count = paragraphs.
Baseline: ci/efficiency/markdown-wrap.tsv.
"""
import re
import sys
import effgate

FENCE = re.compile(r"^\s*(```|~~~)")
NOT_PROSE = re.compile(r"^(\s|#|>|<|\||[-*+]\s|\d+[.)]\s|\[[^\]]+\]:|={3,}|-{3,}|\*{3,}|_{3,}|:::)")


def wrapped_paragraphs(lines):
    n = 0
    run = 0
    fence = False
    for i, l in enumerate(lines):
        if i == 0 and l.strip() == "---":
            fence = "front"
            continue
        if fence == "front":
            if l.strip() in ("---", "..."):
                fence = False
            continue
        if FENCE.match(l):
            fence = not fence
            run = 0
            continue
        prose = (not fence) and l.strip() != "" and not NOT_PROSE.match(l) and not l.endswith(("  ", "\\"))
        if prose:
            run += 1
            if run == 2:
                n += 1
        else:
            run = 0
    return n


def measure(root):
    cur = {}
    for rel in effgate.files_with(root, ".md"):
        n = wrapped_paragraphs(effgate.read_lines(root, rel))
        if n:
            cur[rel + "::hard_wrap"] = n
    return cur


def main():
    p = effgate.make_parser(__doc__.split("\n")[0], "ci/efficiency/markdown-wrap.tsv")
    a = p.parse_args()
    return effgate.run_gate(a, measure(a.dir), "markdown-wrap", "paragraphs")


if __name__ == "__main__":
    sys.exit(main())
