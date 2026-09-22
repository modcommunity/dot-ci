#!/usr/bin/env bash
#
# Build the artifact a release attaches, out of a checkout.
#
#   scripts/package.sh <project-dir> <version> [--out DIR]
#
# Prints one artifact path per line on stdout. Everything said to a person goes to
# stderr, so a caller can read the paths with $(...).
#
# TWO SHAPES, because two different people are downloading.
#
#   An ADDON repository ships addons/<name>/ and nothing else. That folder IS the
#   distributable -- project.godot and examples/ exist only so the addon can be opened
#   and validated standalone, and shipping them would put a second project.godot into
#   the tree of whoever unzipped it. The zip's entries start at addons/, which is the
#   convention every Godot addon follows: unzip at the project root and it is
#   installed.
#
#   Everything ELSE -- the games, the launcher, the deployment tool -- ships the
#   tracked tree as a tarball. A game is not installed into a project; it is a SOURCE
#   that the central publisher turns into a signed pack. That is why no release here
#   builds one: signing is what makes a mounted pack safe, a mounted pack can contain
#   scripts, and the private half of that key exists in one place on purpose. Sixty
#   repositories each holding a copy of it would be sixty ways to lose it.
#
# WHAT IS IN THE ARTIFACT IS WHAT GIT TRACKS, via git archive. Not `cp -r`, and the
# difference is the point: addons/ is a directory of gitignored SYMLINKS into sibling
# checkouts on a developer box and into .deps/ on a runner, and a copy would either
# follow them -- shipping a second, stale copy of every dot-* addon at the same res://
# paths the host already defines -- or preserve them, shipping links that dangle the
# moment the tree moves. git archive resolves it by never seeing them: an ignored file
# is not tracked, so it is not in the archive, and the list maintains itself.
#
set -uo pipefail

PROJECT="${1:?usage: package.sh <project-dir> <version> [--out DIR] [--name NAME]}"
VERSION="${2:?usage: package.sh <project-dir> <version> [--out DIR] [--name NAME]}"
shift 2
OUT=""
NAME=""
while [ $# -gt 0 ]; do
    case "$1" in
        --out)  OUT="${2:?--out needs a directory}"; shift 2 ;;
        --name) NAME="${2:?--name needs a name}"; shift 2 ;;
        *) printf 'unknown option: %s\n' "$1" >&2; exit 2 ;;
    esac
done

[ -d "$PROJECT" ] || { printf 'no such directory: %s\n' "$PROJECT" >&2; exit 2; }
PROJECT="$(cd "$PROJECT" && pwd -P)"

# --name, and it is not a convenience. A runner checks the repository out into a
# directory it chose -- `project` here -- so the basename is the CHECKOUT's name and
# not the repository's, and every game in the family would have released a tarball
# called project-1.2.3.tar.gz. Found by packaging a runner-shaped checkout rather than
# a developer one, which is the only place the two names differ.
NAME="${NAME:-$(basename "$PROJECT")}"
OUT="${OUT:-$PROJECT/dist}"
mkdir -p "$OUT" || exit 1
OUT="$(cd "$OUT" && pwd -P)"

# A leading v is how the tags are written and is not part of the version. plugin.cfg
# and the Asset Library both want the bare number.
VERSION="${VERSION#v}"

cd "$PROJECT" || exit 2
git rev-parse --is-inside-work-tree >/dev/null 2>&1 \
    || { printf '%s is not a git checkout, and the artifact is defined by what git tracks\n' "$NAME" >&2; exit 2; }

STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT

## The addons this repository OWNS, as opposed to the ones it links in to open.
##
## Ownership is decided by git, not by the filesystem: every linked dependency is
## gitignored in every project here, so a tracked addons/<name>/ is ours and an
## untracked one is somebody else's. Reading the directory instead would need a
## symlink test, which is right on Linux and wrong on Windows -- where the family
## COPIES addons rather than linking them, and a copied dependency is indistinguishable
## from owned source by any test except this one.
mapfile -t OWNED < <(git ls-files 'addons/*' | cut -d/ -f2 | sort -u)

artifacts=()

if [ "${#OWNED[@]}" -gt 0 ]; then
    git archive --format=tar HEAD | tar -x -C "$STAGE" || exit 1

    for addon in "${OWNED[@]}"; do
        [ -d "$STAGE/addons/$addon" ] || continue

        cfg="$STAGE/addons/$addon/plugin.cfg"
        if [ -f "$cfg" ]; then
            # Stamped in the ARTIFACT, not in the repository. The version of a release
            # is the tag -- that is the thing that is unique, signed by the push, and
            # impossible to forget to bump -- and a committed 0.1.0 that has to be
            # edited in lockstep across fifty-six repositories is a number that goes
            # wrong silently and is then shipped. Editing it here cannot drift because
            # nothing reads it between this line and the upload.
            sed -i -E "s|^version=\".*\"$|version=\"$VERSION\"|" "$cfg"
            grep -q "version=\"$VERSION\"" "$cfg" \
                || printf 'warning: %s/plugin.cfg has no version line to stamp\n' "$addon" >&2
        fi

        zip_path="$OUT/${addon}-${VERSION}.zip"
        rm -f "$zip_path"
        # Entries begin at addons/, so the zip installs by being unpacked at a project
        # root. README and LICENSE ride along INSIDE the addon folder rather than at
        # the top, where they would land in the consumer's project root and overwrite
        # theirs -- which is a thing addon zips do and is never what anyone wanted.
        for extra in README.md LICENSE; do
            [ -f "$STAGE/$extra" ] && [ ! -f "$STAGE/addons/$addon/$extra" ] \
                && cp "$STAGE/$extra" "$STAGE/addons/$addon/$extra"
        done
        ( cd "$STAGE" && zip -q -r "$zip_path" "addons/$addon" ) || exit 1
        artifacts+=("$zip_path")
        printf 'packed addons/%s -> %s\n' "$addon" "$(basename "$zip_path")" >&2
    done
fi

if [ "${#artifacts[@]}" -eq 0 ]; then
    # No owned addon: a game, the launcher, the deployment tool. The tracked tree,
    # under one top-level directory so it cannot explode into the cwd of whoever
    # unpacks it without looking.
    tar_path="$OUT/${NAME}-${VERSION}.tar.gz"
    rm -f "$tar_path"
    git archive --format=tar.gz --prefix="${NAME}-${VERSION}/" -o "$tar_path" HEAD || exit 1
    artifacts+=("$tar_path")
    printf 'packed the tracked tree -> %s\n' "$(basename "$tar_path")" >&2
fi

# A digest beside each artifact. The release page is not the only thing that consumes
# these -- whatever syncs them onward has to be able to say the bytes it got are the
# bytes that were built, and asking it to trust a redirect is not that.
( cd "$OUT" && sha256sum "${artifacts[@]##*/}" > SHA256SUMS ) || exit 1
artifacts+=("$OUT/SHA256SUMS")

printf '%s\n' "${artifacts[@]}"
