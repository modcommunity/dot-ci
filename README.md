# dot-ci

The checks and the release packaging every project in this family shares, as two reusable GitHub Actions workflows and four shell scripts.

A repository here gets a `.github/workflows/` of about twenty lines and no knowledge of how any of it works. Everything that is actually hard — that the addons have to be fetched before a single script will parse, which runtime and which digest, which scenes are suites, which engine output is noise and which is a failure, what an addon's distributable actually is — lives here once. Fixing one of those is a commit, not sixty commits.

## Calling it

`.github/workflows/ci.yml`, in full:

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

`.github/workflows/release.yml`, in full:

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

Release runs `validate` first and depends on it, rather than `release.yml` calling `validate.yml` itself. A reusable workflow cannot take an expression for a ref, so nesting them would mean pinning the inner one to a branch — and then the scripts a release runs would not be the ones its workflow was written against. Four lines in the caller buys that guarantee back.

## What each repository has to be given

**Nothing, as things stand.** Every repository in the family is public, and a public clone needs no credential, so the checks run green with no secret configured anywhere.

The callers still pass `DOT_DEPS_TOKEN` and it is still worth leaving in place. It is normally empty and `resolve-deps.sh` treats it as optional; the day one of these repositories goes private, creating the secret is the whole change, in one place, rather than a commit against sixty workflow files at the moment CI turns red.

If you do create it: an organisation secret on the addons' side, and the same token as a repository secret on the games' side, because the two owners are different accounts and an organisation secret does not cross that line. It cannot be the built-in `GITHUB_TOKEN` — that is scoped to the one repository the workflow runs in, and every project here except `dot-core` needs between one and forty-three *others* checked out before its first script will parse.

**No cloud credentials, no signing key, no registry login.** See *What a release does not do*, below.

## The inputs

| Input | Default | |
| --- | --- | --- |
| `suites` | auto-detect | Scenes to run, space separated, relative, without `.tscn`. Set it when a repository's suite is not named the way auto-detection expects. |
| `suite-timeout` | `300` | Seconds any one suite may take. Past it, the suite has failed. |
| `godot` | `true` | `false` for a repository that is not a Godot project. Those skip the runtime entirely. |
| `shell-command` | — | A command to run in the checkout, instead of or as well as the Godot check. |

`release.yml` takes `version` (empty means "take it from the tag", which is the only value that cannot disagree with what was pushed) and `prerelease`. A game also passes `pack: true` (plus `pack-exclude-dirs` for anything beyond `addons examples tools screenshots .github`, and the `DEPS_TOKEN` secret), which imports the project and attaches `<name>-<version>-pack.zip` as well — see below. Needs `@v1.1.0` or later.

## What it checks

**Every script parses.** `--import` first, because that pass is what registers the `class_name` globals; without it every cross-file type reference fails at once and one missing pass reads as dozens of unrelated errors. Then `--check-only` per script, on the files *git tracks* — which is exactly this repository's own source, because the linked dependencies are gitignored in every project here.

**Then every suite runs**, because a clean parse says the files are valid GDScript and nothing whatsoever about whether the thing works.

**Capped with a timeout, which is not tidiness.** A scene whose script fails to parse *hangs* rather than failing: the identifier does not resolve, the scene never loads, and nothing ever reaches `get_tree().quit()`. Uncapped, that is a runner sitting at the six-hour job limit with no output, reported as an infrastructure problem.

**And a suite that exits 0 is still read.** A script error inside a test aborts *that test*, not the run — the section had already announced itself, so the suite's own section counter is satisfied, it reports `0 failed`, and it quits cleanly with its checks missing. One project here shipped precisely that: nine sections, sixty-three passed, zero failed, exit 0, eight checks that never ran. The engine had printed the error the whole time, so the check is to look.

Auto-detection takes `examples/*.tscn` whose name contains `selftest` or begins with `headless_` — the two names this family gives a scene that runs to a conclusion and quits. It deliberately does not run everything in `examples/`: several of those open a window, wait for input, or want a peer on the other end of a socket, and a demo waiting forever is indistinguishable on a runner from the parse hang above.

A repository with no detectable suite is **reported and passes**. The parse pass still ran, the summary says which repositories are getting half a check, and that list can then shrink on purpose. Failing them instead would only teach people to delete the workflow.

## What a release builds

**An addon repository ships `addons/<name>/` and nothing else.** That folder is the distributable; `project.godot` and `examples/` exist so the addon can be opened and validated standalone, and shipping them would put a second `project.godot` into the tree of whoever unzipped it. The zip's entries begin at `addons/`, so it installs by being unpacked at a project root. `plugin.cfg`'s version is stamped from the tag **in the artifact only** — the tag is the number that is unique, pushed, and impossible to forget to bump, and a committed version that has to be edited in lockstep across fifty-six repositories is a number that goes wrong quietly and then ships.

**Everything else ships the tracked tree as a tarball** — a game is not installed into a project, it is a source that the deployment turns into signed content.

**A game with `pack: true` also ships `<name>-<version>-pack.zip`**, because the tarball cannot become a pack: its addons are gitignored links and it has no `.godot/imported`, and a mounted pack is never re-imported, so every model and texture in it would load as nothing. The pack zip is the tracked tree without `addons/`, `examples/`, `tools/`, `screenshots/` and anything in `pack-exclude-dirs`, plus exactly the imported outputs its `.import` markers name — moved to `_imported/` with the markers rewritten, because a web export cannot read the engine's reserved `.godot/` directory back out of a mount. It is unsigned. website-city's release sync publishes a release file ending in `-pack.zip` in place of everything else on that release and signs it there, under `<owner>/<repo>`.

Both come with a `SHA256SUMS`, because a release page is not the only thing that consumes these and whatever carries them onward has to be able to say the bytes it got are the bytes that were built.

The artifact is built with `git archive`, and that choice is load-bearing. `addons/` is a directory of gitignored symlinks into sibling checkouts; a `cp -r` would either follow them — shipping a second, stale copy of every dependency at the same `res://` paths the host already defines — or preserve them, shipping links that dangle the moment the tree moves. An ignored file is not tracked, so it is not in the archive, and the list maintains itself.

## What a release does not do

**It does not publish to the content origin, and it does not sign anything.** Signing is what makes delivered content safe: a mounted resource pack can contain scripts and can never be unmounted on any platform, so a signature is the only thing between a content origin and arbitrary code in every client. The private half of that key exists in one place on purpose. Sixty repositories each holding a copy would be sixty ways to lose it, and a release workflow is the most-read, least-guarded place in any repository.

So a release here ends at an artifact and a digest. What carries it to the CDN is one deployment, which already holds the key and already knows what a pack is.

## The runtime

Pinned in `godot.pin`: one version, and the SHA512 that makes the pin mean something. A mismatch is fatal, the file is deleted, and there is no `--force` and no "checksum unavailable, continuing" — a script that fetches a binary without verifying it is a supply chain with nobody in it, and this one runs unattended on every push.

The digests are in this repository, in git, put there by a person reading the release's own `SHA512-SUMS.txt`. They are never read from beside the binary: a checksum served by whoever served the zip is checked by whoever would have had to tamper with both, which is one thing.

That pin is the *second* copy. `godot.pin` says which one is authoritative and what guards the drift between them.

## Why this repository is public

A reusable workflow in a private repository can only be called by repositories owned by the same account. This family has two owners, and that is a rule rather than an accident — so a private `dot-ci` could be called by half of it and not by the other half, which is the half whose releases reach players.

Nothing here is secret. It is YAML and shell; every credential it touches arrives as a secret from the caller, and the repositories it clones stay private.

## Running the scripts yourself

They take a directory and work the same on a laptop as on a runner:

```bash
scripts/fetch-godot.sh --version         # the pinned version
scripts/resolve-deps.sh ../dot-cloud --print   # what that project declares
GODOT=godot scripts/check.sh ../dot-cloud      # import, parse, run the suites
scripts/package.sh ../dot-cloud 0.2.0 --out /tmp/out
```

`resolve-deps.sh` is the only one that wants a token, and only when it is actually cloning. On a developer box the addons are already linked and `check.sh` is all you need — which is the same thing each project's own `tools/check.sh` does, kept there because that is where somebody runs it by hand.
