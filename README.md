# dot-ci

The checks and release packaging that every project in the [dot-*](https://github.com/modcommunity) family shares. It is three reusable GitHub Actions workflows (`validate`, `release` and `release-maps`) and a set of shell and Python scripts. A repository adds about twenty lines of workflow and needs to know nothing else. Fixing a check is one commit here, not one per repository.

## First 10 minutes

1. Add the `ci.yml` below to your repository.
2. Reproduce it locally with [Running the scripts yourself](#running-the-scripts-yourself): import, parse every script, run the suites.
3. Push. A failing check names the script and the line.
4. To release, push a tag such as `v1.2.3`. `release.yml` packages it (see [Releases](#releases)).

`@v1` is a floating tag. It always points at the newest `v1.x.y`, so a project on `@v1` gets fixes with no edit. Pin a full tag such as `@v1.3.5` for a build that cannot change under you. In a game, `./game.sh test` runs the same steps CI does.

## Calling it

`.github/workflows/ci.yml`:

```yaml
name: CI
on:
    push:
        branches: [main]
    pull_request:
    workflow_dispatch:

jobs:
    validate:
        uses: modcommunity/dot-ci/.github/workflows/validate.yml@v1
        secrets:
            DEPS_TOKEN: ${{ secrets.DOT_DEPS_TOKEN }}
```

`.github/workflows/release.yml`:

```yaml
name: Release
on:
    push:
        tags: ['v*']

jobs:
    validate:
        uses: modcommunity/dot-ci/.github/workflows/validate.yml@v1
        secrets:
            DEPS_TOKEN: ${{ secrets.DOT_DEPS_TOKEN }}
    release:
        needs: validate
        uses: modcommunity/dot-ci/.github/workflows/release.yml@v1
        permissions:
            contents: write
```

The release runs `validate` as its own job instead of calling it from inside `release.yml`. A reusable workflow cannot take an expression for a ref, so nesting would pin the inner one to a branch, and a release would run scripts that do not match its workflow.

## Credentials

Nothing is needed today. Every repository in the family is public, so a clone needs no credential and the checks pass with no secret set.

The callers still pass `DOT_DEPS_TOKEN`. It is normally empty and `resolve-deps.sh` treats it as optional. If a repository goes private, creating the secret is the whole change. It must be a personal or app token, not the built-in `GITHUB_TOKEN`, which only reaches the repository the workflow runs in. Release needs no cloud credential, signing key or registry login.

## Inputs of `validate.yml`

| Input | Default | What it does |
| --- | --- | --- |
| `suites` | auto-detect | Scenes to run, space separated, relative, without `.tscn`. |
| `suite-timeout` | `300` | Seconds any one suite may run. Past it, the suite has failed. Set `1800` for a long suite, or locally `SUITE_TIMEOUT=1800 scripts/check.sh`. `0` means no limit. |
| `godot` | `true` | `false` for a repository that is not a Godot project. It skips the runtime. |
| `shell-command` | none | A command to run in the checkout, instead of or as well as the Godot check. |
| `efficiency` | `false` | Run the size, per-frame hazard and duplication gates against baselines under `ci/efficiency/`. |
| `hygiene` | `false` | Run the hygiene gates below. They report only unless `hygiene-blocking` is `true`. |
| `profiles` | `false` | Check every `cfg/` profile against its schema. |
| `perf` | `false` | Run the perf smoke against `ci/perf/smoke.json`. |

`release.yml` takes `version` (empty means take it from the tag, the only value that cannot disagree with what was pushed) and `prerelease`. A game also passes `pack: true` (and `pack-exclude-dirs` for folders beyond `addons examples tools screenshots images .github`).

## What it checks

| Check | What it does |
| --- | --- |
| Every script parses | Imports first, because that registers the `class_name` globals. Then compiles the files git tracks. With dot-core's `tools/dot_parse_all.gd` this is one process; `PARSE_PER_FILE=1` forces one process per script. Any output for a script is a failure. |
| Linked maps | A comment `# bootstrap-link: <repo>/<dir> ci` above an ignored path in a game's `.gitignore` makes `resolve-deps.sh` shallow-clone that repository and link the folder. The trailing `ci` opts in, because one maps repository is 1.8 GB. |
| No JavaScript string evaluation | Fails on `JavaScriptBridge.eval`, `DotWeb.eval*`, `eval(` or `new Function(` in tracked `.gd`, `.js` and `.html`. The web origin's CSP forbids it. A real exception carries a `js-eval: allow <reason>` comment. |
| No Valve-origin files | Uses dot-cloud's `tools/check_valve_files.py --git`: no `.vpk`, `.vtf`, `.vmt`, `.mdl`, `.vvd`, `.vtx`, `.phy`, `.ani` and no `textures/orig` folder. |
| Windows-safe names | Fails on `* ? : " < > |` or a backslash in a name, a name ending in a dot or space, a reserved device name (CON, NUL, COM1 and so on) or two paths that differ only by case. |
| Suites run | Each suite scene runs under a timeout, and its output is read even when it exits 0, because a script error inside a test can leave checks silently unrun. |

Auto-detection runs `examples/*.tscn` whose name contains `selftest` or starts with `headless_`. Other scenes may open a window or wait for a peer, which is indistinguishable from a hang on a runner. A repository with no detectable suite is reported and passes, and the summary lists it.

## Releases

| Repository | What a release ships |
| --- | --- |
| Addon | A zip of `addons/<name>/` only, so it installs by unpacking at a project root. `plugin.cfg`'s version is stamped from the tag in the artifact, never committed. |
| Game or other | The tracked tree as a tarball, built with `git archive` so gitignored addon links are not shipped. |
| Game with `pack: true` | Also `<name>-<version>-pack.zip`: the tracked tree without `addons/`, plus the imported outputs its `.import` markers name (moved to `_imported/`), and a `requires.json` of the addon API levels it needs, so an older client refuses it before mounting. |
| Maps repository | `release-maps.yml` makes one pack per map: it checks the game out beside the maps, imports, and runs `scripts/package-subpacks.sh`. Inputs are `game`, and optionally `maps-dir`, `link-at` and `game-ref`. |

Every release carries a `SHA256SUMS`. Before a release is created, `scripts/server-compat.sh` checks that the newest `dot-server-deploy` release can run the pack. A game that needs an addon API level no server release has yet fails here. `server-compat: false` opts out. A release does not publish to the content origin and does not sign anything. The signing key lives in one deployment on purpose.

## The runtime

`godot.pin` pins one Godot version and its SHA512. A mismatch is fatal. The digests are committed here by a person reading the release's own `SHA512-SUMS.txt`, never read from beside the binary. The pin is a copy of the one in dot-server-deploy, which is authoritative and guards against drift. Move both in the same change.

## Hygiene gates

Opt in with `hygiene: true`. Each gate has a shrink-only baseline under `ci/efficiency/`, made with `--init` and lowered with `--update`. Existing debt never fails; only new violations do.

| Script | What it finds |
| --- | --- |
| `check-comments.py` | Comment blocks over 3 lines, banners, commented-out code and history (dates, "found by"). |
| `check-logging.py` | A `const CHANNEL` in a file that never logs, `push_warning` calls, and runtime `print` (examples, tools and editor scripts are exempt). |
| `check-markdown-wrap.py` | Paragraphs hard-wrapped over several lines in a `.md`. |
| `check-suite-checks.py` | A suite whose `const CHECKS` differs from the total in its last log. |
| `check-generated.py` | A generated file that differs from what its command in `ci/generated.tsv` produces. |
| `check-web-size.py` | A web build file over its budget in `ci/web-budget.tsv`. |
| `comment-report.py`, `duplication-cross.sh` | Reports only; always exit 0. |

## Profile check

With `profiles: true`, `scripts/check-profiles.sh <project>` runs dot-profile's `tools/profile_check.gd` over `cfg/addon/*`, `cfg/game/*` and `cfg/server/*`. It reports unknown keys, wrong types, out-of-range values, NaN and infinity, a missing or cyclic `extends`, duplicate ids and unread `.yaml` files, one `path: message` line each. A project without `cfg/` passes. Pass a project's own kinds with `--schema <script>`.

## Running the scripts yourself

They take a directory and work the same on a laptop as on a runner.

```bash
scripts/fetch-godot.sh --version               # the pinned version
scripts/resolve-deps.sh ../dot-cloud --print   # what that project declares
GODOT=godot scripts/check.sh ../dot-cloud      # import, parse, run the suites
scripts/package.sh ../dot-cloud 0.2.0 --out /tmp/out
```

`resolve-deps.sh` wants a token only when it actually clones.

| Script | What it does |
| --- | --- |
| `efficiency-trend.py` | Reads `efficiency-report.sh` output on stdin, appends the totals to a history file and prints the change. `--strict` exits 1 if size, hazards or duplicate clusters grew. |
| `efficiency-nightly.sh` | The nightly check in one command: report, then the trend with `--strict`. |
| `rollout-caller.sh <repo>` | Turns the efficiency gates on for one repository: baselines first, then the flags. |
| `perf-smoke.sh [--init\|--update] [--scene S] [--seconds N] <project>` | Loads the main scene headless for N seconds (default 5) and compares load time, frame time, node count and memory with `ci/perf/smoke.json`. Fails when more than 20% over budget (timings get 2.5 times that). `--init` records the budget, `--update` only lowers it. Run it under `heavy`. |

## Why this repository is public

A reusable workflow in a private repository can only be called by repositories of the same account. The family has two owners, so a private dot-ci would serve only half of it. Nothing here is secret: it is YAML and scripts, and every credential arrives from the caller.

## Status

Built and maintained with Claude Code. The checks run on every repository in the family, but little of this has been in front of outside users yet. Please report rough edges by opening an issue.

## Licence

MIT. See [LICENSE](LICENSE). Only the TMC back-end web infrastructure is not open source.
