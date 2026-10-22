#!/usr/bin/env bash
# Headless perf smoke for a project: load time, frame time, node count and memory after N
# seconds, compared with a budget recorded in the project (ci/perf/smoke.json).
# Usage: perf-smoke.sh [--init|--update] [--scene res://x.tscn] [--seconds N] [--tolerance PCT] <project-dir>
#   (no flag)  fail when a metric is more than PCT (default 20) over the budget
#   --init     write the budget from this run (refuses to overwrite)
#   --update   lower the budget where this run is better; never raises one
# Scene defaults to the project's main scene. GODOT picks the runtime (default: godot).
# Frame time is the engine's process time with rendering off, so it is a CPU-side ratchet
# for scripts and node count, not a measure of what a GPU does. Run it through `heavy`.
set -u
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
mode=check scene="" seconds=5 tol=20
while [ $# -gt 1 ]; do
    case "$1" in
        --init) mode=init; shift ;;
        --update) mode=update; shift ;;
        --scene) scene="$2"; shift 2 ;;
        --seconds) seconds="$2"; shift 2 ;;
        --tolerance) tol="$2"; shift 2 ;;
        *) break ;;
    esac
done
dir="${1:?usage: perf-smoke.sh [options] <project-dir>}"
[ -f "$dir/project.godot" ] || { echo "perf-smoke: $dir has no project.godot" >&2; exit 2; }
if [ -z "$scene" ]; then
    scene="$(sed -n 's/^run\/main_scene="\(.*\)"/\1/p' "$dir/project.godot" | head -1)"
fi
case "$scene" in res://uid://*|uid://*) echo "perf-smoke: pass --scene (main scene is a uid)" >&2; exit 2 ;; esac
[ -n "$scene" ] || { echo "perf-smoke: no main scene; pass --scene" >&2; exit 2; }

log="$(mktemp)"
trap 'rm -f "$log"' EXIT
(cd "$dir" && timeout $((seconds + 120)) "${GODOT:-godot}" --headless --path . --script "$here/perf_smoke.gd" -- "$scene" "$seconds") >"$log" 2>&1
line="$(grep '^PERF_SMOKE ' "$log" | tail -1 | cut -d' ' -f2-)"
if [ -z "$line" ]; then
    echo "perf-smoke: no result"; tail -5 "$log"; exit 1
fi
if grep -q 'SCRIPT ERROR\|Parse Error' "$log"; then
    echo "perf-smoke: script errors while running"; grep 'SCRIPT ERROR\|Parse Error' "$log" | head -5; exit 1
fi
exec python3 "$here/perf-budget.py" "$mode" "$dir/ci/perf/smoke.json" "$tol" "$line"
