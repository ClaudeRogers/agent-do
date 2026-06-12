"""Registry-vs-implementation drift: do tools honor their command promises?

Parser spec verified against all 94 tools with zero false positives
(2026-06-12 fan-out). The cardinal rule learned there: NEVER gate
extraction by section-header text — legitimate domain headers (NOTES,
ENV VARS, BRANCHES) collide with any stoplist and silently delete real
command sections. Filter per line instead.

Two channels, asymmetric by design:
- declared_only — registry promises a verb the tool's --help lacks.
  High precision; the actionable bug class (metrics/slack-react). FAILS.
- help_only — help shows a verb the registry omits. Registry commands
  maps are intentionally curated subsets (~half the tools), so this is
  an ADVISORY channel only; never gate on it.
"""

from __future__ import annotations

import re

_ARGPARSE_BRACE = re.compile(r"^  \{([^}]+)\}")
_VERB_TOKEN = re.compile(r"^[a-z][a-z0-9-]*$")
# Ignore: argparse/clap auto-subcommand, and the universal listing alias.
_IGNORED_VERBS = {"help"}
_IGNORED_ALIASES = {"ls"}


def extract_help_verbs(help_text: str) -> dict:
    """Extract command verbs from a tool's --help output.

    Returns {"first_tokens": set, "full_paths": set} — registry keys match
    against either (gcp uses multi-word keys; everyone else first-token).
    """
    first_tokens: set[str] = set()
    full_paths: set[str] = set()

    for raw in help_text.splitlines():
        brace = _ARGPARSE_BRACE.match(raw)
        if brace:
            for verb in re.split(r"[,|]", brace.group(1)):
                verb = verb.strip()
                if _VERB_TOKEN.match(verb) and verb not in _IGNORED_VERBS:
                    first_tokens.add(verb)
            continue
        if not raw.startswith("  ") or raw.startswith("   "):
            continue
        line = raw[2:]
        if not line or line[0] in "-$" or line.startswith("agent-"):
            continue
        # sig = text before the first 2+-space description gap
        gap = re.search(r"\s{2,}", line)
        sig = line[: gap.start()] if gap else line
        tokens = sig.split()
        if not tokens:
            continue
        # lead = tokens until the first flag/placeholder
        lead: list[str] = []
        for token in tokens:
            if token.startswith("-") or token[0] in "<[{":
                break
            lead.append(token)
        if not lead:
            continue
        # Prose filter: no description column AND a long lead = sentence text.
        if gap is None and len(lead) > 2:
            continue
        for alias in " ".join(lead).split(" / "):
            run: list[str] = []
            for token in alias.split():
                if any(ch in token for ch in "{|<["):
                    break
                if not _VERB_TOKEN.match(token):
                    break
                run.append(token)
            if not run:
                continue
            if run[0] in _IGNORED_VERBS:
                continue
            # Aliases like `ls` stay in the sets so declared registry keys
            # can match them; they are filtered from the ADVISORY channel only.
            first_tokens.add(run[0])
            full_paths.add(" ".join(run))

    return {"first_tokens": first_tokens, "full_paths": full_paths}


def drift_tool(tool: str, commands: dict, help_text: str) -> dict:
    """Diff one tool's registry commands map against its help output."""
    verbs = extract_help_verbs(help_text)
    if commands and not verbs["first_tokens"]:
        # Help produced no parseable command lines at all — a missing runtime
        # dependency (unbuilt binary, absent tmux), not N phantom verbs. Real
        # drift always shows a working help listing the OTHER verbs.
        return {"tool": tool, "error": "help yielded no parseable commands",
                "declared_only": [], "help_only": []}
    declared_only = sorted(
        key
        for key in commands
        if str(key) not in verbs["first_tokens"]
        and str(key) not in verbs["full_paths"]
        and str(key).split()[0] not in verbs["first_tokens"]
    )
    registry_first_tokens = {str(key).split()[0] for key in commands}
    help_only = sorted(
        token
        for token in verbs["first_tokens"]
        if token not in registry_first_tokens and token not in _IGNORED_ALIASES
    )
    return {"tool": tool, "declared_only": declared_only, "help_only": help_only}


def drift_registry(tools: dict, help_for, only_tool: str | None = None) -> dict:
    """Run drift across the registry. help_for(tool) -> help text or None."""
    results = {}
    declared_only_total = 0
    for name, info in sorted(tools.items()):
        if only_tool and name != only_tool:
            continue
        if not isinstance(info, dict):
            continue
        help_text = help_for(name)
        if help_text is None:
            results[name] = {"tool": name, "error": "help unavailable",
                            "declared_only": [], "help_only": []}
            continue
        report = drift_tool(name, info.get("commands") or {}, help_text)
        declared_only_total += len(report["declared_only"])
        results[name] = report
    return {
        "ok": declared_only_total == 0,
        "declared_only_total": declared_only_total,
        "results": results,
    }
