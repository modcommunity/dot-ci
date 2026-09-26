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
#   With --pack, a game ALSO ships <name>-<version>-pack.zip: the tree the publisher
#   turns into that signed pack. The tarball cannot be it, and not for want of a
#   format -- it has no addons (they are gitignored links) and no .godot/imported, and
#   a mounted pack is never re-imported, so every texture and model in it would fail
#   to load and say nothing. The pack zip is the tracked tree minus what the host
#   already has or no player needs (addons, examples, tools, screenshots, and any
#   --exclude-dir), plus exactly the imported outputs the remaining .import files
#   name. It is UNSIGNED: website-city publishes a release file ending in -pack.zip in
#   place of everything else on the release, and signs it there.
#
#   --pack needs the checkout IMPORTED first (`godot --headless --import`), with its
#   addons resolved so the import can see them. release.yml does both when the caller
#   passes `pack: true`.
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

USAGE="usage: package.sh <project-dir> <version> [--out DIR] [--name NAME] [--pack [--exclude-dir DIR]...]"
PROJECT="${1:?$USAGE}"
VERSION="${2:?$USAGE}"
shift 2
OUT=""
NAME=""
PACK=0
# What a game pack never carries, at any depth. addons/ above all: every dot-* addon
# is already in the host build, and packing a game with its addons produced an 11 MiB
# pack of which the game was a fraction. The same list dot-server-deploy's
# content/<id>/pack.json files give, which is what a pack published from there holds.
EXCLUDE_DIRS=(addons examples tools screenshots .github)
while [ $# -gt 0 ]; do
    case "$1" in
        --out)  OUT="${2:?--out needs a directory}"; shift 2 ;;
        --name) NAME="${2:?--name needs a name}"; shift 2 ;;
        --pack) PACK=1; shift ;;
        --exclude-dir) EXCLUDE_DIRS+=("${2:?--exclude-dir needs a name}"); shift 2 ;;
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

    if [ "$PACK" -eq 1 ]; then
        [ -d "$PROJECT/.godot/imported" ] || {
            printf '%s has not been imported: --pack needs `godot --headless --import` first\n' "$NAME" >&2
            exit 2
        }

        PACK_DIR="$STAGE/pack"
        mkdir -p "$PACK_DIR" || exit 1
        git archive --format=tar HEAD | tar -x -C "$PACK_DIR" || exit 1

        for d in "${EXCLUDE_DIRS[@]}"; do
            find "$PACK_DIR" -depth -type d -name "$d" -exec rm -rf {} + || exit 1
        done
        # A script's .uid sidecar is editor bookkeeping; DotCloudPublisher leaves it out
        # too, and the two publishers should produce the same pack from the same tree.
        find "$PACK_DIR" -name '*.gd.uid' -type f -delete || exit 1

        # The imported outputs, chosen by the .import files that SURVIVED the
        # exclusions rather than by copying .godot/imported whole. That directory holds
        # the output of every asset in the checkout, examples and screenshots included,
        # and one game's excluded map folder is most of its bytes.
        # Under _imported/, NOT at .godot/imported/ where they live in the project,
        # with every marker rewritten to match. A web export cannot read the engine's
        # own reserved directory back out of a mounted pack -- "A required file is not
        # readable after mounting" -- while Linux reads it fine, so a headless check
        # passes on the platform that does not matter. DotCloudPublisher.IMPORTED_DIR
        # is the same name for the same reason; a marker names its output by absolute
        # path, so the directory can be anything the marker agrees with.
        IMPORTED_DIR="_imported"
        imported=0
        missing=0
        while IFS= read -r -d '' marker; do
            while IFS= read -r res; do
                rel="${res#res://}"
                if [ -f "$PROJECT/$rel" ]; then
                    mkdir -p "$PACK_DIR/$IMPORTED_DIR" || exit 1
                    cp "$PROJECT/$rel" "$PACK_DIR/$IMPORTED_DIR/${rel#.godot/imported/}" || exit 1
                    imported=$((imported + 1))
                else
                    # A marker naming an output the import did not write is an asset
                    # that will not load from the pack. Said here, where it can be
                    # fixed, instead of on a player's machine where it cannot.
                    printf 'missing imported output: %s (from %s)\n' "$rel" "${marker#"$PACK_DIR"/}" >&2
                    missing=$((missing + 1))
                fi
            done < <(grep -o 'res://\.godot/imported/[^"]*' "$marker" | sort -u)
            sed -i 's|res://\.godot/imported/|res://'"$IMPORTED_DIR"'/|g' "$marker" || exit 1
        done < <(find "$PACK_DIR" -name '*.import' -type f -print0)

        [ "$missing" -eq 0 ] || { printf '%d imported outputs are missing; re-import and try again\n' "$missing" >&2; exit 1; }

        pack_path="$OUT/${NAME}-${VERSION}-pack.zip"
        rm -f "$pack_path"
        # Entries at the top level, not under a wrapper directory: the publisher strips
        # a common root anyway, and a pack whose files sit one level down mounts where
        # no reference resolves.
        ( cd "$PACK_DIR" && zip -q -r -y "$pack_path" . ) || exit 1
        artifacts+=("$pack_path")
        printf 'packed the game with %d imported outputs -> %s\n' "$imported" "$(basename "$pack_path")" >&2
    fi
elif [ "$PACK" -eq 1 ]; then
    # An addon's zip is already the thing a pack is made from.
    printf 'note: --pack ignored for an addon repository\n' >&2
fi

# A digest beside each artifact. The release page is not the only thing that consumes
# these -- whatever syncs them onward has to be able to say the bytes it got are the
# bytes that were built, and asking it to trust a redirect is not that.
( cd "$OUT" && sha256sum "${artifacts[@]##*/}" > SHA256SUMS ) || exit 1
artifacts+=("$OUT/SHA256SUMS")

printf '%s\n' "${artifacts[@]}"
