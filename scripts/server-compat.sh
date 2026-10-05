#!/usr/bin/env bash
#
# Refuse a game pack that no released server could run.
#
#   scripts/server-compat.sh <requires.json | pack.zip>
#   scripts/server-compat.sh <requires.json | pack.zip> --server-ref v0.1.8
#
# WHY A RELEASE HAS TO ASK THIS
#
# A game pack says which dot-* addon API levels it was built against (requires.json, see
# dot-core's DotAddonApi). A server checks that list before mounting the pack and refuses
# one it cannot satisfy -- correctly, and too late: by then the pack is published, the
# site offers it, and a server that restarts onto it boots into "This game needs
# dot-platform API level 3 or newer; this server has level 2". That happened on
# 2026-10-04 with game-g2gfast v0.1.5, because the addon release it needed existed only
# as untagged commits when the game was tagged.
#
# So the same rule is asked here, of the newest RELEASED server: the addons.lock of
# modcommunity/dot-server-deploy's highest v* tag names the ref of every addon a box
# installs, and each addon's level is the `const LEVEL` / `const OLDEST` in its
# addons/<addon>/<addon>_api.gd at that ref (absent means 1, as DotAddonApi reads it).
# A game passes when, for every addon it names: the lock has it, need <= LEVEL, and
# need >= OLDEST. The fix for a failure is never here -- it is to tag the addon, bump the
# lock, and release dot-server-deploy, then re-tag the game.
#
# Environment:
#   SERVER_REPO   default modcommunity/dot-server-deploy
#   DEPS_TOKEN    optional; read access for private repositories (never printed)
#   DOT_OWNER     default modcommunity   (the addons)
#   GAME_OWNER    default gamemann       (zee-dot-weapons, the one addon that is not)
set -uo pipefail

INPUT="${1:-}"
[ -n "$INPUT" ] && [ -f "$INPUT" ] || { printf 'usage: %s <requires.json|pack.zip> [--server-ref TAG]\n' "$0" >&2; exit 2; }
shift

SERVER_REF=""
while [ $# -gt 0 ]; do
    case "$1" in
        --server-ref) SERVER_REF="${2:-}"; shift 2 ;;
        *) printf 'unknown argument: %s\n' "$1" >&2; exit 2 ;;
    esac
done

export INPUT SERVER_REF
export SERVER_REPO="${SERVER_REPO:-modcommunity/dot-server-deploy}"
export DOT_OWNER="${DOT_OWNER:-modcommunity}"
export GAME_OWNER="${GAME_OWNER:-gamemann}"

exec python3 - <<'PY'
import json, os, re, subprocess, sys, urllib.error, urllib.request, zipfile

inp = os.environ["INPUT"]
if inp.endswith(".zip"):
    with zipfile.ZipFile(inp) as z:
        if "requires.json" not in z.namelist():
            print(f"  --   {os.path.basename(inp)} carries no requires.json; nothing to check")
            sys.exit(0)
        requires = json.loads(z.read("requires.json"))
else:
    requires = json.load(open(inp))

needs = {str(k): int(v) for k, v in (requires.get("addons") or {}).items()}
token = os.environ.get("DEPS_TOKEN", "")
repo = os.environ["SERVER_REPO"]


def fetch(owner_repo, ref, path):
    url = f"https://raw.githubusercontent.com/{owner_repo}/{ref}/{path}"
    req = urllib.request.Request(url)
    if token:
        req.add_header("Authorization", f"token {token}")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.read().decode()
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise


ref = os.environ.get("SERVER_REF", "")
if not ref:
    # The highest v<major>.<minor>.<patch> tag: what a box installed today gets. A tag
    # rather than main, because main can be ahead of anything a box has.
    url = f"https://{'x-access-token:' + token + '@' if token else ''}github.com/{repo}.git"
    out = subprocess.run(["git", "ls-remote", "--tags", url], capture_output=True, text=True)
    if out.returncode != 0:
        print(f"  FAIL  could not list {repo}'s tags", file=sys.stderr)
        sys.exit(1)
    tags = set(re.findall(r"refs/tags/(v\d+\.\d+\.\d+)$", out.stdout, re.M))
    if not tags:
        print(f"  FAIL  {repo} has no release tags", file=sys.stderr)
        sys.exit(1)
    ref = max(tags, key=lambda t: tuple(int(x) for x in t[1:].split(".")))

lock_text = fetch(repo, ref, "addons.lock")
if lock_text is None:
    print(f"  FAIL  {repo}@{ref} has no addons.lock", file=sys.stderr)
    sys.exit(1)

lock = {}
for line in lock_text.splitlines():
    if not line.strip() or line.startswith("#"):
        continue
    parts = line.split("\t")
    if len(parts) >= 2:
        lock[parts[0]] = parts[1]


def repo_of(addon):
    return "zee-dot-weapons" if addon == "zee_weapons" else addon.replace("_", "-")


def owner_of(r):
    return os.environ["DOT_OWNER"] if r.startswith("dot-") else os.environ["GAME_OWNER"]


def const(text, name):
    m = re.search(rf"^const\s+{name}\s*(?::\s*int)?\s*:?=\s*(\d+)", text or "", re.M)
    return max(1, int(m.group(1))) if m else None


print(f"checking {len(needs)} addon requirement(s) against {repo}@{ref}")
problems = []
for addon in sorted(needs):
    need = needs[addon]
    r = repo_of(addon)
    if r not in lock:
        problems.append(f"needs {addon}, and the server at {ref} does not install it")
        continue
    api = fetch(f"{owner_of(r)}/{r}", lock[r], f"addons/{addon}/{addon}_api.gd")
    have = const(api, "LEVEL") or 1
    oldest = min(const(api, "OLDEST") or 1, have)
    if need > have:
        problems.append(f"needs {addon} API level {need}; the server at {ref} locks {r} {lock[r]}, which has level {have}")
    elif need < oldest:
        problems.append(f"was built for {addon} API level {need}; {r} {lock[r]} supports {oldest} to {have}")
    else:
        print(f"  ok    {addon} {need} (server has {have}, {r} {lock[r]})")

if problems:
    for p in problems:
        print(f"  FAIL  {p}")
    print(
        "\nNo released server can run this pack. Tag the addon it needs, bump "
        f"{repo}'s addons.lock to that tag and release it, then tag this game again."
    )
    sys.exit(1)

print(f"every requirement is met by {repo}@{ref}")
PY
