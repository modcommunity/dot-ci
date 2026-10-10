# dot-ci history

Stories whose bug could come back. The live rule from each is in [design.md](design.md) or [CLAUDE.md](../CLAUDE.md).

## An untagged addon API passed CI

dot-server-deploy's `.gitignore` had a bare `/addons/`, which names nothing to link, so its CI ran with Godot off. On 2026-10-04 a host script calling an addon API no tag had yet passed CI and broke a live server. Checking it against main would have passed it too, because main had the API; only the lock is what ships. `resolve-deps.sh` now resolves a project with an `addons.lock` from the lock, each addon at its locked ref, and `server-compat.sh` refuses a game release that needs an API no released server locks.

## A deliberate engine error failed a suite

The "exited 0 but printed an error" check once matched the engine's own `ERROR: Condition "..." is true.` and failed dot-game's suite, which provokes that message on purpose. The pattern is now `SCRIPT ERROR|Parse Error` only.

## Every game would have released `project-<version>`

`package.sh` named the artifact after the checkout's basename, which is right on a developer box and `project` on a runner. Found by packaging a runner-shaped checkout; `--name` exists because of it.
