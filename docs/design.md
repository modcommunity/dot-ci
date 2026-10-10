# dot-ci design

Why the shared CI is shaped the way it is. [README.md](../README.md) is the interface and explains the inputs; this file is the reasoning behind the parts a maintainer is most likely to "simplify". The rules are one line each in [CLAUDE.md](../CLAUDE.md).

## One copy of the knowledge

Sixty repositories, one copy of the knowledge. Every caller's workflow file is a `uses:` line and a secret. Nothing about how a project is checked, which runtime, which scenes, or what an artifact is, appears in any of them. If you are about to write a step into a caller, write an input here instead.

The one exception is `suites`, and it is an input for the same reason: the fact that a repository's suite is called something unusual belongs in that repository, and the knowledge that a suite is a scene which runs to a conclusion belongs here.

## Two things here are copies, and both are deliberate

**The Godot pin.** `godot.pin` is a copy of dot-server-deploy's `tools/fetch-godot.sh` pin, which is authoritative. Reaching into another repository to read one string would put that repository in front of every check in the family. The drift is guarded from the other side: dot-server-deploy's own workflow compares the two and fails, because the drift is caused there and suffered here, and a check belongs where it can name the person who moved the pin. Moving the version means editing both, in one change.

**The owner rule.** Addons are the organisation's, games (and the weapons packs) are their author's. `resolve-deps.sh` encodes that as two defaults, `DOT_OWNER` and `GAME_OWNER`, plus `addon_repo()` for the one addon whose repository is not named after its directory. dot-bootstrap's `projects.tsv` is the one list; dot-server-deploy's setup carries a second copy of the rule for a fresh box that has to clone before dot-bootstrap is on it. A runner is the same case (an empty disk and a token), and reaching `projects.tsv` would mean cloning dot-bootstrap first to find out where to clone dot-core from. The rule is repeated; the list is not. If a third owner ever appears, that is the moment this stops being defensible and the list has to be fetched.

## What is not copied, and must not be

The addon dependencies come from each project's own `.gitignore`, from its `/addons/<name>` lines: the same derivation `bootstrap.sh` does. A project with an `addons.lock` is resolved from the lock instead, each addon cloned at its locked ref, because only the lock is what ships; checking such a project against main would pass a call into an untagged addon API ([history](history.md#an-untagged-addon-api-passed-ci)). A manifest here would be a second copy of fifty-odd lists, which is the bug `projects.tsv` was written to stop.

`/addons/` on its own means "this project vendors its addons" and names nothing to link. The pattern is anchored and single-segment (`^/addons/[a-z0-9_]+$`) precisely so that it does not match, because the failure mode of getting it wrong is not "nothing happens": it is resolving zero addons versus resolving all of them.

## Traps worth not re-finding

**`github.job_workflow_sha` is how a reusable workflow checks out its own scripts.** Pinning to `@main` instead would let a change here reach sixty repositories at once with nothing having been run against it. A reusable workflow cannot take an expression for a `ref:` in a `uses:`, which is also why `release.yml` does not call `validate.yml`: the caller does both and joins them with `needs`.

**The deps token is optional and must stay optional.** A public clone needs no credential; a script that demanded one would fail every check in the family over a secret nothing needs. Callers pass an empty `DOT_DEPS_TOKEN` anyway, so the day a repository goes private the fix is creating the secret, not sixty commits. `_redact` is a no-op when the token is empty on purpose: `sed "s||***|g"` with an empty pattern matches at every position and would print a wall of asterisks where the clone error should be.

**Secrets are not available in a job-level `if:`.** `if: secrets.DEPS_TOKEN != ''` silently evaluates to false and the step is skipped, which looks like the step passing. So `resolve-deps.sh` decides for itself: a project declaring no addons exits 0 having done nothing, and one declaring some with no token fails and says which.

**The engine's own `ERROR: Condition "..." is true.` is not a script error.** Several suites provoke one on purpose, to prove a no-op is a no-op rather than a crash. A guard that fires on correct code is a guard people delete. `check.sh` fails an exit-0 suite on `SCRIPT ERROR` and `Parse Error` only.

**The parse pass treats any unfiltered output as a failure**, which is what makes it catch errors Godot reports without a non-zero exit, so the noise filter is the guard, and the engine is free to reword the noise. 4.7 turned "ObjectDB instances leaked at exit" into "5 ObjectDB instances were leaked at exit"; hence `( were )?` rather than either literal.

**Godot needs `libfontconfig1` and the X11 libraries even with `--headless`.** It links them at load and dies with `libfontconfig.so.1: cannot open shared object file` before a line of GDScript runs, which reads as a broken download.

**The checkout directory is not the repository's name.** A runner checks the caller out into a directory the workflow chose (`project`), so `basename` gives the checkout's name, and every game would release `project-1.2.3.tar.gz`. `package.sh` takes `--name` and the release workflow passes `github.event.repository.name`. Package a runner-shaped checkout, not a developer one, when testing anything added here: it is the only place the two names differ.

**`unzip` answers a write error by asking.** On a runner with nobody to answer, that is a job that hangs rather than fails. Hence `< /dev/null` in `fetch-godot.sh`.

**`git ls-files` rather than `find`, for both the parse list and the artifact.** An addon repository's own source lives in `addons/<its name>/` and its dependencies sit right beside it, so "skip addons/" parses none of the repository and "parse addons/" parses all of dot-core on every one of its consumers, turning one broken dependency into a failure reported against the whole family. What separates them is ownership, not path, and the links being gitignored is what makes git the thing that knows.

## `requires.json`: nothing here keeps the list

`package.sh --pack` runs dot-core's `tools/dot_requires.gd` against the imported checkout and writes `requires.json` into the pack: every addon whose global classes or `res://addons/<x>/` paths the game's files name, at the level that addon's `<addon>_api.gd` declares (1 when it has none). dot-cloud reads it before mounting. A committed `requires.json` wins and is audited with `--check` instead. It is derived from what the runner resolved, which is the pinned `.deps`, so "built against" means what was actually built against. A dot-core too old to have the tool gets a note, not a failure: the pack is then exactly what it was before the tool existed.

## The two publishers must agree

A game's `-pack.zip` from `package.sh --pack` and the pack dot-server-deploy publishes from the same tree must hold the same files under the same paths, with `.godot/imported/` moved to `_imported/` the way `DotCloudPublisher` moves it. After changing what `--pack` includes, build both from one game's tree, decode the deployed pack's manifest payload and diff the paths. The two publishers producing different packs from one tree is the drift to watch for.
