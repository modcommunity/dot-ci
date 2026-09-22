# dot-ci

The shared CI. Two reusable GitHub Actions workflows and four shell scripts, called by every other repository in the family. Read [README.md](README.md) first — it is the interface, and it explains the choices rather than just listing them.

This is not a Godot project. It has no `project.godot`, no `addons/`, and nothing here is ever linked into one.

## The rule this repository exists to keep

**Sixty repositories, one copy of the knowledge.** Every caller's workflow file is a `uses:` line and a secret. Nothing about how a project is checked, which runtime, which scenes, or what an artifact is, appears in any of them. If you find yourself about to write a step into a caller, write an input here instead.

The one exception is `suites`, and it is an input for the same reason: the *fact* that a repository's suite is called something unusual belongs in that repository, and the *knowledge* that a suite is a scene which runs to a conclusion belongs here.

## Two things here are copies, and both are deliberate

**The Godot pin** (`godot.pin`) is a copy of `dot-server-deploy/tools/fetch-godot.sh`'s, which is authoritative. Reaching into a private repository to read one string would put that repository in front of every check in the family. The drift is guarded from the other side: that project's own workflow compares the two and fails, because the drift is caused there and suffered here, and a check belongs where it can name the person who moved the pin. **Moving the version means editing both, in one change.**

**The owner split** — addons are the organisation's, games are their author's — is encoded in `resolve-deps.sh` as a two-line rule. `projects.tsv` in dot-bootstrap is the one *list*, and `dot-server-deploy/setup.sh` already carries a second copy of the *rule* for the one case that cannot read that file: a fresh box cloning what it needs before dot-bootstrap is on it. A runner is the same case — an empty disk and a token — and reaching projects.tsv would mean cloning dot-bootstrap first to find out where to clone dot-core from. The rule is repeated. The list is not.

If a third owner ever appears, that is the moment this stops being defensible and the list has to be fetched.

## What is not copied, and must not be

The addon dependencies come from each project's own `.gitignore`, from its `/addons/<name>` lines — the same derivation `bootstrap.sh` does. A manifest here would be a second copy of fifty-odd lists, which is the bug `projects.tsv` was written to stop and which this family has shipped three times already.

`/addons/` on its own means "this project vendors its addons" and names nothing to link. The pattern is anchored and single-segment (`^/addons/[a-z0-9_]+$`) precisely so that it does not match, because the failure mode of getting it wrong is not "nothing happens" — it is resolving zero addons versus resolving all of them.

## Traps found writing this, worth not re-finding

**`github.job_workflow_sha` is how a reusable workflow checks out its own scripts.** Pinning to `@main` instead would let a change here reach sixty repositories at once with nothing having been run against it. A reusable workflow cannot take an expression for a `ref:` in a `uses:`, which is also why `release.yml` does not call `validate.yml` — the caller does both and joins them with `needs`.

**The deps token is optional and must stay optional.** Every repository here is public, so a clone needs no credential; a script that demanded one would fail every check in the family over a secret nothing needs. The callers pass an empty `DOT_DEPS_TOKEN` anyway, so the day one goes private the fix is creating the secret and not sixty commits. The redaction helper is a no-op when the token is empty on purpose — `sed "s||***|g"` with an empty pattern matches at every position and would print a wall of asterisks where the clone error should be.

**Secrets are not available in a job-level `if:`.** `if: secrets.DEPS_TOKEN != ''` silently evaluates to false and the step is skipped, which looks like the step passing. So `resolve-deps.sh` decides for itself: a project declaring no addons exits 0 having done nothing, and one declaring some with no token fails and says which.

**The engine's own `ERROR: Condition "..." is true.` is not a script error.** It was in the "exited 0 but printed an error" pattern until dot-game's suite failed on it — several suites provoke one on purpose, to prove a no-op is a no-op rather than a crash. A guard that fires on correct code is a guard people delete. `SCRIPT ERROR` and `Parse Error` only.

**The parse pass treats any unfiltered output as a failure**, which is what makes it catch errors Godot reports without a non-zero exit — so the noise filter is the guard, and the engine is free to reword the noise. It did: 4.7 turned "ObjectDB instances leaked at exit" into "5 ObjectDB instances were leaked at exit". Hence `( were )?` rather than either literal.

**Godot needs `libfontconfig1` and the X11 libraries even with `--headless`.** It links them at load and dies with `libfontconfig.so.1: cannot open shared object file` before a line of GDScript runs, which reads as a broken download.

**The checkout directory is not the repository's name.** A runner checks the caller out into a directory the workflow chose (`project`), so `basename` gives the checkout's name — and every game in the family would have released `project-1.2.3.tar.gz`. `package.sh` takes `--name` and the release workflow passes `github.event.repository.name`. Found by packaging a runner-shaped checkout rather than a developer one, which is the only place the two names differ, and it is worth doing that deliberately for anything else added here.

**`unzip` answers a write error by asking.** On a runner with nobody to answer, that is a job that hangs rather than fails. Hence `< /dev/null`.

**`git ls-files` rather than `find`, for both the parse list and the artifact.** An addon repository's own source lives in `addons/<its name>/` and its dependencies sit right beside it, so "skip addons/" parses none of the repository and "parse addons/" parses all of dot-core on every one of its fifty consumers — turning one broken dependency into a failure reported against the whole family. What separates them is ownership, not path, and the links being gitignored is what makes git the thing that knows.

## Changing a workflow

There is no way to test a reusable workflow except by calling it. Tag this repository (`v1` moves; `v1.2.3` does not), point one caller at the new tag, watch it, then move `v1`. Callers pin `@v1` on purpose — a floating `@main` across sixty repositories means a typo here is sixty red repositories at once.

The scripts, unlike the workflows, run on a laptop and should be exercised there first. They take a directory:

```bash
GODOT=godot scripts/check.sh ../dot-cloud
scripts/package.sh ../dot-cloud 0.2.0 --out /tmp/out
```
