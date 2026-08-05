#!/usr/bin/env bash
# lib/common.sh — Shared ZPC utilities
# Sourced by agent-zpc main entry. Do not run directly.

ZPC_GLOBAL_DIR="${AGENT_DO_HOME:-$HOME/.agent-do}/zpc"

# Where memory bindings live: outside every repository, in this user's own
# config. See _zpc_binding_for for the format and why the location is the
# security property.
ZPC_BINDINGS_FILE="$ZPC_GLOBAL_DIR/worktree-bindings.tsv"

# agent-do's own lib/, where the quantity authority lives. Delivery bounds are
# read from it at call time rather than copied into this tool, so there is one
# resolver for every published number and nothing here to go stale. Empty when
# zpc is running detached from its repo — which means no ceiling is available,
# and lib/delivery.py applies none rather than inventing one.
ZPC_AUTHORITY_LIB="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../lib" 2>/dev/null && pwd)" || ZPC_AUTHORITY_LIB=""

# The uid owning a path, or nothing if it cannot be read. Mode `link` reads the
# path itself, `target` (the default) reads what it resolves to. BSD form first
# since darwin is the primary target; GNU `stat -f` means --file-system and
# answers with something that is not a uid, which is why the digits check
# decides.
_zpc_owner_uid() {
    local uid
    if [[ "${2:-target}" == "link" ]]; then
        uid="$(stat -f %u "$1" 2>/dev/null)"
        [[ "$uid" =~ ^[0-9]+$ ]] || uid="$(stat -c %u "$1" 2>/dev/null)"
    else
        uid="$(stat -L -f %u "$1" 2>/dev/null)"
        [[ "$uid" =~ ^[0-9]+$ ]] || uid="$(stat -L -c %u "$1" 2>/dev/null)"
    fi
    [[ "$uid" =~ ^[0-9]+$ ]] || return 1
    printf '%s' "$uid"
}

# Only a store this user owns is a store. Reading memory is also writing it —
# every zpc command appends, and inject pastes what it finds into an agent's
# context — so a store planted by somebody else is not memory to be trusted,
# it is instruction from a stranger.
#
# The name and what it resolves to are both checked, because either one alone
# can be a stranger's: a link owned by somebody else can be re-aimed whenever
# they like, and a link we own can still land in a directory we do not. The
# session-start hooks apply the identical pair (mn-68d471).
_zpc_store_is_ours() {
    local me="${EUID:-$(id -u)}" owner
    owner="$(_zpc_owner_uid "$1" link)" || return 1
    [[ "$owner" == "$me" ]] || return 1
    owner="$(_zpc_owner_uid "$1" target)" || return 1
    [[ "$owner" == "$me" ]]
}

# The store a directory is bound to, or nothing.
#
# A linked worktree has no memory of its own: .zpc/ is gitignored, so it starts
# blank, and every lesson written inside it would die with `worktree remove`.
# `agent-git worktree add` binds it to the checkout that outlives it.
#
# The binding lives in this user's config, never in the repository, and that
# location IS the security property. A pointer file inside the tree would make
# repository content the authority over where memory is read and written: a
# repo can track such a file (nothing stops `git add -f`, and a repo that does
# not ignore .zpc/ needs no force at all), and cloning it would silently
# redirect a session's memory into another project's store — injected as this
# project's recorded truth on the way in, and written to on the way out. A
# clone cannot write $AGENT_DO_HOME, so a clone cannot bind anything.
#
# Format: one binding per line, <absolute worktree>TAB<absolute .zpc>, `#`
# comments and blanks skipped. Paths containing a tab or newline are refused at
# write time rather than escaped, which keeps every reader a plain line split.
#
# Trusted only when all of it holds: the bindings file is this user's by both
# name and target, the value is an absolute path to a `.zpc` directory, and
# this user owns that too. One hop only — the target's own binding, if it
# somehow has one, is not followed.
_zpc_binding_for() {
    local key="${1%/}" line worktree store
    [[ -n "$key" ]] || return 1
    [[ -f "$ZPC_BINDINGS_FILE" ]] || return 1
    _zpc_store_is_ours "$ZPC_BINDINGS_FILE" || return 1

    while IFS=$'\t' read -r worktree store || [[ -n "$worktree" ]]; do
        [[ -n "$worktree" && "$worktree" != \#* ]] || continue
        [[ "${worktree%/}" == "$key" ]] || continue
        store="${store%$'\r'}"
        store="${store%/}"
        [[ -n "$store" && "$store" == /* && "$store" == */.zpc ]] || return 1
        [[ -d "$store" ]] || return 1
        _zpc_store_is_ours "$store" || return 1
        printf '%s' "$store"
        return 0
    done < "$ZPC_BINDINGS_FILE"

    return 1
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
    local under_home=false toplevel="" ceiling="" probe target

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
    #
    # A real store at a rung answers before that rung's binding does. Memory
    # sitting in front of you outranks a note about memory elsewhere, and the
    # order costs nothing in practice: this repo's own tools never leave both
    # (init deletes the binding when it creates a local store).
    probe="$dir"
    while :; do
        if [[ -d "$probe/.zpc" ]] && _zpc_store_is_ours "$probe/.zpc"; then
            printf '%s\n' "$probe/.zpc"
            return 0
        fi
        if target="$(_zpc_binding_for "$probe")"; then
            printf '%s\n' "$target"
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
