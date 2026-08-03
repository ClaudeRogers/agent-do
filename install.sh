#!/bin/bash
# install.sh — Idempotent installer for agent-do + Claude Code (+ optional Codex) hooks
#
# What it does:
#   1. Symlinks agent-do into ~/.local/bin (adds to PATH)
#   2. Writes breadcrumb at ~/.agent-do/install-path
#   3. Generates the installed discovery index from registry.yaml
#   4. Copies Claude Code hooks to ~/.claude/hooks/
#   5. Optional: Codex hooks to ~/.codex/hooks/ (--codex or auto-detected)
#   6. Installs Python dependencies
#   7. Optional: npm install for browse/unbrowse
#   8. Optional: cargo build for manna
#   9. Runs agent-do --health
#  10. Registers the hooks in Claude settings.json (or prints the snippet)
#  11. Prints Codex hooks.json snippet if Codex install ran
#  12. Prints CLAUDE.md snippet for projects
#
# Usage:
#   ./install.sh                  # Install (asks before touching settings.json)
#   ./install.sh --register-hooks # Install and register hooks without asking
#   ./install.sh --print-only     # Never modify settings.json; just print the snippet
#   ./install.sh --codex          # Force Codex install even without ~/.codex/
#   ./install.sh --no-codex       # Skip Codex install even when ~/.codex/ exists
#   ./install.sh --uninstall      # Remove symlink + hooks + settings.json entries

set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SYMLINK_DIR="$HOME/.local/bin"
SYMLINK_PATH="$SYMLINK_DIR/agent-do"
AGENT_DO_HOME="${AGENT_DO_HOME:-$HOME/.agent-do}"
CLAUDE_HOOKS_DIR="$HOME/.claude/hooks"
CLAUDE_SETTINGS_PATH="${CLAUDE_SETTINGS_PATH:-$HOME/.claude/settings.json}"
CODEX_HOOKS_DIR="$HOME/.codex/hooks"
FACTORY_DIR="${FACTORY_DIR:-$HOME/.factory}"
FACTORY_INDEX_PATH="$FACTORY_DIR/agent-do-index.yaml"
HOOKS_DIR="$REPO_DIR/hooks"
CODEX_HOOKS_SRC="$HOOKS_DIR/codex"

# Decide whether to install Codex hooks. Default: auto (yes if ~/.codex/ exists).
INSTALL_CODEX="auto"
# Decide whether to register hooks in settings.json. Default: ask (print-only if
# stdin is not a terminal, so piped installs never modify settings unasked).
REGISTER_HOOKS="ask"
for arg in "$@"; do
    case "$arg" in
        --codex)          INSTALL_CODEX="yes" ;;
        --no-codex)       INSTALL_CODEX="no"  ;;
        --register-hooks) REGISTER_HOOKS="yes" ;;
        --print-only)     REGISTER_HOOKS="no"  ;;
    esac
done

# Colors (skip if not a terminal)
if [ -t 1 ]; then
    GREEN='\033[0;32m'
    YELLOW='\033[1;33m'
    RED='\033[0;31m'
    BLUE='\033[0;34m'
    BOLD='\033[1m'
    NC='\033[0m'
else
    GREEN='' YELLOW='' RED='' BLUE='' BOLD='' NC=''
fi

info()  { echo -e "${GREEN}✓${NC} $*"; }
warn()  { echo -e "${YELLOW}⚠${NC} $*"; }
err()   { echo -e "${RED}✗${NC} $*"; }
step()  { echo -e "\n${BOLD}${BLUE}→${NC} ${BOLD}$*${NC}"; }

# Print a path the way a person writes it: ~/x for anything under $HOME.
display_path() { case "$1" in "$HOME"/*) echo "~${1#"$HOME"}" ;; *) echo "$1" ;; esac; }

# ─── The registered hook set ─────────────────────────────────────────────────
#
# One source of truth for what agent-do registers in Claude's settings.json.
# The merge, the printed snippet, and the uninstall sweep all read this array,
# so the three can never drift apart.
#
# Format: event | matcher | installed-hook-name | timeout-seconds
# An empty matcher means "every invocation of this event", which is how Claude
# Code's own settings.json spells it.
CLAUDE_SETTINGS_SPECS=(
    "SessionStart||agent-do-session-start.sh|10"
    "UserPromptSubmit||agent-do-prompt-router.py|5"
    "UserPromptSubmit||agent-do-correction-keys.py|5"
    "UserPromptSubmit||agent-do-now-stamp.py|5"
    "PreToolUse|Bash|agent-do-pretooluse-check.py|5"
    "SessionEnd||agent-do-coord-stop.sh|10"
    "Stop||agent-do-zpc-write-nudge.sh|5"
    "PostToolUse|ExitPlanMode|agent-do-zpc-position-nudge.sh|5"
)

# Emit the spec as event|matcher|command|timeout, with the command spelled the
# way settings.json wants it: `~/.claude/hooks/x` for a stock install, an
# absolute path when the hooks directory has been relocated.
claude_settings_stream() {
    local spec event matcher name timeout command
    for spec in "${CLAUDE_SETTINGS_SPECS[@]}"; do
        IFS='|' read -r event matcher name timeout <<< "$spec"
        if [ "$CLAUDE_HOOKS_DIR" = "$HOME/.claude/hooks" ]; then
            command="~/.claude/hooks/$name"
        else
            command="$CLAUDE_HOOKS_DIR/$name"
        fi
        printf '%s|%s|%s|%s\n' "$event" "$matcher" "$command" "$timeout"
    done
}

# Merge modes:
#   print  — write the settings.json snippet to stdout, touch nothing
#   apply  — add any missing registration to $CLAUDE_SETTINGS_PATH
#   remove — strip exactly the registrations this installer owns
#
# apply and remove are idempotent by construction: they compute the additions
# or removals first and return without writing when the set is empty, so a
# second run leaves the file byte-identical. Every write is preceded by a
# timestamped backup, and unrelated hooks and settings keys are never touched.
claude_settings_merge() {
    local mode="$1"
    # The spec travels by environment, not by pipe: `python3 -` reads its own
    # program from stdin, which would swallow anything piped in.
    AGENT_DO_MERGE_MODE="$mode" \
    AGENT_DO_SETTINGS_PATH="$CLAUDE_SETTINGS_PATH" \
    AGENT_DO_MERGE_SPECS="$(claude_settings_stream)" \
    python3 - <<'PYMERGE'
import json
import os
import shutil
import sys
import time
from pathlib import Path

mode = os.environ.get("AGENT_DO_MERGE_MODE", "print")
target = Path(os.environ.get("AGENT_DO_SETTINGS_PATH", "")).expanduser()

specs = []
for line in os.environ.get("AGENT_DO_MERGE_SPECS", "").splitlines():
    if not line.strip():
        continue
    event, matcher, command, timeout = line.split("|", 3)
    specs.append((event, matcher, command, int(timeout)))

if not specs:
    sys.stderr.write("no hook specs supplied; refusing to touch settings\n")
    raise SystemExit(3)


def hook_entry(command, timeout):
    return {"type": "command", "command": command, "timeout": timeout}


def fail(message):
    sys.stderr.write(message + "\n")
    raise SystemExit(3)


if mode == "print":
    hooks = {}
    for event, matcher, command, timeout in specs:
        groups = hooks.setdefault(event, [])
        for group in groups:
            if group["matcher"] == matcher:
                group["hooks"].append(hook_entry(command, timeout))
                break
        else:
            groups.append({"matcher": matcher, "hooks": [hook_entry(command, timeout)]})
    print(json.dumps({"hooks": hooks}, indent=2))
    raise SystemExit(0)

if target.is_file():
    raw = target.read_text()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        fail(f"{target} is not valid JSON ({exc}); refusing to write")
    if not isinstance(data, dict):
        fail(f"{target} is not a JSON object; refusing to write")
elif mode == "remove":
    print("NOCHANGE|nothing to remove")
    raise SystemExit(0)
else:
    data = {}

hooks = data.get("hooks", {})
if not isinstance(hooks, dict):
    fail(f"{target} has a 'hooks' key that is not an object; refusing to write")

changed = []

if mode == "apply":
    for event, matcher, command, timeout in specs:
        groups = hooks.get(event, [])
        if not isinstance(groups, list):
            fail(f"{target}: hooks.{event} is not a list; refusing to write")
        # Dedupe on the command across every group of the event, not just the
        # group we would write into. A command registered under some other
        # matcher is still registered; adding ours would double-fire it.
        already = any(
            isinstance(entry, dict) and entry.get("command") == command
            for group in groups if isinstance(group, dict)
            for entry in (group.get("hooks") or [])
        )
        if already:
            print(f"PRESENT|{event}|{command}")
            continue
        for group in groups:
            if isinstance(group, dict) and group.get("matcher", "") == matcher:
                group.setdefault("hooks", []).append(hook_entry(command, timeout))
                break
        else:
            groups.append({"matcher": matcher, "hooks": [hook_entry(command, timeout)]})
        hooks[event] = groups
        data["hooks"] = hooks
        changed.append(command)
        print(f"ADDED|{event}|{command}")

elif mode == "remove":
    owned = {(event, command) for event, _matcher, command, _timeout in specs}
    for event, groups in list(hooks.items()):
        if not isinstance(groups, list):
            continue
        surviving_groups = []
        touched_event = False
        for group in groups:
            if not isinstance(group, dict) or not isinstance(group.get("hooks"), list):
                surviving_groups.append(group)
                continue
            entries = group["hooks"]
            ours = [
                entry for entry in entries
                if isinstance(entry, dict) and (event, entry.get("command")) in owned
            ]
            if not ours:
                surviving_groups.append(group)
                continue
            touched_event = True
            for entry in ours:
                changed.append(entry["command"])
                print(f"REMOVED|{event}|{entry['command']}")
            group["hooks"] = [entry for entry in entries if entry not in ours]
            # A group we emptied is ours to drop; a group that was already
            # empty belongs to the user and stays.
            if group["hooks"]:
                surviving_groups.append(group)
        if touched_event:
            if surviving_groups:
                hooks[event] = surviving_groups
            else:
                del hooks[event]
else:
    fail(f"unknown merge mode: {mode}")

if not changed:
    print("NOCHANGE|already in the desired state")
    raise SystemExit(0)

if target.is_file():
    stamp = int(time.time())
    backup = target.with_name(f"{target.name}.bak.{stamp}")
    collision = 1
    while backup.exists():
        backup = target.with_name(f"{target.name}.bak.{stamp}-{collision}")
        collision += 1
    shutil.copy2(str(target), str(backup))
    print(f"BACKUP|{backup}")

target.parent.mkdir(parents=True, exist_ok=True)
tmp = target.with_name(f"{target.name}.tmp.{os.getpid()}")
tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
os.replace(str(tmp), str(target))
print(f"WROTE|{target}")
PYMERGE
}

# Turn the merge script's machine-readable lines into installer output.
report_settings_merge() {
    local kind field_a field_b
    while IFS='|' read -r kind field_a field_b; do
        case "$kind" in
            ADDED)    info "Registered ${field_a}: ${field_b}" ;;
            REMOVED)  info "Unregistered ${field_a}: ${field_b}" ;;
            PRESENT)  info "Already registered ${field_a}: ${field_b}" ;;
            BACKUP)   info "Backed up settings to ${field_a}" ;;
            WROTE)    info "Updated ${field_a}" ;;
            NOCHANGE) info "No settings.json change needed (${field_a})" ;;
        esac
    done
}

# ─── Uninstall ───────────────────────────────────────────────────────────────

uninstall() {
    step "Uninstalling agent-do"

    # Remove symlink
    if [ -L "$SYMLINK_PATH" ]; then
        rm "$SYMLINK_PATH"
        info "Removed symlink $SYMLINK_PATH"
    else
        warn "No symlink at $SYMLINK_PATH"
    fi

    # Remove breadcrumb
    if [ -f "$AGENT_DO_HOME/install-path" ]; then
        rm "$AGENT_DO_HOME/install-path"
        info "Removed breadcrumb $AGENT_DO_HOME/install-path"
    fi

    # Remove only an index carrying this repository's generated marker.
    if [ -f "$FACTORY_INDEX_PATH" ] && grep -q '^# Generated by agent-do/bin/gen-index\.' "$FACTORY_INDEX_PATH"; then
        rm "$FACTORY_INDEX_PATH"
        info "Removed generated index $FACTORY_INDEX_PATH"
    fi

    # Remove Claude hooks that agent-do installs (only those, not personal hooks)
    local hooks=(
        "agent-do-session-start.sh"
        "agent-do-prompt-router.py"
        "agent-do-correction-keys.py"
        "agent-do-now-stamp.py"
        "agent-do-pretooluse-check.py"
        "agent-do-coord-stop.sh"
        "agent-do-zpc-write-nudge.sh"
        "agent-do-zpc-position-nudge.sh"
    )
    for hook in "${hooks[@]}"; do
        if [ -f "$CLAUDE_HOOKS_DIR/$hook" ]; then
            rm "$CLAUDE_HOOKS_DIR/$hook"
            info "Removed hook $CLAUDE_HOOKS_DIR/$hook"
        fi
    done

    # Remove Codex hooks that agent-do installs (only those, not personal hooks)
    local codex_hooks=(
        "agent-do-session-start.py"
        "agent-do-prompt-router.py"
        "agent-do-now-stamp.py"
        "agent-do-pretooluse-check.py"
        "stop-quality-gate.sh"
        "stop-quality-gate.py"
    )
    for hook in "${codex_hooks[@]}"; do
        if [ -f "$CODEX_HOOKS_DIR/$hook" ]; then
            rm "$CODEX_HOOKS_DIR/$hook"
            info "Removed Codex hook $CODEX_HOOKS_DIR/$hook"
        fi
    done

    # Unregister from settings.json. Removing the wrappers without removing the
    # entries would leave Claude Code invoking commands that no longer exist,
    # so the sweep is part of uninstalling, not a reminder to the user. Only
    # the exact command strings this installer writes are removed.
    step "Unregistering hooks from Claude settings.json"
    local merge_output
    if merge_output=$(claude_settings_merge remove); then
        printf '%s\n' "$merge_output" | report_settings_merge
    else
        warn "Could not edit $CLAUDE_SETTINGS_PATH — remove the agent-do hook"
        warn "entries by hand. Search for 'agent-do' in the hooks sections."
    fi

    echo ""
    warn "Codex is not swept automatically: remove the agent-do hooks from"
    warn "~/.codex/hooks.json by hand. Search for 'agent-do' in the hooks sections."
    echo ""
    info "Uninstall complete. Repo at $REPO_DIR is untouched."
    exit 0
}

if [ "${1:-}" = "--uninstall" ]; then
    uninstall
fi

# ─── Install ─────────────────────────────────────────────────────────────────

echo -e "${BOLD}agent-do installer${NC}"
echo "Repo: $REPO_DIR"
echo ""

# 1. Symlink into ~/.local/bin
step "Symlinking agent-do into PATH"
mkdir -p "$SYMLINK_DIR"
if [ -L "$SYMLINK_PATH" ]; then
    EXISTING=$(readlink "$SYMLINK_PATH" 2>/dev/null || true)
    if [ "$EXISTING" = "$REPO_DIR/agent-do" ]; then
        info "Symlink already correct: $SYMLINK_PATH → $REPO_DIR/agent-do"
    else
        ln -sf "$REPO_DIR/agent-do" "$SYMLINK_PATH"
        info "Updated symlink: $SYMLINK_PATH → $REPO_DIR/agent-do (was: $EXISTING)"
    fi
elif [ -e "$SYMLINK_PATH" ]; then
    err "$SYMLINK_PATH exists but is not a symlink — skipping (remove it manually)"
else
    ln -s "$REPO_DIR/agent-do" "$SYMLINK_PATH"
    info "Created symlink: $SYMLINK_PATH → $REPO_DIR/agent-do"
fi

# Check if ~/.local/bin is in PATH
if ! echo "$PATH" | tr ':' '\n' | grep -qx "$SYMLINK_DIR"; then
    warn "$SYMLINK_DIR is not in your PATH"
    warn "Add to your shell profile: export PATH=\"\$HOME/.local/bin:\$PATH\""
fi

# 2. Write breadcrumb
step "Writing install-path breadcrumb"
mkdir -p "$AGENT_DO_HOME"
echo "$REPO_DIR" > "$AGENT_DO_HOME/install-path"
info "Wrote $AGENT_DO_HOME/install-path"

# 3. Install the generated discovery cache
step "Installing generated tool index"
mkdir -p "$FACTORY_DIR"
"$REPO_DIR/bin/gen-index" --output "$FACTORY_INDEX_PATH"
info "Generated $FACTORY_INDEX_PATH from registry.yaml"

# 4. Install hooks (wrapper-based, so `git pull` updates flow through)
#
# Installed hooks are thin wrappers that delegate to the canonical files
# under `<repo>/hooks/`. This means:
#   - `git pull` on the repo immediately changes hook behavior on the next
#     event. No re-install needed unless the wrapper itself changes (rare).
#   - Hooks that import from `<repo>/lib/` work correctly because the wrapper
#     resolves the repo root and sets sys.path before delegating.
#   - The wrappers themselves are version-tagged so re-running install.sh
#     refreshes them when the wrapper format changes.
#
# The canonical hook files stay in `hooks/` (Claude defaults) and
# `hooks/codex/` (Codex-specific variants). install.sh writes the
# corresponding wrapper at the installed path.

WRAPPER_VERSION="2"
# v2: hooks restructured into hooks/claude/ + hooks/codex/ symmetric dirs.
#     Auto-commit removed from the bundle (it's git automation, not agent-do).

install_py_wrapper() {
    local repo_hook_rel="$1"  # e.g. "hooks/agent-do-prompt-router.py"
    local installed="$2"      # e.g. "$CLAUDE_HOOKS_DIR/agent-do-prompt-router.py"
    local hook_name
    hook_name=$(basename "$installed")
    cat > "$installed" <<WRAPPER
#!/usr/bin/env python3
# agent-do hook wrapper v$WRAPPER_VERSION (managed by install.sh; do not edit).
# Delegates to the canonical hook under the agent-do repo so that future
# \`git pull\` updates flow through without re-running install.sh.
import os
import runpy
import sys
from pathlib import Path


def _resolve_repo():
    env_root = os.environ.get("AGENT_DO_REPO")
    if env_root:
        candidate = Path(env_root).expanduser()
        if candidate.is_dir():
            return candidate
    breadcrumb = Path.home() / ".agent-do" / "install-path"
    if breadcrumb.is_file():
        try:
            candidate = Path(breadcrumb.read_text().strip()).expanduser()
            if candidate.is_dir():
                return candidate
        except OSError:
            pass
    return None


def main():
    repo = _resolve_repo()
    if repo is None:
        sys.stderr.write(
            "[$hook_name wrapper] could not resolve agent-do repo; "
            "set AGENT_DO_REPO or run install.sh\\n"
        )
        return
    hook = repo / "$repo_hook_rel"
    if not hook.is_file():
        sys.stderr.write(f"[$hook_name wrapper] canonical hook missing: {hook}\\n")
        return
    sys.path.insert(0, str(repo / "lib"))
    runpy.run_path(str(hook), run_name="__main__")


if __name__ == "__main__":
    main()
WRAPPER
    chmod +x "$installed"
}

install_sh_wrapper() {
    local repo_hook_rel="$1"
    local installed="$2"
    local hook_name
    hook_name=$(basename "$installed")
    cat > "$installed" <<WRAPPER
#!/usr/bin/env bash
# agent-do hook wrapper v$WRAPPER_VERSION (managed by install.sh; do not edit).
# Delegates to the canonical hook under the agent-do repo so that future
# \`git pull\` updates flow through without re-running install.sh.
set -uo pipefail
repo="\${AGENT_DO_REPO:-\$(cat "\$HOME/.agent-do/install-path" 2>/dev/null)}"
if [ -z "\$repo" ] || [ ! -d "\$repo" ]; then
    echo "[$hook_name wrapper] could not resolve agent-do repo; set AGENT_DO_REPO or run install.sh" >&2
    exit 0
fi
canonical="\$repo/$repo_hook_rel"
if [ ! -x "\$canonical" ]; then
    echo "[$hook_name wrapper] canonical hook missing or not executable: \$canonical" >&2
    exit 0
fi
exec "\$canonical" "\$@"
WRAPPER
    chmod +x "$installed"
}

step "Installing Claude Code hooks (wrapper-based)"
mkdir -p "$CLAUDE_HOOKS_DIR"

# Map: installed-name | source-relative-to-repo | wrapper-kind | requirement
#
# Scope: only hooks that nudge agents toward agent-do tools, manage agent-do
# state, or implement agent-do conventions ship here. Personal productivity
# hooks (screenshot shorthand, prompt annotation, git auto-commit, generic
# OS notifications) belong in your dotfiles, not in the agent-do repo.
#
# `optional` means the canonical hook may legitimately be absent (a checkout
# predating it, a lane still landing it). The wrapper installs anyway: it
# resolves the canonical file at event time and exits 0 when it is missing, so
# an installed-but-unbacked wrapper is inert rather than broken.
CLAUDE_HOOK_SPECS=(
    "agent-do-session-start.sh|hooks/claude/agent-do-session-start.sh|sh|required"
    "agent-do-prompt-router.py|hooks/claude/agent-do-prompt-router.py|py|required"
    "agent-do-correction-keys.py|hooks/claude/agent-do-correction-keys.py|py|required"
    "agent-do-now-stamp.py|hooks/claude/agent-do-now-stamp.py|py|required"
    "agent-do-pretooluse-check.py|hooks/claude/agent-do-pretooluse-check.py|py|required"
    "agent-do-coord-stop.sh|hooks/claude/agent-do-coord-stop.sh|sh|required"
    "agent-do-zpc-write-nudge.sh|hooks/claude/agent-do-zpc-write-nudge.sh|sh|optional"
    "agent-do-zpc-position-nudge.sh|hooks/claude/agent-do-zpc-position-nudge.sh|sh|optional"
)
for spec in "${CLAUDE_HOOK_SPECS[@]}"; do
    IFS='|' read -r name rel kind requirement <<< "$spec"
    src="$REPO_DIR/$rel"
    dst="$CLAUDE_HOOKS_DIR/$name"
    if [ ! -f "$src" ]; then
        if [ "$requirement" = "optional" ]; then
            warn "Hook source not present yet: $rel (installing inert wrapper)"
        else
            err "Hook source not found: $src"
            continue
        fi
    fi
    case "$kind" in
        py) install_py_wrapper "$rel" "$dst" ;;
        sh) install_sh_wrapper "$rel" "$dst" ;;
    esac
    info "Installed Claude wrapper: $name → $rel"
done

# 3b. Optional: Codex hooks (also wrapper-based, same upgrade model)
should_install_codex="no"
case "$INSTALL_CODEX" in
    yes)  should_install_codex="yes" ;;
    auto) [ -d "$HOME/.codex" ] && should_install_codex="yes" ;;
esac

if [ "$should_install_codex" = "yes" ]; then
    step "Installing Codex hooks (wrapper-based)"
    mkdir -p "$CODEX_HOOKS_DIR"

    # The now stamp needs no Codex-side shim: it reads stdin, writes under
    # AGENT_DO_HOME, and imports nothing from the repo, so the canonical Claude
    # hook is already the whole implementation on both runtimes.
    CODEX_HOOK_SPECS=(
        "agent-do-session-start.py|hooks/codex/agent-do-session-start.py|py"
        "agent-do-prompt-router.py|hooks/codex/agent-do-prompt-router.py|py"
        "agent-do-now-stamp.py|hooks/claude/agent-do-now-stamp.py|py"
        "agent-do-pretooluse-check.py|hooks/codex/agent-do-pretooluse-check.py|py"
        "stop-quality-gate.sh|hooks/codex/stop-quality-gate.sh|sh"
        "stop-quality-gate.py|hooks/codex/stop-quality-gate.py|py"
    )
    for spec in "${CODEX_HOOK_SPECS[@]}"; do
        IFS='|' read -r name rel kind <<< "$spec"
        src="$REPO_DIR/$rel"
        dst="$CODEX_HOOKS_DIR/$name"
        if [ ! -f "$src" ]; then
            err "Codex hook source not found: $src"
            continue
        fi
        case "$kind" in
            py) install_py_wrapper "$rel" "$dst" ;;
            sh) install_sh_wrapper "$rel" "$dst" ;;
        esac
        info "Installed Codex wrapper: $name → $rel"
    done

    info "Codex registration template: $CODEX_HOOKS_SRC/hooks.json.example"
    info "Merge into ~/.codex/hooks.json (see snippet at the end of this run)"
else
    info "Skipped Codex install (use --codex to force, or install ~/.codex/ first)"
fi

# 5. Python dependencies
step "Installing Python dependencies"
if command -v pip3 &>/dev/null; then
    pip3 install -r "$REPO_DIR/requirements.txt" --quiet 2>/dev/null && \
        info "Python dependencies installed" || \
        warn "pip install failed — try: pip3 install -r requirements.txt"
elif command -v pip &>/dev/null; then
    pip install -r "$REPO_DIR/requirements.txt" --quiet 2>/dev/null && \
        info "Python dependencies installed" || \
        warn "pip install failed — try: pip install -r requirements.txt"
else
    warn "pip not found — install Python deps manually: pip install -r requirements.txt"
fi

# 6. Optional: Node.js tools
step "Optional: Browser tools (agent-browse, agent-unbrowse)"
if command -v npm &>/dev/null; then
    # `|| answer=""` keeps an unattended run (stdin at /dev/null, CI) from
    # dying on EOF under `set -e`; an unanswered prompt means "no".
    read -rp "Install Node.js deps for browse/unbrowse? [y/N] " answer || answer=""
    if [[ "$answer" =~ ^[Yy] ]]; then
        (cd "$REPO_DIR/tools/agent-browse" && npm install --quiet 2>/dev/null) && \
            info "agent-browse deps installed" || warn "agent-browse npm install failed"
        (cd "$REPO_DIR/tools/agent-unbrowse" && npm install --quiet 2>/dev/null) && \
            info "agent-unbrowse deps installed" || warn "agent-unbrowse npm install failed"
    else
        info "Skipped (run later: cd tools/agent-browse && npm install)"
    fi
else
    warn "npm not found — browser tools require Node.js 18+"
fi

# 7. Optional: Rust tool
step "Optional: Issue tracker (agent-manna)"
if command -v cargo &>/dev/null; then
    read -rp "Build agent-manna (Rust)? [y/N] " answer || answer=""
    if [[ "$answer" =~ ^[Yy] ]]; then
        (cd "$REPO_DIR/tools/agent-manna" && cargo build --release --quiet 2>/dev/null) && \
            info "agent-manna built" || warn "cargo build failed"
    else
        info "Skipped (run later: cd tools/agent-manna && cargo build --release)"
    fi
else
    warn "cargo not found — agent-manna requires Rust"
fi

# 8. Health check
step "Running health check"
"$REPO_DIR/agent-do" --health 2>/dev/null || warn "Health check had issues (non-fatal)"

# 9. Register the hooks in settings.json (or print the snippet)
step "Claude Code settings.json configuration"

SETTINGS_DISPLAY="$(display_path "$CLAUDE_SETTINGS_PATH")"

print_settings_snippet() {
    echo ""
    echo "Add the following to $SETTINGS_DISPLAY under the \"hooks\" key:"
    echo "(If you already have hooks entries, merge these into the existing arrays)"
    echo ""
    claude_settings_merge print
    echo ""
    echo "Note: agent-do's Stop entry is the zpc write nudge, and nothing else."
    echo "Auto-commit, DPT scoring, and other turn-end behavior stay yours to"
    echo "register: add your own scripts alongside it under Stop."
    echo ""
}

do_register="$REGISTER_HOOKS"
if [ "$do_register" = "ask" ]; then
    if [ -t 0 ]; then
        read -rp "Register agent-do hooks in $SETTINGS_DISPLAY? [y/N] " answer || answer=""
        if [[ "$answer" =~ ^[Yy] ]]; then do_register="yes"; else do_register="no"; fi
    else
        do_register="no"
        info "Non-interactive shell — not touching settings.json (use --register-hooks)"
    fi
fi

if [ "$do_register" = "yes" ]; then
    if merge_output=$(claude_settings_merge apply); then
        printf '%s\n' "$merge_output" | report_settings_merge
        info "Hooks registered. Restart Claude Code to pick them up."
    else
        err "Could not register hooks automatically — falling back to the snippet"
        print_settings_snippet
    fi
else
    print_settings_snippet
fi

# 9b. Print Codex hooks.json snippet if Codex install ran
if [ "$should_install_codex" = "yes" ]; then
    step "Codex hooks.json configuration"
    echo ""
    echo "Codex now supports hookSpecificOutput.additionalContext on PreToolUse"
    echo "(May 2026 release). The wrappers in ~/.codex/hooks/ runpy-pass-through to"
    echo "this repo's hooks, so updates flow through automatically."
    echo ""
    echo "Merge the following into ~/.codex/hooks.json (full template is at"
    echo "$CODEX_HOOKS_SRC/hooks.json.example):"
    echo ""
    cat "$CODEX_HOOKS_SRC/hooks.json.example"
    echo ""
fi

# 10. Print CLAUDE.md snippet
step "Project CLAUDE.md snippet"
echo ""
echo "Add the following to your project's CLAUDE.md to teach Claude about agent-do:"
echo ""
cat << 'CLAUDE_SNIPPET'
## agent-do (Universal Automation CLI)

BEFORE using raw commands (xcrun, adb, osascript, curl for APIs, etc.),
CHECK if agent-do has a tool:

```bash
agent-do <tool> <command> [args...]   # Structured API (AI/scripts)
agent-do -n "what you want"           # Natural language (humans)
agent-do --list                       # List all registered tools
agent-do <tool> --help                # Per-tool help
```

Key tools: vercel, render, supabase, gcp, browse, ios, android, macos, tui, db,
docker, k8s, cloud, ssh, excel, slack, image, video, audio, zpc
CLAUDE_SNIPPET
echo ""

# Done
echo -e "\n${BOLD}${GREEN}Installation complete!${NC}"
echo ""
echo "Next steps:"
if [ "$do_register" = "yes" ]; then
    echo "  1. Hooks are registered in $SETTINGS_DISPLAY (nothing to merge by hand)"
else
    echo "  1. Merge the settings.json snippet above into $SETTINGS_DISPLAY"
    echo "     (or re-run: ./install.sh --register-hooks)"
fi
echo "  2. Optionally add the CLAUDE.md snippet to your project"
echo "  3. Restart Claude Code to pick up the new hooks"
echo ""
echo "Verify: agent-do --list"
