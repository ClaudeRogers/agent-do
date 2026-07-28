#!/usr/bin/env bash
# lib/common.sh — Shared ZPC utilities
# Sourced by agent-zpc main entry. Do not run directly.

ZPC_GLOBAL_DIR="${AGENT_DO_HOME:-$HOME/.agent-do}/zpc"

# The uid owning a path, or nothing if it cannot be read. BSD form first since
# darwin is the primary target; GNU `stat -f` means --file-system and answers
# with something that is not a uid, which is why the digits check decides.
_zpc_owner_uid() {
    local uid
    uid="$(stat -f %u "$1" 2>/dev/null)"
    [[ "$uid" =~ ^[0-9]+$ ]] || uid="$(stat -c %u "$1" 2>/dev/null)"
    [[ "$uid" =~ ^[0-9]+$ ]] || return 1
    printf '%s' "$uid"
}

# Only a store this user owns is a store. Reading memory is also writing it —
# every zpc command appends, and inject pastes what it finds into an agent's
# context — so a store planted by somebody else is not memory to be trusted,
# it is instruction from a stranger.
_zpc_store_is_ours() {
    local owner
    owner="$(_zpc_owner_uid "$1")" || return 1
    [[ "$owner" == "${EUID:-$(id -u)}" ]]
}

# Walk up from cwd to find .zpc/, bounded three ways.
#
# Unbounded, this walk answers "whose memory is this?" with whatever it meets
# first on the way to /. A cwd in a scratch directory would adopt a planted
# /tmp/.zpc, or another account's store, and from then on every zpc command
# reads and writes memory somebody else controls. The bounds, in the order they
# bind: a git worktree ends at its toplevel, because a repository's memory is
# the repository's; $HOME is the floor and the last rung, because above it the
# directories stop being this user's; and outside $HOME with no worktree in
# sight only cwd is probed, because there is no project to speak of. Ownership
# is checked at every rung, which is the bound that holds when the other three
# do not.
resolve_zpc_dir() {
    local dir="${1:-$PWD}"
    local home="${HOME:-}"
    local under_home=false toplevel="" ceiling="" probe

    home="${home%/}"
    dir="${dir%/}"
    [[ -n "$dir" ]] || dir="/"

    if [[ -n "$home" && ( "$dir" == "$home" || "$dir" == "$home"/* ) ]]; then
        under_home=true
    fi

    # The toplevel is the nearest ancestor holding .git — a file in a submodule
    # or a linked worktree, a directory otherwise. Found by walking rather than
    # by asking git: this runs ahead of every zpc command, and a subprocess per
    # command to learn what a few stat calls already know is a tax on all of it.
    probe="$dir"
    while :; do
        if [[ -e "$probe/.git" ]]; then
            toplevel="$probe"
            break
        fi
        [[ "$probe" == "/" ]] && break
        probe="${probe%/*}"
        [[ -n "$probe" ]] || probe="/"
    done

    if [[ -n "$toplevel" ]]; then
        ceiling="$toplevel"
        # A repository that contains $HOME (someone ran git init in / or in
        # /Users) must not raise the floor: the floor is the reason one user's
        # cwd cannot reach another user's store.
        if [[ "$under_home" == true && ${#toplevel} -lt ${#home} ]]; then
            ceiling="$home"
        fi
    elif [[ "$under_home" == true ]]; then
        ceiling="$home"
    else
        ceiling="$dir"
    fi

    # The ceiling is probed, never skipped: $HOME is the last rung, not a rung
    # we stop short of. A store that fails the ownership check is passed over
    # rather than fatal — anything found above it faces the same test.
    probe="$dir"
    while :; do
        if [[ -d "$probe/.zpc" ]] && _zpc_store_is_ours "$probe/.zpc"; then
            printf '%s\n' "$probe/.zpc"
            return 0
        fi
        [[ "$probe" == "$ceiling" || "$probe" == "/" ]] && break
        probe="${probe%/*}"
        [[ -n "$probe" ]] || probe="/"
    done

    return 1
}

# Directory variables — set by init_zpc_dirs
ZPC_DIR=""
ZPC_MEMORY_DIR=""
ZPC_STATE_DIR=""
ZPC_TEAM_DIR=""

init_zpc_dirs() {
    ZPC_DIR="$(resolve_zpc_dir)" || return 1
    ZPC_MEMORY_DIR="$ZPC_DIR/memory"
    ZPC_STATE_DIR="$ZPC_DIR/.state"
    ZPC_TEAM_DIR="$ZPC_DIR/team"
}

ensure_zpc() {
    init_zpc_dirs || {
        if [[ "${OUTPUT_FORMAT:-text}" == "json" ]]; then
            json_error "No .zpc/ directory found. Run 'agent-do zpc init' first." 1
        else
            echo "Error: No .zpc/ directory found. Run 'agent-do zpc init' first." >&2
        fi
        exit 1
    }
}

ensure_global() {
    mkdir -p "$ZPC_GLOBAL_DIR"
}

today() { date +%Y-%m-%d; }

count_lines() {
    local file="$1"
    [[ -f "$file" && -s "$file" ]] && wc -l < "$file" | tr -d ' ' || echo "0"
}

validate_json() {
    echo "$1" | python3 -c "import sys,json; json.load(sys.stdin)" 2>/dev/null
}

append_jsonl() {
    local file="$1" line="$2"
    validate_json "$line" || {
        if [[ "${OUTPUT_FORMAT:-text}" == "json" ]]; then
            json_error "Invalid JSON: $line" 1
        else
            echo "Error: Invalid JSON" >&2
        fi
        return 1
    }
    echo "$line" >> "$file"
}

read_jsonl() {
    local file="$1" count="${2:-20}"
    [[ -f "$file" && -s "$file" ]] && tail -n "$count" "$file" || true
}

_json_escape() {
    local s="$1"
    s="${s//\\/\\\\}"
    s="${s//\"/\\\"}"
    printf '%s' "$s"
}

# Leave a receipt for a read command in .zpc/.state/access-log.jsonl.
# Append-only and silent: a log that cannot be written is never a reason for
# the command it describes to fail.
log_access() {
    local cmd="$1"
    [[ -n "${ZPC_DIR:-}" && -n "${ZPC_STATE_DIR:-}" ]] || return 0

    local ts source project line
    ts="$(date -u +%Y-%m-%dT%H:%M:%SZ 2>/dev/null)" || return 0
    source="${AGENT_DO_ZPC_SOURCE:-cli}"
    project="$(dirname "$ZPC_DIR")"

    printf -v line '{"ts":"%s","cmd":"%s","source":"%s","project":"%s"}' \
        "$(_json_escape "$ts")" \
        "$(_json_escape "$cmd")" \
        "$(_json_escape "$source")" \
        "$(_json_escape "$project")"

    {
        mkdir -p "$ZPC_STATE_DIR" &&
        printf '%s\n' "$line" >> "$ZPC_STATE_DIR/access-log.jsonl"
    } 2>/dev/null || true

    return 0
}

die() {
    local msg="$1"
    if [[ "${OUTPUT_FORMAT:-text}" == "json" ]]; then
        json_error "$msg" 1
    else
        echo "Error: $msg" >&2
    fi
    exit 1
}
