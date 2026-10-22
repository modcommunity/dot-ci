#!/usr/bin/env bash
# Cross-repository duplication scan for the nightly runner: the top clusters, never fails.
# Usage: duplication-cross.sh [--top N] [repo-dir ...]   (default top 15; every ~/godot/*/ with a .git)
set -u
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
top=15
if [ "${1:-}" = "--top" ]; then top="${2:-15}"; shift 2; fi
dirs=("$@")
if [ ${#dirs[@]} -eq 0 ]; then
    for d in "$HOME"/godot/*/; do
        [ -e "$d/.git" ] && dirs+=("${d%/}")
    done
fi
python3 "$here/check-duplication.py" --cross --top "$top" "${dirs[@]}" || echo "duplication (cross): scan failed"
exit 0
