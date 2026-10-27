#!/usr/bin/env bash
# The nightly efficiency check in one command: report table, trend against the last run, and
# a non-zero exit (REGRESSED line) when size violations, frame hazards or duplicate clusters grew.
# The nightly runner pastes this output into the item's note. Run under `heavy` on the dev box.
set -u
# EFFICIENCY_PANEL_FILE=path also writes the whole output there (the nightly runner or a dev01 sync reads it).
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
out="$("$here/efficiency-report.sh" "$@")"
text="$(printf '%s\n' "$out" | tail -n 8; echo)"
trend="$(printf '%s\n' "$out" | python3 "$here/efficiency-trend.py" --strict)"
rc=$?
printf '%s\n%s\n' "$text" "$trend"
if [ -n "${EFFICIENCY_PANEL_FILE:-}" ]; then
    printf '%s\n%s\n' "$text" "$trend" > "$EFFICIENCY_PANEL_FILE"
fi
exit "$rc"
