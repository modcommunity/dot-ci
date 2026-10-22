#!/usr/bin/env bash
# One summary table of the efficiency gates over many repositories, for the nightly panel.
# Usage: efficiency-report.sh [repo-dir ...]   (default: every ~/godot/*/ with a .git)
# Report only: it never fails on findings. Counts are violations with the baseline ignored
# (size, hazards) or cross-repository duplicate clusters (dup); lines and comment share are
# over the tracked .gd files.
set -u
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

dirs=("$@")
if [ ${#dirs[@]} -eq 0 ]; then
    for d in "$HOME"/godot/*/; do
        [ -e "$d/.git" ] && dirs+=("${d%/}")
    done
fi

count() { # gate dir -> number of known violations
    python3 "$here/$1" "$2" --no-baseline 2>/dev/null | sed -n 's/^[a-z-]*: \([0-9]*\) violations known.*/\1/p' | tail -1
}

# Duplicate clusters across all the given repositories, once, not per repository.
dup_out="$(python3 "$here/check-duplication.py" --cross "${dirs[@]}" 2>/dev/null | head -6)"

printf '%-28s %6s %8s %10s %7s\n' repo size hazards lines comment%
for d in "${dirs[@]}"; do
    name="$(basename "$d")"
    size="$(count check-size.py "$d")"
    haz="$(count check-frame-hazards.py "$d")"
    read -r lines com < <((cd "$d" && git ls-files -z '*.gd' | xargs -0 -r cat) 2>/dev/null |
        awk '{ n++ } /^[ \t]*#/ { c++ } END { printf "%d %.1f\n", n, n ? 100 * c / n : 0 }')
    printf '%-28s %6s %8s %10s %6s%%\n' "$name" "${size:-0}" "${haz:-0}" "${lines:-0}" "${com:-0}"
done
echo "${dup_out:-duplication (cross): no output}"
