#!/usr/bin/env bash
# The nightly efficiency check in one command: report table, trend against the last run, and
# a non-zero exit (REGRESSED line) when size violations, frame hazards or duplicate clusters grew.
# The nightly runner pastes this output into the item's note. Run under `heavy` on the dev box.
set -u
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
out="$("$here/efficiency-report.sh" "$@")"
printf '%s\n' "$out" | tail -n 8
echo
printf '%s\n' "$out" | python3 "$here/efficiency-trend.py" --strict
