#!/usr/bin/env bash
# DPT Installer — Sets up agent-do tool, Claude Code hook, and catalog entries
#
# Usage:
#   ./install.sh              Full install (tool + hook + catalog)
#   ./install.sh --tool-only  Just the agent-do symlink
#   ./install.sh --hook-only  Refresh only the thin PostToolUse wrapper
#   ./install.sh --catalog-only  Refresh only legacy discovery entries
#   ./install.sh --uninstall  Remove all installed files

set -euo pipefail

DPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AGENT_DO_DIR=""
CLAUDE_HOOKS_DIR="$HOME/.claude/hooks"
CLAUDE_SETTINGS="$HOME/.claude/settings.json"
FACTORY_CATALOG="$HOME/.factory/agent-do-catalog.yaml"
FACTORY_INDEX="$HOME/.factory/agent-do-index.yaml"

RED='\033[0;31m'
GREEN='\033[0;32m'
CYAN='\033[0;36m'
DIM='\033[2m'
NC='\033[0m'

info()  { echo -e "${CYAN}$1${NC}"; }
ok()    { echo -e "${GREEN}✓${NC} $1"; }
warn()  { echo -e "${RED}!${NC} $1"; }
dim()   { echo -e "${DIM}  $1${NC}"; }

# ============================================================================
# DETECT AGENT-DO
# ============================================================================

find_agent_do() {
    # Check common locations. The repo-local case is the primary path now that
    # DPT lives inside the agent-do tree.
    local repo_root
    repo_root="$(cd "$DPT_DIR/../.." && pwd)"
    local candidates=(
        "$repo_root"
        "$HOME/Documents/AI/Custom_Coding/agent-do"
        "$HOME/agent-do"
    )
    # Check if agent-do is on PATH
    local agent_do_path
    agent_do_path=$(command -v agent-do 2>/dev/null || true)
    if [[ -n "$agent_do_path" ]]; then
        # Follow to find the tools directory
        local real_path
        real_path=$(readlink -f "$agent_do_path" 2>/dev/null || realpath "$agent_do_path" 2>/dev/null || echo "$agent_do_path")
        local candidate_dir
        candidate_dir=$(dirname "$real_path")
        # agent-do binary is in the root of the agent-do repo
        if [[ -d "$candidate_dir/tools" ]]; then
            candidates=("$candidate_dir" "${candidates[@]}")
        fi
    fi

    for dir in "${candidates[@]}"; do
        if [[ -d "$dir/tools" && -f "$dir/agent-do" ]]; then
            AGENT_DO_DIR="$dir"
            return 0
        fi
    done
    return 1
}

# ============================================================================
# INSTALL FUNCTIONS
# ============================================================================

install_tool() {
    info "Installing agent-dpt tool..."

    # Build engine first
    if [[ ! -f "$DPT_DIR/dist/dpt-engine.js" ]]; then
        info "Building DPT engine..."
        bash "$DPT_DIR/bin/build"
    fi

    chmod +x "$DPT_DIR/bin/agent-dpt"
    ok "bin/agent-dpt made executable"

    if find_agent_do; then
        # Create symlink directory in agent-do
        mkdir -p "$AGENT_DO_DIR/tools/agent-dpt"
        ln -sf "$DPT_DIR/bin/agent-dpt" "$AGENT_DO_DIR/tools/agent-dpt/agent-dpt"
        ok "Symlinked into agent-do: $AGENT_DO_DIR/tools/agent-dpt/"
        dim "agent-do dpt <command> is now available"
    else
        warn "agent-do not found. Tool installed at: $DPT_DIR/bin/agent-dpt"
        dim "Add to PATH or symlink manually into agent-do/tools/agent-dpt/"
    fi
}

install_hook() {
    info "Installing Claude Code PostToolUse hook..."

    mkdir -p "$CLAUDE_HOOKS_DIR"

    # Install only a stable delegate. Policy remains in the repo-owned hook, so
    # pulls change behavior immediately and the installed copy cannot drift.
    cat > "$CLAUDE_HOOKS_DIR/dpt-post-edit.sh" << HOOKEOF
#!/usr/bin/env bash
# agent-do DPT hook wrapper v1 (managed by tools/agent-dpt/install.sh).
set -uo pipefail
repo="\${AGENT_DO_REPO:-}"
if [[ -z "\$repo" && -f "\$HOME/.agent-do/install-path" ]]; then
    repo="\$(cat "\$HOME/.agent-do/install-path" 2>/dev/null)"
fi
if [[ -z "\$repo" ]]; then
    repo="$(cd "$DPT_DIR/../.." && pwd)"
fi
canonical="\$repo/tools/agent-dpt/hooks/dpt-post-edit.sh"
if [[ ! -x "\$canonical" ]]; then
    echo "[dpt-post-edit.sh wrapper] canonical hook missing or not executable: \$canonical" >&2
    exit 0
fi
exec "\$canonical" "\$@"
HOOKEOF

    chmod +x "$CLAUDE_HOOKS_DIR/dpt-post-edit.sh"
    ok "Hook installed: $CLAUDE_HOOKS_DIR/dpt-post-edit.sh"

    # Wire into settings.json if it exists
    if [[ -f "$CLAUDE_SETTINGS" ]]; then
        # Check if hook is already wired
        if grep -q "dpt-post-edit.sh" "$CLAUDE_SETTINGS" 2>/dev/null; then
            ok "Hook already wired in settings.json"
        else
            warn "Hook script installed but NOT auto-wired into settings.json"
            dim "Add this to your PostToolUse hooks in $CLAUDE_SETTINGS:"
            echo ""
            echo '    {"type": "command", "command": "~/.claude/hooks/dpt-post-edit.sh", "timeout": 15}'
            echo ""
            dim "Under the PostToolUse section with matcher: \"Edit|Write\""
        fi
    else
        warn "No settings.json found at $CLAUDE_SETTINGS"
        dim "Create it or add the hook manually when you set up Claude Code"
    fi
}

install_catalog() {
    info "Installing catalog and index entries..."

    if [[ -f "$FACTORY_CATALOG" ]]; then
        if grep -q "^  dpt:" "$FACTORY_CATALOG" 2>/dev/null; then
            python3 - "$FACTORY_CATALOG" <<'PY'
import sys
from pathlib import Path

path = Path(sys.argv[1])
text = path.read_text()
updated = text.replace(
    "Design Perception Tensor - automated design quality scoring (72 " + "rules, 5 layers)",
    "Design Perception Tensor - automated design quality scoring (65 rules, 5 layers)",
)
if updated != text:
    path.write_text(updated)
PY
            ok "Catalog entry already exists (current count enforced)"
        else
            cat >> "$FACTORY_CATALOG" << 'CATEOF'

  # === DESIGN QUALITY ===

  dpt:
    category: meta
    description: Design Perception Tensor - automated design quality scoring (65 rules, 5 layers)
    commands:
      - scan [url]: Full scan, returns structured JSON
      - score [url]: Quick score + grade + dimensions
      - report [url]: Narrative design critique
      - violations [url]: Violations sorted by impact
      - baseline [url]: Save scan as comparison baseline
      - diff [url]: Compare current vs baseline
      - build: Rebuild engine from source
    examples:
      - agent-do dpt score
      - agent-do dpt scan https://stripe.com
      - agent-do dpt violations
      - agent-do dpt baseline && agent-do dpt diff
    triggers:
      - design quality
      - design score
      - dpt
      - design check
      - ui quality
      - visual quality
CATEOF
            ok "Catalog entry added to $FACTORY_CATALOG"
        fi
    else
        warn "Catalog not found at $FACTORY_CATALOG"
    fi

    if [[ -f "$FACTORY_INDEX" ]]; then
        if grep -q "dpt:" "$FACTORY_INDEX" 2>/dev/null; then
            python3 - "$FACTORY_INDEX" <<'PY'
import sys
from pathlib import Path

path = Path(sys.argv[1])
text = path.read_text()
updated = text.replace(
    "Design quality scoring - 72 " + "rules across 5 perception layers, 0-100 score",
    "Design quality scoring - 65 rules across 5 perception layers, 0-100 score",
)
if updated != text:
    path.write_text(updated)
PY
            ok "Index entry already exists (current count enforced)"
        else
            # Add to tools section
            sed -i.bak '/^  # META/i\
  # DESIGN QUALITY\
  dpt:       "Design quality scoring - 65 rules across 5 perception layers, 0-100 score"\
' "$FACTORY_INDEX" && rm -f "${FACTORY_INDEX}.bak"
            ok "Index entry added to $FACTORY_INDEX"
        fi
    else
        warn "Index not found at $FACTORY_INDEX"
    fi
}

uninstall() {
    info "Uninstalling DPT..."

    # Remove agent-do symlink
    if find_agent_do; then
        rm -rf "$AGENT_DO_DIR/tools/agent-dpt"
        ok "Removed agent-do symlink"
    fi

    # Remove hook
    rm -f "$CLAUDE_HOOKS_DIR/dpt-post-edit.sh"
    ok "Removed hook script"

    # Note: don't auto-modify settings.json or catalog — too risky
    warn "Manual cleanup needed:"
    dim "Remove dpt-post-edit.sh entry from $CLAUDE_SETTINGS"
    dim "Remove dpt: entries from $FACTORY_CATALOG and $FACTORY_INDEX"
}

# ============================================================================
# MAIN
# ============================================================================

echo ""
echo "  DPT Installer"
echo "  Design Perception Tensor v0.4.0"
echo ""

case "${1:-}" in
    --tool-only)
        install_tool
        ;;
    --hook-only)
        install_hook
        ;;
    --catalog-only)
        install_catalog
        ;;
    --uninstall)
        uninstall
        ;;
    *)
        install_tool
        install_hook
        install_catalog
        ;;
esac

echo ""
echo -e "  ${GREEN}Done.${NC} Test with: agent-do dpt help"
echo ""
