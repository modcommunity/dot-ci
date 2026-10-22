# CI and test speedups

Measured on dev02, 2026-10-22, game-arena (`./game.sh --no-parse test <suite>`, one at a time under `heavy`). Numbers are in the table below.

## Done in this repository

- `validate.yml`, `release.yml`, `release-maps.yml`: the shared libraries are installed only when `dpkg -s` says one is missing. The runner image normally has them, so the `apt-get update` (several seconds, one network round trip) is skipped.
- `release.yml`, `release-maps.yml`: the Godot runtime is cached in `~/.godot-ci` (key `godot-<hash of godot.pin>`), as `validate.yml` already did. A tag build no longer downloads about 60 MB.
- Checked 2026-10-22: the cache is not inert. Every workflow passes `fetch-godot.sh --dest ~/.godot-ci/<version>`, which overrides the `RUNNER_TOOL_CACHE/dot-godot` default, so the cached path and the fetch destination are the same directory.
- `ci.yml`: `concurrency` cancels a superseded run on the same ref. It deliberately does not cache the runtime: its fetch step is the end-to-end proof of the pin.

## Not done, and why

- Caching `.godot/imported`: the key would have to cover the project and every resolved addon at its locked ref, and a stale import cache fails silently (a `.glb` that loads as nothing). The import costs seconds in a game (see the table), so the risk is not worth it.
- `fetch-depth`: every checkout is already depth 1, and `resolve-deps.sh` clones with `--depth 1`.
- Parse: already one process for all scripts (`dot_parse_all.gd`); the per-file `--check-only` loop is only the fallback when the tool is missing.
- Parallel suites in a caller: `check.sh` runs suites serially. A matrix over `suites` in the caller (one job per slow suite) would cut wall time to the slowest suite, at the cost of one import and runtime restore per job. Worth it only for a repository whose suites total more than about ten minutes.

## Proposed game.sh diffs (not applied: a change must be mirrored into every game)

`do_test` imports once per invocation, so running N suites by hand pays N imports. When `./game.sh test <suite>` is given a suite and `.godot/imported` is newer than every `*.import`, `project.godot` and `addons/` file, skip the import:

```diff
-    echo "importing"
-    timeout 600 "$GODOT" --headless --path . --import >/dev/null 2>&1
+    if [ ! -d .godot/imported ] || [ -n "$(find project.godot addons examples -newer .godot/imported -type f \( -name '*.import' -o -name '*.gd' -o -name project.godot \) -print -quit 2>/dev/null)" ]; then
+        echo "importing"
+        timeout 600 "$GODOT" --headless --path . --import >/dev/null 2>&1
+    fi
```

Caveat: a new `class_name` needs the import (the global class cache), and a `.gd` newer than the directory triggers it, which is why `*.gd` is in the test.
