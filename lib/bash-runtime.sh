#!/usr/bin/env bash
# Canonical GNU Bash runtime selection for agent-do entry points.
#
# This file must remain compatible with macOS Bash 3.2: it is the bootstrap
# layer that either activates a supported Bash or stops before newer syntax is
# reached anywhere else in the repository.

AGENT_DO_MIN_BASH_MAJOR=4
AGENT_DO_MIN_BASH_MINOR=4

agent_do_bash_version_supported() {
    local major="${1:-0}"
    local minor="${2:-0}"

    [ "$major" -gt "$AGENT_DO_MIN_BASH_MAJOR" ] || {
        [ "$major" -eq "$AGENT_DO_MIN_BASH_MAJOR" ] &&
            [ "$minor" -ge "$AGENT_DO_MIN_BASH_MINOR" ]
    }
}

agent_do_current_bash_supported() {
    agent_do_bash_version_supported "${BASH_VERSINFO[0]:-0}" "${BASH_VERSINFO[1]:-0}"
}

agent_do_resolve_bash_candidate() {
    local candidate="${1:-}"
    local candidate_dir=""

    [ -n "$candidate" ] || return 1
    case "$candidate" in
        /*|*/*)
            candidate_dir="$(cd "$(dirname "$candidate")" 2>/dev/null && pwd)" || return 1
            printf '%s/%s\n' "$candidate_dir" "${candidate##*/}"
            ;;
        *) command -v "$candidate" 2>/dev/null ;;
    esac
}

agent_do_bash_path_supported() {
    local candidate="${1:-}"

    [ -x "$candidate" ] || return 1
    "$candidate" -c '
major=${BASH_VERSINFO[0]:-0}
minor=${BASH_VERSINFO[1]:-0}
(( major > 4 || (major == 4 && minor >= 4) ))
' >/dev/null 2>&1
}

agent_do_find_supported_bash() {
    local candidate=""
    local resolved=""

    if [ -n "${AGENT_DO_BASH:-}" ]; then
        resolved="$(agent_do_resolve_bash_candidate "$AGENT_DO_BASH" 2>/dev/null || true)"
        if agent_do_bash_path_supported "$resolved"; then
            printf '%s\n' "$resolved"
            return 0
        fi
        printf 'agent-do: AGENT_DO_BASH does not name GNU Bash %s.%s or newer: %s\n' \
            "$AGENT_DO_MIN_BASH_MAJOR" "$AGENT_DO_MIN_BASH_MINOR" "$AGENT_DO_BASH" >&2
        return 1
    fi

    for candidate in \
        "${BASH:-}" \
        "$(command -v bash 2>/dev/null || true)" \
        /opt/homebrew/bin/bash \
        /usr/local/bin/bash \
        /home/linuxbrew/.linuxbrew/bin/bash \
        /run/current-system/sw/bin/bash \
        "${HOME:-}/.local/bin/bash"
    do
        resolved="$(agent_do_resolve_bash_candidate "$candidate" 2>/dev/null || true)"
        if agent_do_bash_path_supported "$resolved"; then
            printf '%s\n' "$resolved"
            return 0
        fi
    done

    return 1
}

agent_do_prepend_bash_to_path() {
    local bash_path="$1"
    local runtime_home="${AGENT_DO_HOME:-${HOME:-}/.agent-do}"
    local shim_dir="$runtime_home/runtime/bin"
    local shim_path="$shim_dir/bash"
    local shim_target=""
    local pending_shim="$shim_path.$$.new"
    local resolved_shim_path=""

    if [ -z "$runtime_home" ] || [ "$runtime_home" = "/.agent-do" ]; then
        printf 'agent-do: cannot create the Bash runtime shim without HOME or AGENT_DO_HOME\n' >&2
        return 1
    fi
    mkdir -p "$shim_dir" || return 1
    if [ -e "$shim_path" ] && [ ! -L "$shim_path" ]; then
        printf 'agent-do: Bash runtime shim path is not a symlink: %s\n' "$shim_path" >&2
        return 1
    fi
    bash_path="$(agent_do_resolve_bash_candidate "$bash_path")" || return 1
    resolved_shim_path="$(agent_do_resolve_bash_candidate "$shim_path")" || return 1
    if [ -L "$shim_path" ]; then
        shim_target="$(readlink "$shim_path" 2>/dev/null || true)"
    fi
    if [ "$bash_path" = "$resolved_shim_path" ]; then
        [ -n "$shim_target" ] || {
            printf 'agent-do: Bash runtime shim has no target: %s\n' "$shim_path" >&2
            return 1
        }
        case "$shim_target" in
            /*) bash_path="$shim_target" ;;
            *) bash_path="$shim_dir/$shim_target" ;;
        esac
        bash_path="$(agent_do_resolve_bash_candidate "$bash_path")" || return 1
        if ! agent_do_bash_path_supported "$bash_path"; then
            printf 'agent-do: Bash runtime shim target is not supported: %s\n' "$bash_path" >&2
            return 1
        fi
    fi
    if [ "$shim_target" != "$bash_path" ]; then
        rm -f "$pending_shim"
        ln -s "$bash_path" "$pending_shim" || return 1
        if ! mv -f "$pending_shim" "$shim_path"; then
            rm -f "$pending_shim"
            return 1
        fi
    fi

    case "${PATH:-}" in
        "$shim_dir"|"$shim_dir":*) ;;
        *) PATH="$shim_dir${PATH:+:$PATH}" ;;
    esac
    export PATH
}

agent_do_ensure_supported_bash() {
    local entrypoint="$1"
    shift
    local selected=""

    if agent_do_current_bash_supported; then
        selected="$(agent_do_resolve_bash_candidate "${AGENT_DO_BASH:-${BASH:-bash}}" 2>/dev/null || true)"
        if ! agent_do_bash_path_supported "$selected"; then
            printf 'agent-do: could not resolve a supported running Bash executable: %s\n' \
                "${AGENT_DO_BASH:-${BASH:-unknown}}" >&2
            return 1
        fi
        AGENT_DO_BASH="$selected"
        export AGENT_DO_BASH
        agent_do_prepend_bash_to_path "$selected" || return 1
        return 0
    fi

    selected="$(agent_do_find_supported_bash)" || {
        printf 'agent-do requires GNU Bash %s.%s or newer; current runtime is %s.\n' \
            "$AGENT_DO_MIN_BASH_MAJOR" "$AGENT_DO_MIN_BASH_MINOR" "${BASH_VERSION:-unknown}" >&2
        printf 'Install it on macOS with: brew install bash\n' >&2
        printf 'Or set AGENT_DO_BASH to the absolute path of a supported Bash.\n' >&2
        return 1
    }

    AGENT_DO_BASH="$selected"
    export AGENT_DO_BASH
    agent_do_prepend_bash_to_path "$selected" || return 1
    exec "$selected" "$entrypoint" "$@"
}
