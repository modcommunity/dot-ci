#!/usr/bin/env bash
#
# Pack every directory under one folder of an imported project as a pack of its own.
#
#   scripts/package-subpacks.sh <project> <version> --root maps/imported --out <dir> [id ...]
#
# WHAT IT IS FOR
#
# Maps. A game that delivers its maps publishes each one as its own pack -- a server
# fetches the map it changes to and a player downloads the one being played, so a server
# offering thirty courses does not make anybody download thirty. The maps live in their
# own repository (g2gfast-maps), but only a Godot project that has IMPORTED them can
# produce what a pack needs: the imported outputs (`.ctex` and friends) that its `.import`
# markers name. So this runs inside the game's project, with the map repository linked in
# at <root>, after `godot --headless --import`, exactly as package.sh --pack runs after an
# import for the game itself.
#
# Each `<root>/<id>/` becomes `<id>-<version>-pack.zip`, which website-city's release sync
# publishes as `<owner>/<id>@<version>` -- one release of the map repository, one pack per
# map.
#
# WHAT A PACK ZIP HOLDS, AND THE ONE DIFFERENCE FROM A GAME'S
#
# The directory's files at the zip's top level; the imported outputs its markers name,
# under `_imported/` with the markers rewritten to match (package.sh --pack's rule, and
# the web export's reason for it); no `*.gd.uid`. The difference: a game's pack is rooted
# at `res://`, a map's at `res://<root>/<id>/`. A marker inside the project names its
# source as `res://maps/imported/surf_mesa/x.png`, which the site would not recognise as
# a file in the pack -- it rewrites only references to paths the pack holds, relative to
# its root -- so references to the map's own directory are re-rooted to `res://` here,
# and the site then moves them under the mount prefix like any other.
#
# No requires.json: a map pack carries data, not scripts, and a pack with no such file
# needs nothing a host can check.
set -uo pipefail

PROJECT="${1:-}"
VERSION="${2:-}"
[ -n "$PROJECT" ] && [ -d "$PROJECT" ] && [ -n "$VERSION" ] \
    || { printf 'usage: %s <project> <version> --root <dir> --out <dir> [id ...]\n' "$0" >&2; exit 2; }
shift 2

ROOT=""
OUT=""
IDS=()
while [ $# -gt 0 ]; do
    case "$1" in
        --root) ROOT="${2:-}"; shift 2 ;;
        --out)  OUT="${2:-}"; shift 2 ;;
        -*)     printf 'unknown option: %s\n' "$1" >&2; exit 2 ;;
        *)      IDS+=("$1"); shift ;;
    esac
done

[ -n "$ROOT" ] && [ -n "$OUT" ] || { printf -- '--root and --out are required\n' >&2; exit 2; }
ROOT="${ROOT%/}"
PROJECT="$(cd "$PROJECT" && pwd -P)"
mkdir -p "$OUT" && OUT="$(cd "$OUT" && pwd -P)"

[ -d "$PROJECT/$ROOT" ] || { printf 'no %s in %s\n' "$ROOT" "$PROJECT" >&2; exit 2; }
[ -d "$PROJECT/.godot/imported" ] || {
    printf '%s has not been imported: run godot --headless --import first\n' "$PROJECT" >&2
    exit 2
}

# A version is one path component of a mount path, as for any pack.
case "$VERSION" in
    */*|*..*|'') printf 'version %s cannot be one path component\n' "$VERSION" >&2; exit 2 ;;
esac

if [ ${#IDS[@]} -eq 0 ]; then
    while IFS= read -r d; do IDS+=("$d"); done \
        < <(find -L "$PROJECT/$ROOT" -mindepth 1 -maxdepth 1 -type d -printf '%f\n' | sort)
fi

STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT

artifacts=()
fails=0

for id in "${IDS[@]}"; do
    case "$id" in .*|*/*) continue ;; esac
    src="$PROJECT/$ROOT/$id"
    [ -d "$src" ] || { printf '  FAIL  %s: no %s/%s\n' "$id" "$ROOT" "$id" >&2; fails=$((fails + 1)); continue; }

    dir="$STAGE/$id"
    rm -rf "$dir"
    mkdir -p "$dir"
    # -L: the root is normally a link to another repository, and so may be what is
    # inside it. A pack carries the bytes, never a link that dangles once mounted.
    cp -rL "$src/." "$dir/" || { fails=$((fails + 1)); continue; }
    find "$dir" \( -name '*.gd.uid' -o -name '.godot' -o -name '.git' \) -prune -exec rm -rf {} + 2>/dev/null

    imported=0
    missing=0
    while IFS= read -r -d '' marker; do
        while IFS= read -r res; do
            rel="${res#res://}"
            if [ -f "$PROJECT/$rel" ]; then
                mkdir -p "$dir/_imported"
                cp "$PROJECT/$rel" "$dir/_imported/${rel#.godot/imported/}" || exit 1
                imported=$((imported + 1))
            else
                printf '  missing imported output: %s (from %s/%s)\n' "$rel" "$id" "${marker#"$dir"/}" >&2
                missing=$((missing + 1))
            fi
        done < <(grep -o 'res://\.godot/imported/[^"]*' "$marker" | sort -u)
    done < <(find "$dir" -name '*.import' -type f -print0)

    if [ "$missing" -gt 0 ]; then
        printf '  FAIL  %s: %d imported outputs are missing; re-import and try again\n' "$id" "$missing" >&2
        fails=$((fails + 1))
        continue
    fi

    # Re-root: the project's paths to this directory become the pack's own root, and the
    # engine's imported directory becomes _imported/. Only in the text resources the site
    # rewrites (website-city's REWRITABLE: tscn, tres, import), so a binary is never
    # touched by a sed that does not know it is binary.
    while IFS= read -r -d '' text; do
        sed -i -e "s|res://\.godot/imported/|res://_imported/|g" \
               -e "s|res://$ROOT/$id/|res://|g" "$text" || exit 1
    done < <(find "$dir" \( -name '*.import' -o -name '*.tscn' -o -name '*.tres' \) -type f -print0)

    zip_path="$OUT/${id}-${VERSION}-pack.zip"
    rm -f "$zip_path"
    ( cd "$dir" && zip -q -r -y -X "$zip_path" . ) || { fails=$((fails + 1)); continue; }
    artifacts+=("$zip_path")
    printf '  packed %s with %d imported outputs -> %s\n' "$id" "$imported" "$(basename "$zip_path")" >&2
done

if [ ${#artifacts[@]} -gt 0 ]; then
    ( cd "$OUT" && sha256sum "${artifacts[@]##*/}" > SHA256SUMS ) || exit 1
fi

printf '%d packed, %d failed\n' "${#artifacts[@]}" "$fails" >&2
printf '%s\n' "${artifacts[@]}"
exit $((fails > 0))
