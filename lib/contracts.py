"""Contracts gate and lexicon-driven proposal engine.

The lexicon (lib/contracts-lexicon.yaml) is the source of truth for verb
classification; proposals are regenerable build products. The gate wraps
validate_registry_contracts with the grandfather-baseline ratchet.
"""

from __future__ import annotations

import re
from pathlib import Path

from registry import (
    CONTRACT_BEATS,
    get_tool_contract_attributes,
    get_tool_contracts,
    validate_registry_contracts,
)

LIB_DIR = Path(__file__).resolve().parent
LEXICON_PATH = LIB_DIR / "contracts-lexicon.yaml"
LEARNED_PATH = LIB_DIR / "contracts-lexicon-learned.yaml"
BASELINE_PATH = LIB_DIR / "contracts-baseline.yaml"

_PIPE_GROUP = re.compile(r"<?([a-z0-9][a-z0-9-]*(?:\|[a-z0-9][a-z0-9-]*)+)>?")


def _load_yaml(path: Path) -> dict:
    import yaml

    with open(path) as f:
        return yaml.safe_load(f) or {}


def load_lexicon(path: Path = LEXICON_PATH, learned_path: Path = LEARNED_PATH) -> dict:
    """Hand lexicon merged over agent-derived classifications; hand always wins."""
    lexicon = _load_yaml(path)
    if learned_path.exists():
        merged: dict = {}
        for tool, verbs in (_load_yaml(learned_path).get("overrides") or {}).items():
            merged.setdefault(str(tool), {}).update(verbs or {})
        for tool, verbs in (lexicon.get("overrides") or {}).items():
            merged.setdefault(str(tool), {}).update(verbs or {})
        lexicon["overrides"] = merged
    return lexicon


def load_baseline(path: Path = BASELINE_PATH) -> set[str]:
    if not path.exists():
        return set()
    data = _load_yaml(path)
    return {str(name) for name in data.get("grandfathered") or []}


def _match_pattern(pattern: str, verb: str) -> bool:
    if pattern.startswith("*"):
        return verb.endswith(pattern[1:]) and verb != pattern[1:].lstrip("-")
    if pattern.endswith("*"):
        return verb.startswith(pattern[:-1])
    return verb == pattern


def classify_verb(tool: str, verb: str, lexicon: dict) -> dict | None:
    """Resolve one verb: override → exact → pattern. None means unclassified."""
    overrides = (lexicon.get("overrides") or {}).get(tool) or {}
    if verb in overrides:
        rule = overrides[verb] or {}
        if rule.get("skip"):
            return None
        return {**rule, "rule": f"override:{tool}.{verb}"}
    exact = lexicon.get("exact") or {}
    if verb in exact:
        return {**exact[verb], "rule": f"exact:{verb}"}
    for item in lexicon.get("patterns") or []:
        if _match_pattern(item["match"], verb):
            rule = {k: v for k, v in item.items() if k != "match"}
            return {**rule, "rule": f"pattern:{item['match']}"}
    return None


def _subcommand_tokens(description: str) -> list[str]:
    tokens: list[str] = []
    for group in _PIPE_GROUP.findall(str(description)):
        for token in group.split("|"):
            if token not in tokens:
                tokens.append(token)
    return tokens


def propose_tool_contracts(tool: str, info: dict, lexicon: dict) -> dict:
    """Propose a contracts block for one tool from its commands map."""
    if isinstance(info.get("contracts"), dict):
        contracts = {beat: verbs for beat, verbs in get_tool_contracts(info).items() if verbs}
        attributes = get_tool_contract_attributes(info)
        if attributes:
            contracts["attributes"] = attributes
        return {"source": "declared", "contracts": contracts, "unclassified": [], "rules": {}}

    beats: dict[str, list[str]] = {}
    attributes: dict[str, list[str]] = {}
    rules: dict[str, str] = {}
    unclassified: list[str] = []

    def place(name: str, rule: dict) -> None:
        rules[name] = rule.get("rule", "")
        for beat in rule.get("beats") or []:
            beats.setdefault(beat, []).append(name)
        attrs = rule.get("attributes") or []
        if attrs:
            attributes[name] = list(attrs)

    for verb, description in (info.get("commands") or {}).items():
        verb = str(verb)
        rule = classify_verb(tool, verb, lexicon)
        if rule is not None:
            place(verb, rule)
            continue
        tokens = _subcommand_tokens(str(description))
        if tokens:
            misses = []
            for token in tokens:
                qualified = f"{verb} {token}"
                sub_rule = classify_verb(tool, qualified, lexicon) or classify_verb(
                    tool, token, lexicon
                )
                if sub_rule is not None:
                    place(qualified, sub_rule)
                else:
                    misses.append(qualified)
            unclassified.extend(misses)
        else:
            unclassified.append(verb)

    ordered: dict = {beat: beats[beat] for beat in CONTRACT_BEATS if beat in beats}
    if attributes:
        ordered["attributes"] = attributes
    return {
        "source": "proposed",
        "contracts": ordered,
        "unclassified": sorted(unclassified),
        "rules": rules,
    }


def propose_contracts(registry: dict, lexicon: dict | None = None) -> dict:
    lexicon = lexicon or load_lexicon()
    tools = registry.get("tools") or {}
    proposals = {
        name: propose_tool_contracts(name, info, lexicon)
        for name, info in sorted(tools.items())
        if isinstance(info, dict)
    }
    exceptions = {
        name: item["unclassified"] for name, item in proposals.items() if item["unclassified"]
    }
    classified = sum(len(item["rules"]) for item in proposals.values())
    return {
        "ok": True,
        "proposals": proposals,
        "exceptions": exceptions,
        "stats": {
            "tools": len(proposals),
            "declared": sum(1 for item in proposals.values() if item["source"] == "declared"),
            "proposed": sum(1 for item in proposals.values() if item["source"] == "proposed"),
            "classified_verbs": classified,
            "unclassified_verbs": sum(len(verbs) for verbs in exceptions.values()),
            "tools_with_exceptions": len(exceptions),
        },
    }


def render_markdown(payload: dict, generated_at: str = "") -> str:
    """Render a propose payload as the reviewable inventory document."""
    import yaml

    stats = payload["stats"]
    lines = [
        "# agent-do Contracts Inventory (v2)",
        "",
        f"Generated: {generated_at}" if generated_at else "",
        "",
        "REGENERABLE BUILD PRODUCT — do not hand-edit. Produced by",
        "`agent-do harness contracts propose --out <file>` from `registry.yaml`",
        "+ `lib/contracts-lexicon.yaml`. To change a classification, change the",
        "lexicon (or its `overrides:`) and regenerate.",
        "",
        f"- Tools: {stats['tools']} ({stats['declared']} declared, {stats['proposed']} proposed)",
        f"- Classified verbs: {stats['classified_verbs']}",
        f"- Unclassified verbs: {stats['unclassified_verbs']} across {stats['tools_with_exceptions']} tools",
        "",
        "## Exceptions for review",
        "",
        "Verbs the lexicon could not classify. THIS SECTION IS THE REVIEW",
        "ARTIFACT: resolve each by adding a lexicon rule or per-tool override.",
        "",
    ]
    if payload["exceptions"]:
        for name, verbs in sorted(payload["exceptions"].items(), key=lambda kv: -len(kv[1])):
            lines.append(f"- **{name}**: {', '.join(f'`{verb}`' for verb in verbs)}")
    else:
        lines.append("- none — full coverage")
    lines += ["", "## Proposed declarations", ""]
    for name, item in sorted(payload["proposals"].items()):
        lines.append(f"### {name}")
        lines.append("")
        if item["source"] == "declared":
            lines.append("Existing `contracts:` block in registry.yaml — preserved verbatim.")
            lines.append("")
            continue
        if item["contracts"]:
            block = yaml.safe_dump(
                {"contracts": item["contracts"]}, default_flow_style=False, sort_keys=False
            ).rstrip()
            lines += ["```yaml", block, "```"]
        else:
            lines.append("No verbs classified — every command is an exception (see above).")
        if item["unclassified"]:
            lines.append(f"Review needed: {', '.join(f'`{verb}`' for verb in item['unclassified'])}")
        lines.append("")
    return "\n".join(lines) + "\n"


def validate_gate(registry: dict, strict: bool = False) -> dict:
    """Shape validation plus the grandfather-baseline ratchet."""
    report = validate_registry_contracts(registry)
    tools = registry.get("tools") or {}
    undeclared = {
        name
        for name, info in tools.items()
        if isinstance(info, dict) and not isinstance(info.get("contracts"), dict)
    }
    baseline = load_baseline()
    new_without_contracts = sorted(undeclared - baseline)
    stale_baseline = sorted(baseline - undeclared)

    ok = report["errors"] == 0 and not new_without_contracts and not stale_baseline
    if strict and report["missing"]:
        ok = False
    return {
        "ok": ok,
        "tool": "harness",
        "command": "contracts validate",
        "strict": strict,
        "tools": report["tools"],
        "declared": report["declared"],
        "missing": report["missing"],
        "errors": report["errors"],
        "warnings": report["warnings"],
        "new_without_contracts": new_without_contracts,
        "stale_baseline": stale_baseline,
        "results": [
            item
            for item in report["results"]
            if item["errors"] or any(w["code"] != "missing_contracts" for w in item["warnings"])
        ],
    }
