#!/usr/bin/env bash
#
# Checks every profile yml under a project's cfg/ against its schema (dot-profile's profile_check).
#
#   GODOT=godot scripts/check-profiles.sh <project-dir> [profile_check args...]
#
# Runs after the import so the class cache exists. A project with no cfg/ directory, or one
# that does not link dot-core's tool, passes having checked nothing. Extra arguments reach the
# tool (--schema <script> for a project's own kinds, --skip-unknown).
set -uo pipefail
dir="${1:-.}"
shift || true
GODOT="${GODOT:-godot}"
[ -d "$dir" ] || { printf 'no such directory: %s\n' "$dir" >&2; exit 2; }
tool=addons/dot_profile/tools/profile_check.gd
if [ ! -d "$dir/cfg" ] || [ ! -f "$dir/$tool" ]; then
    printf 'profiles: nothing to check in %s\n' "$dir"
    exit 0
fi
[ -f "$dir/.godot/global_script_class_cache.cfg" ] || "$GODOT" --headless --path "$dir" --import >/dev/null 2>&1 < /dev/null
out="$(cd "$dir" && timeout 120 "$GODOT" --headless --path . --script "$tool" -- . "$@" 2>&1 < /dev/null)"
rc=$?
printf '%s\n' "$out" | grep -v '^Godot Engine'
if [ "$rc" -ne 0 ] || ! grep -q '^PROFILE_CHECK ' <<<"$out"; then
    printf 'FAIL profile check (exit %s)\n' "$rc" >&2
    exit 1
fi
