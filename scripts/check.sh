#!/usr/bin/env bash
#
# The family's two-step check, in the one place every repository can call it.
#
#   scripts/check.sh <project-dir>              import, parse, then run every suite
#   scripts/check.sh <project-dir> --parse      the import and parse passes only
#
# Both steps matter and step two is not optional. A clean parse says every file is
# valid GDScript; it says nothing at all about whether the thing works, and everything
# that has ever gone wrong here in spite of a clean parse is in docs/bugs-found.md.
#
# Environment:
#   GODOT         the runtime to use (default: godot on PATH)
#   SUITES        the scenes to run, space separated, relative and without .tscn.
#                 Empty means auto-detect -- see below.
#   SUITE_TIMEOUT seconds per suite (default 300)
#
# THE TIMEOUT IS LOAD BEARING, NOT TIDINESS. A scene whose script fails to parse
# HANGS rather than failing: the identifier does not resolve, the scene never loads,
# and nothing ever reaches get_tree().quit(). Uncapped, that is a runner sitting at
# the six-hour job limit with no output, reported as an infrastructure problem.
#
# WHICH SCENES ARE THE SUITES
#
# Auto-detection takes examples/*.tscn whose name contains `selftest` or begins with
# `headless_` -- the two names this family gives a scene that runs to a conclusion and
# quits. It deliberately does NOT run everything in examples/: several of those are
# demos that open a window, wait for input, or want a peer on the other end of a
# socket, and a demo that waits forever is indistinguishable here from the parse-error
# hang above. A repository whose suite is named something else sets SUITES.
#
# A repository with no detectable suite is REPORTED AND PASSES. Failing it would only
# teach people to delete the workflow; the parse pass still ran, and the summary says
# which repositories are getting half a check so the list can shrink on purpose.
#
set -uo pipefail

PROJECT="${1:-.}"
[ -d "$PROJECT" ] || { printf 'no such directory: %s\n' "$PROJECT" >&2; exit 2; }
cd "$PROJECT" || exit 2

GODOT="${GODOT:-godot}"
SUITE_TIMEOUT="${SUITE_TIMEOUT:-300}"
RED=$'\033[31m'; GRN=$'\033[32m'; YLW=$'\033[33m'; OFF=$'\033[0m'
fails=0
ran=0

# Shutdown noise that is not a parse error, matched exactly so that anything else is.
#
# This filter is the whole guard: the parse pass treats ANY unfiltered output as a
# failure, which is what makes it catch errors Godot reports without a non-zero exit.
# The engine is free to reword this noise and did -- 4.7 turned "ObjectDB instances
# leaked at exit" into "5 ObjectDB instances were leaked at exit", and the guard then
# called two clean scripts parse failures, which is how a guard stops being read.
# Hence ( were )? rather than either literal wording.
## The scripts this repository is answerable for.
##
## `git ls-files` rather than `find`, because the two disagree in exactly the place
## that matters. An addon repository's own source lives in addons/<its name>/, and the
## DEPENDENCIES sit right beside it in that same directory -- so "skip addons/" parses
## none of dot-cloud and "parse addons/" parses all thirty-one files of dot-core on
## every one of its consumers, turning one broken dependency into a failure reported
## against fifty repositories. What separates them is not the path, it is ownership:
## the links are gitignored in every project here, which makes the tracked set exactly
## "ours" and nothing else.
##
## The fallback matters for a run outside a checkout (a release tarball, a container).
## find does not follow symlinks unless told to, so linked dependencies are skipped
## there too -- but a COPIED one would not be, which is why git is preferred when it
## can answer.
project_scripts() {
    if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
        git ls-files '*.gd' | sort
    else
        find . -name '*.gd' -not -path './.godot/*' -not -path './.deps/*' \
            | sed 's|^\./||' | sort
    fi
}

NOISE='ObjectDB instances( were)? leaked|resources still in use|Pages in use exist at exit|at: (cleanup|clear|~PagedAllocator)|WARNING: .*Text-based project'

echo "importing"
# --import registers the class_name globals. Without it every cross-file type
# reference fails and it reads as dozens of unrelated errors rather than as one
# missing pass -- and it has to be re-run after any script with a NEW class_name.
timeout 600 "$GODOT" --headless --path . --import >/dev/null 2>&1

echo "parsing"
while read -r f; do
    out="$(timeout 120 "$GODOT" --headless --path . --check-only --script "res://${f#./}" 2>&1 \
        | grep -Ev '^(Godot Engine v|$)' \
        | grep -Eiv "$NOISE")"
    if [ -n "$out" ]; then
        printf '  %sFAIL%s %s\n%s\n' "$RED" "$OFF" "$f" "$out"
        fails=$((fails + 1))
    fi
done < <(project_scripts)

[ "$fails" -eq 0 ] && printf '  %sok%s   every script parses\n' "$GRN" "$OFF"

if [ "${2:-}" = "--parse" ]; then
    exit $((fails > 0))
fi

if [ -z "${SUITES:-}" ]; then
    SUITES="$(ls examples/*.tscn 2>/dev/null \
        | sed 's|\.tscn$||' \
        | grep -E '(selftest|/headless_)' \
        | tr '\n' ' ')"
fi

# Unquoted on purpose: SUITES is a space-separated list and the split is the point.
# shellcheck disable=SC2086
for scene in $SUITES; do
    [ -f "$scene.tscn" ] || { printf '  %s--%s   %s.tscn is not here\n' "$YLW" "$OFF" "$scene"; continue; }
    echo
    echo "running $scene"
    ran=$((ran + 1))

    out="$(timeout "$SUITE_TIMEOUT" "$GODOT" --headless --path . "res://$scene.tscn" 2>&1)"
    status=$?
    printf '%s\n' "$out"

    if [ "$status" -eq 124 ]; then
        printf '  %sFAIL%s %s did not finish within %ss\n' "$RED" "$OFF" "$scene" "$SUITE_TIMEOUT"
        fails=$((fails + 1))
    elif [ "$status" -ne 0 ]; then
        printf '  %sFAIL%s %s exited %d\n' "$RED" "$OFF" "$scene" "$status"
        fails=$((fails + 1))
    elif printf '%s' "$out" | grep -qE 'SCRIPT ERROR|Parse Error'; then
        # EXIT 0 IS NOT A PASS HERE, and this is the check the suites cannot do for
        # themselves.
        #
        # SCRIPT ERROR and Parse Error only. NOT the engine's own `ERROR: Condition
        # "..." is true.`, which was in this pattern until dot-game's suite failed on
        # it: that line comes from inside the engine, several of these suites provoke
        # one ON PURPOSE to prove a no-op is a no-op rather than a crash, and failing
        # on it means the repositories with the most careful tests are the ones that
        # go red. A guard that fires on correct code is a guard people delete. A script error inside a test aborts THAT TEST, not the run: the
        # section had already announced itself, so the section counter is satisfied,
        # the suite reports "0 failed" and quits cleanly with its checks missing.
        # dot-settings shipped exactly that -- "8 sections, 63 passed, 0 failed", exit
        # 0, eight checks that never ran. The engine still printed the error.
        printf '  %sFAIL%s %s exited 0 with a script error in its output\n' "$RED" "$OFF" "$scene"
        fails=$((fails + 1))
    fi
done

echo
if [ "$ran" -eq 0 ]; then
    printf '%s--%s   no headless suite in this repository; the parse pass is the whole check\n' \
        "$YLW" "$OFF"
fi
if [ "$fails" -eq 0 ]; then
    printf '%sall checks passed%s (%d suite(s))\n' "$GRN" "$OFF" "$ran"
else
    printf '%s%d failed%s\n' "$RED" "$fails" "$OFF"
fi
exit $((fails > 0))
