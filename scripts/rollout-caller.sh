#!/usr/bin/env bash
#
# Turn the efficiency gates on for ONE caller repository: baselines first, then the flags.
#
#   scripts/rollout-caller.sh <repo-dir>
#
# 1. Skips (exit 3) a dirty tree, and (exit 0, reported) a repo without a ci.yml that calls dot-ci.
# 2. Runs each --init that applies and whose baseline file is missing (never overwrites):
#    check-size, check-frame-hazards, check-duplication (when the repo has .gd files),
#    check-comments, check-logging, check-markdown-wrap, check-suite-checks, and
#    perf-smoke.sh --init for a game project (project.godot at the root, a game-* or mg-* name,
#    a plain res:// main scene). perf-smoke runs Godot: call this through `heavy --` .
# 3. Adds `efficiency: true`, `perf: true` (smoke.json exists), `hygiene: true` (logging,
#    markdown-wrap and suite-checks baselines exist) under `with:` in .github/workflows/ci.yml.
# 4. One plain `git commit`. Never pushes: push only after the dot-ci v1 tag has moved,
#    because @v1 rejects inputs it does not declare.
#
# Idempotent: a second run finds the baselines and flags in place and commits nothing.
# Exit: 0 done or nothing to do, 3 skipped (dirty tree), 1 an --init or the edit failed.
#
set -uo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo="${1:?usage: rollout-caller.sh <repo-dir>}"
[ -d "$repo/.git" ] || [ -f "$repo/.git" ] || { echo "rollout: $repo is not a git repository" >&2; exit 1; }
repo="$(cd "$repo" && pwd)"
name="$(basename "$repo")"
yml="$repo/.github/workflows/ci.yml"
say() { printf 'rollout %s: %s\n' "$name" "$*"; }

[ -f "$yml" ] && grep -q 'dot-ci/.github/workflows/validate.yml' "$yml" || { say "SKIP no ci.yml calling dot-ci"; exit 0; }
if [ -n "$(git -C "$repo" status --porcelain)" ]; then say "SKIP dirty tree"; exit 3; fi

rc=0
init() { # gate-script baseline-name
    local f="$repo/ci/efficiency/$2.tsv"
    [ -e "$f" ] && return 0
    if python3 "$here/$1" --init "$repo" >/dev/null 2>&1; then say "baseline $2"; else say "FAILED $1 --init"; rc=1; fi
}
gd="$(git -C "$repo" ls-files '*.gd' | head -1)"
if [ -n "$gd" ]; then
    init check-size.py size
    init check-frame-hazards.py frame-hazards
    init check-duplication.py duplication
    init check-comments.py comments
    init check-logging.py logging
    init check-suite-checks.py suite-checks
fi
init check-markdown-wrap.py markdown-wrap

smoke="$repo/ci/perf/smoke.json"
if [ ! -e "$smoke" ] && [ -f "$repo/project.godot" ]; then
    case "$name" in game-*|mg-*)
        scene="$(sed -n 's/^run\/main_scene="\(.*\)"/\1/p' "$repo/project.godot" | head -1)"
        case "$scene" in res://*.tscn)
            case "$scene" in res://uid://*) ;; *)
                if "$here/perf-smoke.sh" --init "$repo" >/dev/null 2>&1; then say "baseline perf smoke"; else say "FAILED perf-smoke --init"; rc=1; fi ;;
            esac ;;
        esac ;;
    esac
fi

flags=()
e="$repo/ci/efficiency"
[ -e "$e/size.tsv" ] && [ -e "$e/frame-hazards.tsv" ] && [ -e "$e/duplication.tsv" ] && flags+=(efficiency)
[ -e "$smoke" ] && flags+=(perf)
[ -e "$e/logging.tsv" ] && [ -e "$e/markdown-wrap.tsv" ] && [ -e "$e/suite-checks.tsv" ] && flags+=(hygiene)

if [ "${#flags[@]}" -gt 0 ]; then
    python3 - "$yml" "${flags[@]}" <<'PY' || { say "FAILED ci.yml edit"; rc=1; }
import re, sys
path, flags = sys.argv[1], sys.argv[2:]
lines = open(path).read().split("\n")
job = next((i for i, l in enumerate(lines) if "dot-ci/.github/workflows/validate.yml" in l), None)
if job is None:
    sys.exit(1)
indent = re.match(r"\s*", lines[job]).group()
w = next((i for i in range(job + 1, len(lines))
          if re.match(re.escape(indent) + r"with:\s*$", lines[i])), None)
if w is None:  # no with: block yet: put one right after uses:
    lines.insert(job + 1, indent + "with:")
    w = job + 1
end = w + 1
while end < len(lines) and lines[end].startswith(indent + " "):
    end += 1
child = indent + "    "
present = {re.match(r"\s*([\w-]+):", l).group(1) for l in lines[w + 1:end] if re.match(r"\s*[\w-]+:", l)}
add = [child + f + ": true" for f in flags if f not in present]
lines[end:end] = add
open(path, "w").write("\n".join(lines))
PY
fi

git -C "$repo" add -A ci .github/workflows/ci.yml
if git -C "$repo" diff --cached --quiet; then say "nothing to do"; exit $rc; fi
git -C "$repo" commit -q -m "Efficiency gates: baselines and caller flags (${flags[*]:-none})

Flags are only valid once dot-ci's v1 tag has the new inputs; do not push before it moves.

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>" && say "committed (${flags[*]:-none}); not pushed"
exit $rc
