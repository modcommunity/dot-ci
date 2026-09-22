#!/usr/bin/env bash
#
# Put the addons a project needs into its addons/, on a machine that has nothing.
#
#   scripts/resolve-deps.sh <project-dir>
#   scripts/resolve-deps.sh <project-dir> --print   name the repositories, clone nothing
#
# WHY A RUNNER NEEDS THIS AT ALL
#
# The links in addons/ are gitignored in every project here, on purpose: a consumer
# copies the addon folder into its own tree rather than depending on a checkout of
# ours. So a fresh `git clone` of any project except dot-core opens with no addons,
# and in GDScript that is not a missing-feature situation -- a script that MENTIONS a
# class_name the project does not have fails to parse, and takes every script that
# references it down with it. One unresolved addon is a hundred parse errors that name
# identifiers rather than the missing directory, which reads exactly like a broken
# repository. The whole parse pass is worthless until this has run.
#
# THE LIST IS NOT HERE, AND THAT IS THE POINT
#
# The addons a project needs come from that project's OWN .gitignore, from its
# /addons/<name> lines -- the same derivation bootstrap.sh does, for the same reason:
# the repository that gains a dependency is the repository that has to ignore the
# link, so the list maintains itself and cannot drift. A manifest in this repository
# would be a second copy of fifty-odd lists, which is the exact bug projects.tsv was
# written to stop and which this family has already shipped three times.
#
# A project with no /addons/<name> lines needs nothing (dot-core), or vendors its own
# (dot-server-deploy, whose .gitignore is a bare `/addons/` -- "ignore the lot", which
# names nothing to link and must not be read as "link everything").
#
# THE OWNER SPLIT IS ENCODED HERE, AND THAT IS A THIRD COPY ON PURPOSE
#
# The addons are the organisation's and the games are their author's. projects.tsv is
# the one list that records which is which, and dot-server-deploy's setup.sh already
# carries a second copy of the RULE for the one case that cannot read that file: a
# fresh box cloning what it needs before dot-bootstrap is on it. A CI runner is the
# same case -- it has an empty disk and a token, and reaching projects.tsv would mean
# cloning dot-bootstrap first to find out where to clone dot-core from. So the rule is
# repeated, in two lines, and not the list.
#
# CREDENTIALS come from the environment and never from an argument: an argument is in
# the runner log, in the process list, and in `ps`.
#
#   DEPS_TOKEN   a token that can read the private addon repositories
#   GIT_HOST     default github.com
#   DOT_OWNER    default modcommunity   (the addons)
#   GAME_OWNER   default gamemann       (the games, and the weapons pack)
#
set -uo pipefail

PROJECT="${1:-.}"
MODE="${2:-clone}"

[ -d "$PROJECT" ] || { printf 'no such directory: %s\n' "$PROJECT" >&2; exit 2; }
PROJECT="$(cd "$PROJECT" && pwd -P)"

GIT_HOST="${GIT_HOST:-github.com}"
DOT_OWNER="${DOT_OWNER:-modcommunity}"
GAME_OWNER="${GAME_OWNER:-gamemann}"
DEPS_DIR="$PROJECT/.deps"

## The repository an addon directory lives in.
##
## dot_user_avatar -> dot-user-avatar, true for every link in the family except one:
## the weapons pack took the prefix `zee_` so it could sit on top of the family
## without colliding with it, and its repository is named for what it IS rather than
## for its prefix. Same exception setup.sh's addon_repo() carries.
addon_repo() {
    case "$1" in
        zee_weapons) printf 'zee-dot-weapons\n' ;;
        *)           printf '%s\n' "${1//_/-}" ;;
    esac
}

## Who owns it. See the note above about why this rule is here and the list is not.
addon_owner() {
    case "$1" in
        dot-*) printf '%s\n' "$DOT_OWNER" ;;
        *)     printf '%s\n' "$GAME_OWNER" ;;
    esac
}

# /addons/ on its own names nothing. The anchored, single-segment pattern is what
# makes that true: `/addons/` does not match `^/addons/[a-z0-9_]+$`, and a project
# that vendors its addons therefore resolves zero of them rather than all of them.
mapfile -t ADDONS < <(grep -oE '^/addons/[a-z0-9_]+$' "$PROJECT/.gitignore" 2>/dev/null \
    | sed 's|^/addons/||' | sort -u)

if [ "${#ADDONS[@]}" -eq 0 ]; then
    printf 'no addon dependencies declared in %s/.gitignore\n' "$(basename "$PROJECT")" >&2
    exit 0
fi

if [ "$MODE" = "--print" ]; then
    for a in "${ADDONS[@]}"; do printf '%s\t%s\n' "$a" "$(addon_repo "$a")"; done
    exit 0
fi

# The token is OPTIONAL, and which way it goes is not this script's to decide. Every
# repository in the family is public as this is written, and a public clone needs no
# credential at all -- so demanding one would fail every check in the family over a
# secret nothing needs. One going private later must not need a change here either,
# which is the whole reason the caller passes a secret that is usually empty.
CREDENTIAL=""
[ -n "${DEPS_TOKEN:-}" ] && CREDENTIAL="x-access-token:${DEPS_TOKEN}@"

## Keep the token out of anything printed.
##
## A no-op when there is no token, and that case is not hypothetical -- `sed s||***|g`
## with an empty pattern replaces at EVERY position, so an unauthenticated clone
## failure would print a wall of asterisks instead of the reason it failed.
_redact() {
    if [ -n "${DEPS_TOKEN:-}" ]; then
        sed "s|${DEPS_TOKEN}|***|g"
    else
        cat
    fi
}

mkdir -p "$DEPS_DIR" "$PROJECT/addons"

# .gdignore, and it is not belt and braces. The clones land INSIDE the project, so
# Godot's import pass walks them -- and a second copy of dot-core's scripts under a
# different path does not fail as "there are two", it fails as `Class "DotResult"
# hides a global script class`, once per class, naming files that are all correct.
# A dot-prefixed directory being skipped is the editor's behaviour and not a promise;
# this file is the documented way to say it, and it costs nothing.
printf '' > "$DEPS_DIR/.gdignore"

fails=0

for addon in "${ADDONS[@]}"; do
    repo="$(addon_repo "$addon")"
    owner="$(addon_owner "$repo")"

    if [ ! -d "$DEPS_DIR/$repo/.git" ]; then
        # --depth 1: CI wants the files, never the history, and dot-core's history is
        # larger than every addon it ships. The token is interpolated into the URL
        # rather than passed as an argument so it is never a separate word anything
        # logs; git itself keeps it out of the error text.
        if ! err="$(git clone --quiet --depth 1 \
            "https://${CREDENTIAL}${GIT_HOST}/${owner}/${repo}.git" \
            "$DEPS_DIR/$repo" 2>&1)"; then
            # git echoes the URL it was given, and the URL carries the token. Redacted
            # here rather than discarded: a clone failure with no reason printed is
            # half an hour of guessing between "the token cannot see it", "the
            # repository is not created yet" and "the name is wrong", and those want
            # three different fixes.
            printf '  FAIL  could not clone %s/%s (for addons/%s)\n        %s\n' \
                "$owner" "$repo" "$addon" \
                "$(printf '%s' "$err" | _redact | tr '\n' ' ')" >&2
            fails=$((fails + 1))
            continue
        fi
    fi

    if [ ! -d "$DEPS_DIR/$repo/addons/$addon" ]; then
        printf '  FAIL  %s has no addons/%s\n' "$repo" "$addon" >&2
        fails=$((fails + 1))
        continue
    fi

    # Replaced unconditionally. A stale link, or a regular file a checkout on a machine
    # without symlink support left behind, both have to go -- and the second is not
    # hypothetical: Git writes the link's TARGET PATH into a text file when it cannot
    # make one, and Godot then reads a one-line text file where a directory should be
    # and registers not one class_name.
    rm -rf "${PROJECT:?}/addons/$addon"
    ln -s "../.deps/$repo/addons/$addon" "$PROJECT/addons/$addon"
    printf '  linked addons/%s -> %s\n' "$addon" "$repo"
done

printf '%d addon(s) declared, %d failed\n' "${#ADDONS[@]}" "$fails"
exit $((fails > 0))
