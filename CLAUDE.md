# dot-ci

The family's shared CI: three reusable GitHub Actions workflows (`validate.yml`, `release.yml`, `release-maps.yml`) and the shell scripts they run, called by every other repository. Read [README.md](README.md) first: it is the interface, and it explains the choices rather than just listing them.

This is not a Godot project. It has no `project.godot`, no `addons/`, and nothing here is ever linked into one. **This repository is public**: write nothing here about another repository beyond what the README already says.

## Read before

| Read | Before |
| --- | --- |
| [docs/design.md](docs/design.md) | changing a workflow or script: one copy of the knowledge, the two deliberate copies (Godot pin, owner rule), dependency resolution, the traps, `requires.json`, the two publishers agreeing |
| [docs/history.md](docs/history.md) | the untagged addon API that passed CI, the engine error that failed a suite, the `project-<version>` artifact name |

## Layout

| Path | What |
| --- | --- |
| `.github/workflows/validate.yml` | reusable: resolve addons, import, parse every tracked script, run every suite |
| `.github/workflows/release.yml` | reusable: artifact + `SHA256SUMS` on a `v*` tag; `pack: true` adds `-pack.zip`; server-compat gate |
| `.github/workflows/release-maps.yml` | reusable: one pack per map for a map repository |
| `.github/workflows/ci.yml` | this repository's own check: `bash -n` and shellcheck on `scripts/`, workflows load as YAML, the pin fetches and verifies |
| `godot.pin` | the runtime version and SHA512 (the second copy; it says which is authoritative) |
| `scripts/fetch-godot.sh` | fetch and verify the pinned runtime |
| `scripts/resolve-deps.sh` | addons from `.gitignore` or `addons.lock`, cloned into `.deps/` and linked |
| `scripts/check.sh` | import, parse pass, suites, the exit-0 stderr check |
| `scripts/package.sh` | the release artifact; `--pack` builds the pack zip and `requires.json` |
| `scripts/package-subpacks.sh` | one pack per map directory |
| `scripts/server-compat.sh` | refuses a pack the newest released server cannot run |

## Running and testing

There is no way to test a reusable workflow except by calling it. Tag this repository (`v1` moves; `v1.2.3` does not), point one caller at the new tag, watch it, then move `v1`. Callers pin `@v1` (or an exact tag) on purpose: a floating `@main` across sixty repositories means a typo here is sixty red repositories at once.

The scripts run on a laptop and should be exercised there first; they take a directory ([README](README.md#running-the-scripts-yourself) has the full list):

```bash
GODOT=godot scripts/check.sh ../dot-cloud
scripts/package.sh ../dot-cloud 0.2.0 --out /tmp/out
scripts/package.sh ../game-arena 0.2.0 --out /tmp/out --pack   # imported first
```

## Rules that bite

- Never write a step into a caller; add an input here. `suites` is the one per-repository fact. [design](docs/design.md#one-copy-of-the-knowledge)
- Moving the Godot version means editing `godot.pin` and dot-server-deploy's `tools/fetch-godot.sh` in one change; take the digest from the release's own `SHA512-SUMS.txt`. [design](docs/design.md#two-things-here-are-copies-and-both-are-deliberate)
- The owner rule is repeated in `resolve-deps.sh` (`DOT_OWNER`, `GAME_OWNER`, `addon_repo()`); the project list is never copied here. [design](docs/design.md#two-things-here-are-copies-and-both-are-deliberate)
- Dependencies come from the project's `.gitignore` (`^/addons/[a-z0-9_]+$`, so a bare `/addons/` names nothing) or its `addons.lock` at the locked refs. [design](docs/design.md#what-is-not-copied-and-must-not-be)
- Workflows check out their own scripts at `github.job_workflow_sha`; `release.yml` never calls `validate.yml`. [design](docs/design.md#traps-worth-not-re-finding)
- The deps token stays optional; `_redact` must stay a no-op on an empty token; never gate a step on `secrets.` in an `if:`. [design](docs/design.md#traps-worth-not-re-finding)
- An exit-0 suite fails on `SCRIPT ERROR` or `Parse Error` only, never on the engine's `ERROR: Condition`. Noise filters match both wordings (`( were )?`). [design](docs/design.md#traps-worth-not-re-finding)
- Headless Godot still needs `libfontconfig1` and the X11 libraries; `unzip` runs with `< /dev/null`. [design](docs/design.md#traps-worth-not-re-finding)
- Artifacts are named with `--name` (the repository name), never the checkout's basename; test new packaging on a runner-shaped checkout. [design](docs/design.md#traps-worth-not-re-finding)
- Parse lists and artifacts come from `git ls-files`, never `find` or a path rule. [design](docs/design.md#traps-worth-not-re-finding)
- After changing what `--pack` includes, diff its paths against the pack dot-server-deploy publishes from the same tree. [design](docs/design.md#the-two-publishers-must-agree)
- A release signs nothing and publishes nothing; it ends at an artifact and a digest. [README](README.md#what-a-release-does-not-do)
