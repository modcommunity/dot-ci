#!/usr/bin/env bash
#
# Fails a repository with a `*` or `?` in any path under a cfg/ directory.
#
#   scripts/check-cfg-names.sh <project-dir>
#
# Windows cannot create such a file and a published pack cannot carry it. A per-map glob
# file is spelled `surf_%.yml` (`%` for `*`, `@` for `?`), see dot-map's docs/map-config.md.
set -uo pipefail
dir="${1:-.}"
[ -d "$dir" ] || { printf 'no such directory: %s\n' "$dir" >&2; exit 2; }
bad=$(cd "$dir" && find . -path ./.godot -prune -o -path ./.git -prune -o -path '*/cfg/*' -name '*[*?]*' -print)
if [ -n "$bad" ]; then
    printf 'FAIL cfg path with * or ? (use %% for * and @ for ?):\n%s\n' "$bad" >&2
    exit 1
fi
echo "cfg names ok"
