#!/usr/bin/env bash
# Which consumer games/addons and which of their suites a change can break. See affected.py.
exec python3 -I "$(dirname "$(readlink -f "$0")")/affected.py" "$@"
