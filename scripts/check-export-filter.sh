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
# A preset passes with `cfg/*`, `cfg/addons/*` or `*.yml` in its include_filter.
set -uo pipefail
dir="${1:-.}"
[ -d "$dir" ] || { printf 'no such directory: %s\n' "$dir" >&2; exit 2; }
bad=0
for f in "$dir/export_presets.cfg" "$dir/export_presets.example.cfg"; do
    [ -f "$f" ] || continue
    preset=""
    while IFS= read -r line; do
        case "$line" in
            "[preset."*".options]") ;;
            "[preset."*"]") preset="$line" ;;
            name=*) pname="${line#name=}" ;;
            include_filter=*)
                if ! grep -Eq 'cfg/\*|cfg/addons/\*|\*\.yml' <<<"$line"; then
                    printf 'FAIL %s %s %s: include_filter lacks cfg/* (cfg/addons/*.yml is dropped from the export)\n' "$f" "$preset" "${pname:-}" >&2
                    bad=1
                fi ;;
        esac
    done < "$f"
done
[ "$bad" = 0 ] && echo "export filters ok"
exit "$bad"
