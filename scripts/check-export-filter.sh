#!/usr/bin/env bash
#
# Fails a repository whose export presets would drop the addons' cfg/addons/*.yml.
#
#   scripts/check-export-filter.sh <project-dir>
#
# Godot's exporter packs resources and whatever include_filter names, and .yml is not a
# resource. dot-core's DotAddonConfig reads res://cfg/addons/<name>/*.yml, so an export
# without a cfg filter ships without the addon defaults and the missing-directory rule
# (a missing directory is not an error) hides it. Both export_presets.cfg and the
# export_presets.example.cfg a repository ships in its place (the editor rewrites the
# real one, so it is usually gitignored) are checked; no presets file is a pass.
# A preset passes with `cfg/*`, `cfg/addons/*` or `*.yml` in its include_filter. An
# exclude_filter naming cfg/ is a deliberate "ships no cfg" (it beats the include): a note,
# not a failure, but a WARN when the include also names cfg, since that include then ships
# nothing. No include and no such exclude still fails.
set -uo pipefail
dir="${1:-.}"
[ -d "$dir" ] || { printf 'no such directory: %s\n' "$dir" >&2; exit 2; }
bad=0
# One verdict per preset, taken when the next preset (or the end of the file) closes it,
# because exclude_filter follows include_filter and an exclude beats an include.
judge() {
    [ -n "${preset:-}" ] && [ -n "${have_inc:-}" ] || return 0
    if grep -Eq 'cfg/\*|cfg/addons/\*' <<<"$exc"; then
        if grep -Eq 'cfg/\*|cfg/addons/\*|\*\.yml' <<<"$inc"; then
            printf 'WARN %s %s %s: exclude_filter covers cfg/* and beats the include_filter, so cfg/addons/*.yml is not shipped; narrow the exclude or drop the include\n' "$f" "$preset" "${pname:-}" >&2
        else
            printf 'note %s %s %s: exclude_filter drops cfg/ on purpose (a shell with no addon defaults of its own)\n' "$f" "$preset" "${pname:-}"
        fi
    elif ! grep -Eq 'cfg/\*|cfg/addons/\*|\*\.yml' <<<"$inc"; then
        printf 'FAIL %s %s %s: include_filter lacks cfg/* (cfg/addons/*.yml is dropped from the export)\n' "$f" "$preset" "${pname:-}" >&2
        bad=1
    fi
}
for f in "$dir/export_presets.cfg" "$dir/export_presets.example.cfg"; do
    [ -f "$f" ] || continue
    preset="" have_inc="" inc="" exc="" pname=""
    while IFS= read -r line; do
        case "$line" in
            "[preset."*".options]") ;;
            "[preset."*"]") judge; preset="$line" have_inc="" inc="" exc="" pname="" ;;
            name=*) pname="${line#name=}" ;;
            include_filter=*) inc="$line" have_inc=1 ;;
            exclude_filter=*) exc="$line" ;;
        esac
    done < "$f"
    judge
done
[ "$bad" = 0 ] && echo "export filters ok"
exit "$bad"
