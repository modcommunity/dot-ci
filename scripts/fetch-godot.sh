#!/usr/bin/env bash
#
# Fetch the pinned Godot runtime for a Linux CI runner, verify it, and print the
# path to it on stdout.
#
#   scripts/fetch-godot.sh [--dest DIR]
#   scripts/fetch-godot.sh --version        print the pinned version and exit
#
# Everything said to a person goes to stderr, because stdout is the path and the
# caller reads it with $(...).
#
# The verification IS the program. A mismatch is fatal, the file is deleted, and
# there is no --force and no "checksum unavailable, continuing" -- a script that
# fetches a binary without verifying it is a supply chain with nobody in it, and CI
# runs unattended on every push, which is the worst possible place to have one.
#
# The pin and the digest live in godot.pin beside this script; that file says why it
# is a copy of dot-server-deploy's and what guards the drift.
#
# Only Linux x86_64 is handled, deliberately. That is what GitHub's runners are, and
# an untested branch for a platform nothing here runs on is a branch that is wrong
# the first time somebody needs it.
#
set -uo pipefail

SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
PIN="$SELF_DIR/../godot.pin"
[ -f "$PIN" ] || { printf 'godot.pin is missing beside %s\n' "$SELF_DIR" >&2; exit 2; }

# Only the two assignments, and only in the shape this file writes them. Sourcing the
# pin would make a comment in it executable, which is not what a pin is for.
GODOT_VERSION="$(grep -oE '^GODOT_VERSION=.+$' "$PIN" | head -1 | cut -d= -f2-)"
WANT="$(grep -oE '^SHA512_linux_x86_64=[0-9a-f]+$' "$PIN" | head -1 | cut -d= -f2-)"

[ -n "$GODOT_VERSION" ] || { printf 'godot.pin declares no GODOT_VERSION\n' >&2; exit 2; }
[ -n "$WANT" ]          || { printf 'godot.pin declares no SHA512_linux_x86_64\n' >&2; exit 2; }

DEST="${RUNNER_TOOL_CACHE:-$HOME/.cache}/dot-godot/$GODOT_VERSION"
while [ $# -gt 0 ]; do
    case "$1" in
        --dest)    DEST="${2:?--dest needs a directory}"; shift 2 ;;
        --version) printf '%s\n' "$GODOT_VERSION"; exit 0 ;;
        *) printf 'unknown option: %s\n' "$1" >&2; exit 2 ;;
    esac
done

ASSET="Godot_v${GODOT_VERSION}_linux.x86_64.zip"
BINARY="Godot_v${GODOT_VERSION}_linux.x86_64"
URL="https://github.com/godotengine/godot/releases/download/${GODOT_VERSION}/${ASSET}"

# Already there and already verified. The cache key is the version, and the version
# names an immutable release asset, so a hit cannot be a different file.
if [ -x "$DEST/$BINARY" ]; then
    printf 'godot %s is already in %s\n' "$GODOT_VERSION" "$DEST" >&2
    printf '%s\n' "$DEST/$BINARY"
    exit 0
fi

mkdir -p "$DEST" || exit 1
printf 'fetching %s\n' "$URL" >&2
curl -fsSL --retry 3 --retry-delay 5 -o "$DEST/$ASSET" "$URL" \
    || { printf 'could not download %s\n' "$ASSET" >&2; exit 1; }

GOT="$(sha512sum "$DEST/$ASSET" | awk '{print $1}')"
if [ "$GOT" != "$WANT" ]; then
    rm -f "$DEST/$ASSET"
    printf 'SHA512 MISMATCH for %s\n  want %s\n  got  %s\nthe file has been deleted\n' \
        "$ASSET" "$WANT" "$GOT" >&2
    exit 1
fi
printf 'sha512 verified\n' >&2

# < /dev/null is not decoration: unzip answers a write error by ASKING, and on a
# runner with nobody to answer it that is a job that hangs rather than fails.
unzip -q -o "$DEST/$ASSET" -d "$DEST" < /dev/null || exit 1
rm -f "$DEST/$ASSET"
chmod +x "$DEST/$BINARY" || exit 1

[ -x "$DEST/$BINARY" ] || { printf 'the archive did not contain %s\n' "$BINARY" >&2; exit 1; }
printf '%s\n' "$DEST/$BINARY"
