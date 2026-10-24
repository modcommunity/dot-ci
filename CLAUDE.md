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
| `scripts/check-export-filter.sh` | fails a repository whose `export_presets.cfg` or `.example.cfg` has a preset `include_filter` without `cfg/*` |
| `scripts/check-cfg-names.sh` | fails a repository with a `*` or `?` in any path under a `cfg/` directory (spell per-map globs `surf_%.yml`) |
| `scripts/check-windows-names.py` | fails a repository whose `git ls-files` has a name Windows cannot check out: `* ? : " < > | \`, a component ending in a dot or space, a reserved device name (CON, NUL, COM1...), or two paths differing only by case. Always on in `validate.yml`; tests in `tests/test_windows_names.py` |
| `scripts/check-size.py`, `check-frame-hazards.py`, `check-duplication.py` | the efficiency gates (opt-in `efficiency: true`): file/function size, per-frame hazards, duplicated 30-line windows. Each has a baseline at `ci/efficiency/*.tsv` in the checked repository that only shrinks (`--init` once, `--update` lowers and refuses to add); `check-duplication.py --cross <dirs>` is the report-only nightly mode. Shared code in `effgate.py`; tests in `tests/` |
| `scripts/efficiency-report.sh [dirs]` | one summary table for the nightly panel (repo, size violations, frame hazards, lines, comment-line share, then cross-repository duplicate clusters) over the given repositories, default every `~/godot/*/` with a `.git`. Report only, never fails; ignores baselines |
| `scripts/efficiency-nightly.sh`, `perf-smoke.sh`, `perf_smoke.gd`, `perf-budget.py` | the nightly report plus trend in one command; the headless perf smoke (load, frame time, nodes, memory vs `ci/perf/smoke.json`, 20% ratchet). [README](README.md#running-the-scripts-yourself) |
| `scripts/check-comments.py`, `check-generated.py`, `check-web-size.py`, `duplication-cross.sh` | the opt-in `hygiene: true` gates (report-only unless `hygiene-blocking`) with the same shrink-only baselines, and the nightly cross-repository duplication wrapper. [README](README.md#hygiene-gates-and-the-nightly-scan) |
| `scripts/check-profiles.sh` | opt-in `profiles: true`: runs dot-core's `profile_check.gd` over a project's `cfg/` profile yml; fails on any schema, `extends` or duplicate-id problem |
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
