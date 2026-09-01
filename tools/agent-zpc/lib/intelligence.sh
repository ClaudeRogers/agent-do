#!/usr/bin/env bash
# lib/intelligence.sh — Harvest, Query, Patterns, Promote commands
# Sourced by agent-zpc. Do not run directly.

cmd_harvest() {
    ensure_zpc
    mkdir -p "$ZPC_STATE_DIR"

    local auto=false dry_run=false since=""

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --auto) auto=true; shift ;;
            --dry-run) dry_run=true; shift ;;
            --since) since="$2"; shift 2 ;;
            --help|-h)
                echo "Usage: agent-zpc harvest [--auto] [--dry-run] [--since last]"
                return 0
                ;;
            *) shift ;;
        esac
    done

    log_access "harvest"

    local lessons_file="$ZPC_MEMORY_DIR/lessons.jsonl"
    local decisions_file="$ZPC_MEMORY_DIR/decisions.jsonl"
    local patterns_file="$ZPC_MEMORY_DIR/patterns.md"
    local harvest_log="$ZPC_STATE_DIR/harvest-log.jsonl"

    # Determine since-line for incremental scan
    local since_line=0
    if [[ "$since" == "last" && -f "$harvest_log" && -s "$harvest_log" ]]; then
        since_line=$(python3 << 'PYTHON' - "$harvest_log"
import json, sys
last = ""
with open(sys.argv[1]) as f:
    for line in f:
        line = line.strip()
        if line:
            last = line
if last:
    try:
        obj = json.loads(last)
        print(obj.get("lesson_count", 0))
    except:
        print(0)
else:
    print(0)
PYTHON
        )
    fi

    # Run harvest via python
    local result
    result=$(python3 << 'PYTHON' - "$lessons_file" "$decisions_file" "$patterns_file" "$since_line" "$auto" "$dry_run" "$ZPC_LIB_DIR"
import json, sys, os, re
from collections import Counter

lessons_file = sys.argv[1]
decisions_file = sys.argv[2]
patterns_file = sys.argv[3]
since_line = int(sys.argv[4])
auto_mode = sys.argv[5] == "true"
dry_run = sys.argv[6] == "true"

sys.path.insert(0, sys.argv[7])
import epistemics

# Read lessons. Retracted claims are dropped here rather than filtered later:
# consolidation reads the living corpus, or it launders the corpse into a
# pattern that outlives the row it came from.
format_issues = []
for i, (_, parsed) in enumerate(epistemics.load(lessons_file), 1):
    if parsed is None:
        format_issues.append({"line": i, "missing": ["INVALID JSON"]})

lessons = []
for record in epistemics.analyze(lessons_file, "les-")["claims"]:
    if record["retraction"] is not None:
        continue
    obj = record["row"]
    lessons.append((len(lessons) + 1, obj))
    required = ["date", "context", "problem", "solution", "takeaway", "tags"]
    missing = [k for k in required if k not in obj]
    if missing:
        format_issues.append({"line": len(lessons), "missing": missing})
    elif not isinstance(obj.get("tags"), list):
        format_issues.append({"line": len(lessons), "missing": ["tags (not array)"]})

# Count decisions
decision_count = 0
if os.path.exists(decisions_file):
    with open(decisions_file) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                if not epistemics.is_correction(json.loads(line)):
                    decision_count += 1
            except json.JSONDecodeError:
                pass

# Count patterns
pattern_count = 0
pattern_tags = set()
if os.path.exists(patterns_file):
    with open(patterns_file) as f:
        for line in f:
            m = re.match(r"^## (.+)$", line.strip())
            if m:
                pattern_count += 1
                pattern_tags.add(m.group(1).strip())

# Tag counts (optionally from since_line)
tag_counter = Counter()
for i, obj in lessons:
    if since_line and i <= since_line:
        continue
    for tag in obj.get("tags", []):
        if isinstance(tag, str):
            tag_counter[tag] += 1

# Consolidation gaps
gaps = []
for tag, count in tag_counter.most_common():
    if count >= 3 and tag not in pattern_tags:
        gaps.append({"tag": tag, "count": count})

# Machine-written sections carry this marker, and only they are ever rewritten.
# A hand-written pattern is someone's judgment and stays exactly as typed.
AUTO_MARK = "<!-- zpc:auto -->"


def live_bullets(tag, limit=5):
    """Takeaways still standing for a tag, oldest first, duplicates collapsed."""
    seen = dict.fromkeys(
        text
        for _, obj in lessons
        if tag in obj.get("tags", [])
        for text in [epistemics.claim_text(obj)]
        if text
    )
    return list(seen)[:limit]


def draft_section(tag):
    bullets = live_bullets(tag)
    if not bullets:
        return ""
    return f"\n## {tag}\n{AUTO_MARK}\n" + "\n".join(f"- {b}" for b in bullets) + "\n"


# Draft patterns for gaps
drafts = []
for gap in gaps:
    section = draft_section(gap["tag"])
    if section:
        drafts.append({"tag": gap["tag"], "count": gap["count"], "section": section})


def refresh_auto_sections(path):
    """Rebuild machine-written sections from the corpus as it stands today.

    Retraction is only half a correction while the retracted takeaway survives
    inside a consolidated pattern that every inject repeats. A section whose
    every claim has been retracted is not emptied to a stub — it is removed,
    because there is nothing left that it was consolidating.
    """
    try:
        with open(path) as handle:
            lines = handle.read().split("\n")
    except OSError:
        return [], []

    blocks = []
    current = None
    for line in lines:
        heading = re.match(r"^## (.+)$", line.strip())
        if heading:
            current = {"tag": heading.group(1).strip(), "lines": [line]}
            blocks.append(current)
        elif current is not None:
            current["lines"].append(line)
        else:
            blocks.append({"tag": None, "lines": [line]})

    refreshed, dropped = [], []
    out = []
    for block in blocks:
        tag = block["tag"]
        body = block["lines"]
        is_auto = tag is not None and any(line.strip() == AUTO_MARK for line in body[:2])
        if not is_auto:
            out.extend(body)
            continue
        bullets = live_bullets(tag)
        if not bullets:
            dropped.append(tag)
            continue
        rebuilt = [f"## {tag}", AUTO_MARK] + [f"- {b}" for b in bullets]
        trailing = [line for line in body[::-1] if not line.strip()]
        rebuilt.extend(trailing)
        if rebuilt != body:
            refreshed.append(tag)
        out.extend(rebuilt)

    rebuilt_text = "\n".join(out)
    if rebuilt_text != "\n".join(lines):
        with open(path, "w") as handle:
            handle.write(rebuilt_text)
    return refreshed, dropped


# Auto-write patterns with 5+ lessons
auto_written = []
auto_refreshed, auto_dropped = [], []
if auto_mode and not dry_run:
    auto_refreshed, auto_dropped = refresh_auto_sections(patterns_file)
    if drafts:
        with open(patterns_file, "a") as f:
            for draft in drafts:
                if draft["count"] >= 5:
                    f.write(draft["section"])
                    auto_written.append(draft["tag"])

output = {
    "lesson_count": len(lessons),
    "decision_count": decision_count,
    "pattern_count": pattern_count,
    "format_issues": format_issues,
    "consolidation_gaps": [{"tag": g["tag"], "count": g["count"]} for g in gaps],
    "drafts": drafts,
    "auto_written": auto_written,
    "auto_refreshed": auto_refreshed,
    "auto_dropped": auto_dropped,
    "dry_run": dry_run
}
print(json.dumps(output))
PYTHON
    )

    # Log harvest
    if [[ "$dry_run" == "false" ]]; then
        local log_entry
        log_entry=$(python3 << 'PYTHON' - "$result"
import json, sys
from datetime import datetime
data = json.loads(sys.argv[1])
entry = {
    "date": datetime.now().strftime("%Y-%m-%d"),
    "timestamp": datetime.now().isoformat(),
    "lesson_count": data["lesson_count"],
    "decision_count": data["decision_count"],
    "pattern_count": data["pattern_count"],
    "format_issues": len(data["format_issues"]),
    "gaps": len(data["consolidation_gaps"])
}
print(json.dumps(entry))
PYTHON
        )
        echo "$log_entry" >> "$ZPC_STATE_DIR/harvest-log.jsonl"
    fi

    # Output
    if [[ "${OUTPUT_FORMAT:-text}" == "json" ]]; then
        json_result "$result"
    else
        python3 << 'PYTHON' - "$result"
import json, sys
data = json.loads(sys.argv[1])
prefix = "DRY RUN — " if data["dry_run"] else ""
print(f"{prefix}ZPC HARVEST SUMMARY")
print(f"  Lessons:    {data['lesson_count']} total")
print(f"  Decisions:  {data['decision_count']} total")
print(f"  Patterns:   {data['pattern_count']} sections")
issues = data["format_issues"]
if issues:
    lines = ", ".join(str(i["line"]) for i in issues)
    print(f"  Format issues: {len(issues)} entries (lines: {lines})")
else:
    print(f"  Format issues: 0")
gaps = data["consolidation_gaps"]
print(f"  Consolidation gaps: {len(gaps)} tags need patterns")
for g in gaps:
    print(f"    {g['tag']} ({g['count']} lessons)")
if data["auto_written"]:
    print(f"\n  Auto-written patterns: {', '.join(data['auto_written'])}")
if data.get("auto_refreshed"):
    print(f"  Rebuilt from live lessons: {', '.join(data['auto_refreshed'])}")
if data.get("auto_dropped"):
    print(f"  Dropped (every claim retracted): {', '.join(data['auto_dropped'])}")
if data["drafts"]:
    print("\n--- Draft Patterns ---")
    for d in data["drafts"]:
        if d["tag"] not in data["auto_written"]:
            print(d["section"])
PYTHON
    fi
}

cmd_query() {
    ensure_zpc

    local tag="" since="" text="" qtype="all" limit=20 include_global=false

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --tag|-t) tag="$2"; shift 2 ;;
            --since|-s) since="$2"; shift 2 ;;
            --text) text="$2"; shift 2 ;;
            --type) qtype="$2"; shift 2 ;;
            --limit|-n) limit="$2"; shift 2 ;;
            --global) include_global=true; shift ;;
            --help|-h)
                echo "Usage: agent-zpc query [--global] [--tag X] [--since DATE] [--text \"...\"] [--type lessons|decisions|all]"
                return 0
                ;;
            *) shift ;;
        esac
    done

    log_access "query"

    local lessons_file="$ZPC_MEMORY_DIR/lessons.jsonl"
    local decisions_file="$ZPC_MEMORY_DIR/decisions.jsonl"
    local global_lessons_file="$ZPC_GLOBAL_DIR/global-lessons.jsonl"

    local result
    result=$(python3 << 'PYTHON' - "$lessons_file" "$decisions_file" "$global_lessons_file" "$tag" "$since" "$text" "$qtype" "$limit" "$include_global" "$ZPC_LIB_DIR"
import json, sys, os

lessons_file, decisions_file, global_lessons_file = sys.argv[1], sys.argv[2], sys.argv[3]
tag, since, text, qtype, limit = sys.argv[4], sys.argv[5], sys.argv[6], sys.argv[7], int(sys.argv[8])
include_global = sys.argv[9] == "true"

sys.path.insert(0, sys.argv[10])
import epistemics

def matches(obj, tag, since, text):
    if tag and tag not in obj.get("tags", []):
        return False
    if since and obj.get("date", "") < since:
        return False
    if text:
        text_lower = text.lower()
        blob = json.dumps(obj).lower()
        if text_lower not in blob:
            return False
    return True

def local_claims(path, prefix, kind, scope="project"):
    """Claims with their epistemic state attached, ids derived where absent.

    Deriving here is what lets `query --text les-1a2b3c` find a row whose id has
    not been written to disk yet: the id an agent read in an inject blob is the
    id this search answers to, backfilled or not. The machine-wide store reads
    through the same path: a retracted global row answers a query flagged as
    retracted, never as a live claim.
    """
    rows = []
    for record in epistemics.analyze(path, prefix)["claims"]:
        obj = dict(record["row"])
        obj["_type"] = kind
        obj["_scope"] = scope
        obj["_retracted"] = record["retraction"] is not None
        if record["retraction"] is not None:
            obj["_retraction"] = record["retraction"]
        if record["challenges"]:
            obj["_challenges"] = len(record["challenges"])
        rows.append(obj)
    return rows

results = []

if qtype in ("all", "lessons") and os.path.exists(lessons_file):
    for obj in local_claims(lessons_file, "les-", "lesson"):
        if matches(obj, tag, since, text):
            results.append(obj)

if qtype in ("all", "decisions") and os.path.exists(decisions_file):
    for obj in local_claims(decisions_file, "dec-", "decision"):
        if matches(obj, tag, since, text):
            results.append(obj)

if include_global and qtype in ("all", "lessons") and os.path.exists(global_lessons_file):
    for obj in local_claims(global_lessons_file, "les-", "lesson", scope="global"):
        if matches(obj, tag, since, text):
            results.append(obj)

# Sort by date descending, limit
results.sort(key=lambda x: x.get("date", ""), reverse=True)
results = results[:limit]

print(json.dumps({"count": len(results), "results": results}))
PYTHON
    )

    if [[ "${OUTPUT_FORMAT:-text}" == "json" ]]; then
        json_result "$result"
    else
        python3 << 'PYTHON' - "$result"
import json, sys
data = json.loads(sys.argv[1])
if data["count"] == 0:
    print("No matches found.")
else:
    print(f"Found {data['count']} entries:\n")
    for r in data["results"]:
        t = r.pop("_type", "unknown")
        scope = r.pop("_scope", "project")
        retraction = r.pop("_retraction", None)
        challenges = r.pop("_challenges", 0)
        r.pop("_retracted", None)
        scope_label = "[global] " if scope == "global" else ""
        date = r.get("date", "?")
        # A retracted row is still findable — the point of never deleting it is
        # that its correction can be read beside it.
        state = " [RETRACTED]" if retraction else (f" [challenged: {challenges}]" if challenges else "")
        handle = f" {r['id']}" if r.get("id") else ""
        if t == "lesson":
            print(f"{scope_label}[{date}]{handle} LESSON:{state} {r.get('takeaway', '?')}")
            print(f"  Context: {r.get('context', '')}")
            print(f"  Problem: {r.get('problem', '')}")
            print(f"  Tags: {', '.join(r.get('tags', []))}")
        elif t == "decision":
            print(f"{scope_label}[{date}]{handle} DECISION:{state} {r.get('chosen', '?')}")
            print(f"  Problem: {r.get('decision', '')}")
            print(f"  Rationale: {r.get('rationale', '')}")
            print(f"  Confidence: {r.get('confidence', '?')}")
        if retraction:
            print(f"  Retracted {retraction.get('ts', '')[:10]}: {retraction.get('evidence', '')}")
            if retraction.get("takeaway"):
                print(f"  Instead: {retraction['takeaway']}")
        print()
PYTHON
    fi
}

cmd_patterns() {
    ensure_zpc

    local score=false

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --score) score=true; shift ;;
            --help|-h)
                echo "Usage: agent-zpc patterns [--score]"
                return 0
                ;;
            *) shift ;;
        esac
    done

    log_access "patterns"

    local patterns_file="$ZPC_MEMORY_DIR/patterns.md"

    if [[ ! -f "$patterns_file" ]]; then
        echo "No patterns file found."
        return 0
    fi

    if [[ "$score" == "false" ]]; then
        if [[ "${OUTPUT_FORMAT:-text}" == "json" ]]; then
            local content
            content=$(<"$patterns_file")
            json_success "$content"
        else
            cat "$patterns_file"
        fi
        return 0
    fi

    # Score patterns
    local lessons_file="$ZPC_MEMORY_DIR/lessons.jsonl"
    local result
    result=$(python3 << 'PYTHON' - "$patterns_file" "$lessons_file"
import json, sys, os, re, subprocess
from datetime import datetime, timedelta

patterns_file = sys.argv[1]
lessons_file = sys.argv[2]

# Extract pattern tags
pattern_tags = []
with open(patterns_file) as f:
    for line in f:
        m = re.match(r"^## (.+)$", line.strip())
        if m:
            pattern_tags.append(m.group(1).strip())

# Try to get pattern file modification dates via git
pattern_dates = {}
try:
    git_log = subprocess.check_output(
        ["git", "log", "--follow", "--format=%H %aI", "--", patterns_file],
        stderr=subprocess.DEVNULL, text=True
    ).strip()
    if git_log:
        # Use earliest commit date as baseline
        lines = git_log.strip().split("\n")
        if lines:
            earliest = lines[-1].split(" ", 1)[1][:10]
            for tag in pattern_tags:
                pattern_dates[tag] = earliest
except:
    pass

# Count lessons per tag, split by pattern date. Corrections carry no tags and
# no date of their own; counting them would score a pattern by how often it was
# argued with rather than by how often it failed.
lessons = []
if os.path.exists(lessons_file):
    with open(lessons_file) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                if "retracts" in obj or "challenges" in obj:
                    continue
                lessons.append(obj)
            except:
                pass

scores = []
for tag in pattern_tags:
    pattern_date = pattern_dates.get(tag, "unknown")
    pre = 0
    post = 0
    for lesson in lessons:
        if tag in lesson.get("tags", []):
            if pattern_date != "unknown" and lesson.get("date", "") > pattern_date:
                post += 1
            else:
                pre += 1

    days = 0
    if pattern_date != "unknown":
        try:
            pd = datetime.strptime(pattern_date, "%Y-%m-%d")
            days = (datetime.now() - pd).days
        except:
            pass

    effectiveness = days / (post + 1) if days > 0 else 0
    warning = "Pattern may not be effective" if post > pre and pre > 0 else ""

    scores.append({
        "tag": tag,
        "pattern_date": pattern_date,
        "pre_lessons": pre,
        "post_lessons": post,
        "days_active": days,
        "effectiveness": round(effectiveness, 1),
        "warning": warning
    })

print(json.dumps(scores))
PYTHON
    )

    if [[ "${OUTPUT_FORMAT:-text}" == "json" ]]; then
        json_result "$result"
    else
        python3 << 'PYTHON' - "$result"
import json, sys
scores = json.loads(sys.argv[1])
if not scores:
    print("No patterns to score.")
else:
    print(f"{'Pattern':<20} {'Since':<12} {'Pre':<5} {'Post':<5} {'Score':<8} {'Note'}")
    print("-" * 70)
    for s in scores:
        note = s["warning"] if s["warning"] else "OK"
        print(f"{s['tag']:<20} {s['pattern_date']:<12} {s['pre_lessons']:<5} {s['post_lessons']:<5} {s['effectiveness']:<8} {note}")
PYTHON
    fi
}

cmd_review() {
    ensure_zpc
    mkdir -p "$ZPC_STATE_DIR"

    local since="" phase="" auto=false dry_run=false limit=50

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --since|-s) since="$2"; shift 2 ;;
            --phase|-p) phase="$2"; shift 2 ;;
            --auto) auto=true; shift ;;
            --dry-run) dry_run=true; shift ;;
            --limit|-n) limit="$2"; shift 2 ;;
            --help|-h)
                cat << 'REVIEWHELP'
Usage: agent-zpc review [--since DATE|COMMIT] [--phase "name"] [--auto] [--dry-run]

Post-sprint review: analyze git history and draft lessons/decisions from commits.
Solves the capture discipline problem — lessons that weren't logged during work
get extracted after the fact.

The command reads git log, categorizes commits, and drafts structured entries:
  - fix/bug/error/workaround commits → lesson drafts (error-resolution pairs)
  - revert/undo commits → lesson drafts (corrections)
  - feat/add/implement commits → decision drafts (what was chosen)
  - refactor/migrate/replace commits → decision drafts (architectural changes)

Options:
  --since DATE|COMMIT   Start point (date like 2025-01-15, or commit SHA/tag)
  --phase "name"        Label for this review (stored in review log)
  --auto                Write drafts directly to lessons/decisions JSONL
  --dry-run             Show drafts without writing anything
  --limit N             Max commits to analyze (default 50)

Examples:
  agent-do zpc review --since 2025-02-25               # Since date
  agent-do zpc review --since v0.8                      # Since tag
  agent-do zpc review --since HEAD~20                   # Last 20 commits
  agent-do zpc review --phase "Sprint 3" --auto         # Auto-write with label
  agent-do zpc review --dry-run                         # Preview only

Without --since, uses the last checkpoint or review timestamp as baseline.
REVIEWHELP
                return 0
                ;;
            *) shift ;;
        esac
    done

    # Determine since baseline
    local since_ref="$since"
    if [[ -z "$since_ref" ]]; then
        # Check last review log, then last checkpoint log
        local review_log="$ZPC_STATE_DIR/review-log.jsonl"
        local checkpoint_log="$ZPC_STATE_DIR/checkpoint-log.jsonl"
        if [[ -f "$review_log" && -s "$review_log" ]]; then
            since_ref=$(tail -1 "$review_log" | python3 -c "import json,sys; print(json.loads(sys.stdin.read()).get('last_commit',''))" 2>/dev/null || echo "")
        fi
        if [[ -z "$since_ref" && -f "$checkpoint_log" && -s "$checkpoint_log" ]]; then
            since_ref=$(tail -1 "$checkpoint_log" | python3 -c "import json,sys; print(json.loads(sys.stdin.read()).get('timestamp','')[:10])" 2>/dev/null || echo "")
        fi
        if [[ -z "$since_ref" ]]; then
            since_ref="HEAD~${limit}"
        fi
    fi

    # Get git log — try ref range first, then date, then raw limit
    local git_log=""
    # Try as commit ref range (SHA, tag, HEAD~N)
    git_log=$(git log --oneline --no-merges -n "$limit" "${since_ref}..HEAD" 2>/dev/null) || true
    # If empty, try as date with --since
    if [[ -z "$git_log" ]]; then
        git_log=$(git log --oneline --no-merges -n "$limit" --since="$since_ref" 2>/dev/null) || true
    fi
    # Last resort: just get the last N commits
    if [[ -z "$git_log" ]]; then
        git_log=$(git log --oneline --no-merges -n "$limit" 2>/dev/null) || true
    fi

    if [[ -z "$git_log" ]]; then
        if [[ "${OUTPUT_FORMAT:-text}" == "json" ]]; then
            json_result '{"commits_analyzed":0,"lesson_drafts":[],"decision_drafts":[],"message":"No commits found"}'
        else
            echo "No commits found since $since_ref"
        fi
        return 0
    fi

    local date_str
    date_str="$(today)"

    local result
    result=$(python3 << 'PYTHON' - "$git_log" "$date_str" "$phase"
import json, sys, re

git_log = sys.argv[1]
date_str = sys.argv[2]
phase = sys.argv[3] if sys.argv[3] else "post-sprint review"

fix_patterns = re.compile(r'\b(fix|bug|error|workaround|hotfix|patch|resolve|crash|broken|fail)', re.I)
revert_patterns = re.compile(r'\b(revert|undo|rollback|wrong|restore|back\s*out)', re.I)
feat_patterns = re.compile(r'\b(feat|add|implement|create|introduce|build|wire|integrate|complete|enable)', re.I)
refactor_patterns = re.compile(r'\b(refactor|migrate|replace|restructure|rewrite|reorganize|rename|extract|simplify|consolidate|refine|improve|update|rework|redesign)', re.I)
# Auto-commit pattern from agent swarms — skip these (no semantic content)
auto_commit = re.compile(r'^\[agent-[a-f0-9]+\]\s+Auto-commit:', re.I)

lesson_drafts = []
decision_drafts = []
uncategorized = []

for line in git_log.strip().split("\n"):
    line = line.strip()
    if not line:
        continue
    parts = line.split(" ", 1)
    sha = parts[0]
    msg = parts[1] if len(parts) > 1 else ""

    # Skip auto-commits from agent swarms (no semantic content to extract)
    if auto_commit.search(msg):
        continue

    # Strip conventional commit prefix for cleaner analysis
    clean_msg = re.sub(r'^(fix|feat|refactor|chore|docs|test|style|perf|ci|build|refine|improve|update)(\(.+?\))?:\s*', '', msg, flags=re.I)

    if revert_patterns.search(msg):
        lesson_drafts.append({
            "date": date_str,
            "context": f"git review: {sha[:7]}",
            "problem": clean_msg,
            "solution": "Reverted — original approach was incorrect",
            "takeaway": f"[REVIEW DRAFT] {clean_msg}",
            "tags": ["review", "correction"],
            "source_commit": sha,
            "source_message": msg,
            "category": "revert"
        })
    elif fix_patterns.search(msg):
        lesson_drafts.append({
            "date": date_str,
            "context": f"git review: {sha[:7]}",
            "problem": clean_msg,
            "solution": f"Fixed in commit {sha[:7]}",
            "takeaway": f"[REVIEW DRAFT] {clean_msg}",
            "tags": ["review", "bugfix"],
            "source_commit": sha,
            "source_message": msg,
            "category": "fix"
        })
    elif refactor_patterns.search(msg):
        decision_drafts.append({
            "date": date_str,
            "decision": clean_msg,
            "options": ["[fill in alternatives]"],
            "chosen": clean_msg,
            "rationale": f"[REVIEW DRAFT] from commit {sha[:7]}",
            "confidence": 0.7,
            "mode": "review",
            "tags": ["review", "architecture"],
            "source_commit": sha,
            "source_message": msg,
            "category": "refactor"
        })
    elif feat_patterns.search(msg):
        decision_drafts.append({
            "date": date_str,
            "decision": clean_msg,
            "options": ["[fill in alternatives]"],
            "chosen": clean_msg,
            "rationale": f"[REVIEW DRAFT] from commit {sha[:7]}",
            "confidence": 0.7,
            "mode": "review",
            "tags": ["review", "feature"],
            "source_commit": sha,
            "source_message": msg,
            "category": "feat"
        })
    else:
        uncategorized.append({"sha": sha[:7], "message": msg})

# Get the latest commit SHA for baseline tracking
latest_sha = git_log.strip().split("\n")[0].split(" ", 1)[0] if git_log.strip() else ""

output = {
    "commits_analyzed": len(git_log.strip().split("\n")),
    "lesson_drafts": lesson_drafts,
    "decision_drafts": decision_drafts,
    "uncategorized": uncategorized,
    "latest_commit": latest_sha,
    "phase": phase
}
print(json.dumps(output))
PYTHON
    )

    # Write drafts if --auto (and not --dry-run)
    local lessons_written=0 decisions_written=0
    if [[ "$auto" == "true" && "$dry_run" == "false" ]]; then
        local write_result
        write_result=$(python3 << 'PYTHON' - "$result" "$ZPC_MEMORY_DIR/lessons.jsonl" "$ZPC_MEMORY_DIR/decisions.jsonl"
import json, sys

data = json.loads(sys.argv[1])
lessons_file = sys.argv[2]
decisions_file = sys.argv[3]

written_lessons = 0
written_decisions = 0

if data["lesson_drafts"]:
    with open(lessons_file, "a") as f:
        for draft in data["lesson_drafts"]:
            entry = {k: v for k, v in draft.items() if k not in ("source_commit", "source_message", "category")}
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
            written_lessons += 1

if data["decision_drafts"]:
    with open(decisions_file, "a") as f:
        for draft in data["decision_drafts"]:
            entry = {k: v for k, v in draft.items() if k not in ("source_commit", "source_message", "category")}
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
            written_decisions += 1

print(json.dumps({"written_lessons": written_lessons, "written_decisions": written_decisions}))
PYTHON
        )
        lessons_written=$(echo "$write_result" | python3 -c "import json,sys; print(json.loads(sys.stdin.read())['written_lessons'])")
        decisions_written=$(echo "$write_result" | python3 -c "import json,sys; print(json.loads(sys.stdin.read())['written_decisions'])")
    fi

    # Log review
    if [[ "$dry_run" == "false" ]]; then
        local review_entry
        review_entry=$(python3 << 'PYTHON' - "$result" "$lessons_written" "$decisions_written"
import json, sys
from datetime import datetime
data = json.loads(sys.argv[1])
entry = {
    "date": datetime.now().strftime("%Y-%m-%d"),
    "timestamp": datetime.now().isoformat(),
    "phase": data["phase"],
    "commits_analyzed": data["commits_analyzed"],
    "lesson_drafts": len(data["lesson_drafts"]),
    "decision_drafts": len(data["decision_drafts"]),
    "lessons_written": int(sys.argv[2]),
    "decisions_written": int(sys.argv[3]),
    "last_commit": data["latest_commit"]
}
print(json.dumps(entry))
PYTHON
        )
        echo "$review_entry" >> "$ZPC_STATE_DIR/review-log.jsonl"
    fi

    # Output
    if [[ "${OUTPUT_FORMAT:-text}" == "json" ]]; then
        json_result "$result"
    else
        python3 << 'PYTHON' - "$result" "$dry_run" "$auto" "$lessons_written" "$decisions_written"
import json, sys
data = json.loads(sys.argv[1])
dry_run = sys.argv[2] == "true"
auto = sys.argv[3] == "true"
lessons_written = int(sys.argv[4])
decisions_written = int(sys.argv[5])

prefix = "DRY RUN — " if dry_run else ""
print(f"{prefix}ZPC REVIEW: {data['phase']}")
print(f"  Commits analyzed: {data['commits_analyzed']}")
print(f"  Lesson drafts:    {len(data['lesson_drafts'])}")
print(f"  Decision drafts:  {len(data['decision_drafts'])}")
print(f"  Uncategorized:    {len(data['uncategorized'])}")

if auto and not dry_run:
    print(f"\n  Written: {lessons_written} lessons, {decisions_written} decisions")

if data["lesson_drafts"]:
    print("\n--- Lesson Drafts ---")
    for d in data["lesson_drafts"]:
        cat = d.get("category", "?")
        print(f"  [{cat}] {d['source_message']}")
        print(f"    → {d['takeaway']}")

if data["decision_drafts"]:
    print("\n--- Decision Drafts ---")
    for d in data["decision_drafts"]:
        cat = d.get("category", "?")
        print(f"  [{cat}] {d['source_message']}")
        print(f"    → {d['chosen']}")

if data["uncategorized"]:
    print(f"\n--- Uncategorized ({len(data['uncategorized'])}) ---")
    for u in data["uncategorized"]:
        print(f"  {u['sha']} {u['message']}")
PYTHON
    fi
}

cmd_promote() {
    ensure_zpc

    local source="" target="" rule="" why="" scope="" seen_in=""
    local whens=()
    local positionals=()

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --to) target="$2"; shift 2 ;;
            --rule) rule="$2"; shift 2 ;;
            --why) why="$2"; shift 2 ;;
            --when) whens+=("$2"); shift 2 ;;
            --seen-in) seen_in="$2"; shift 2 ;;
            --scope) scope="$2"; shift 2 ;;
            --help|-h) _promote_help; return 0 ;;
            *) positionals+=("$1"); shift ;;
        esac
    done

    source="${positionals[0]:-}"

    if [[ -z "$source" || -z "$target" ]]; then
        die "Usage: agent-zpc promote <line-number|tag> --to team|global [--rule ... --why ... --when kind:match ... (--seen-in a,b | --scope machine|user)]"
    fi

    if [[ "$target" != "team" && "$target" != "global" ]]; then
        die "Target must be 'team' or 'global'"
    fi

    local lessons_file="$ZPC_MEMORY_DIR/lessons.jsonl"
    local dest_file

    if [[ "$target" == "team" ]]; then
        mkdir -p "$ZPC_TEAM_DIR"
        dest_file="$ZPC_TEAM_DIR/shared-lessons.jsonl"
    else
        ensure_global
        dest_file="$ZPC_GLOBAL_DIR/global-lessons.jsonl"
    fi

    local whens_json
    whens_json=$(printf '%s\n' "${whens[@]+"${whens[@]}"}" | python3 -c 'import json,sys; print(json.dumps([l for l in sys.stdin.read().split("\n") if l]))')

    local result rc=0
    result=$(python3 << 'PYTHON' - "$lessons_file" "$dest_file" "$source" "$ZPC_LIB_DIR" "$target" \
        "$rule" "$why" "$whens_json" "$seen_in" "$scope" "$(dirname "$ZPC_DIR")"
import json, sys, os

lessons_file, dest_file, source = sys.argv[1], sys.argv[2], sys.argv[3]
sys.path.insert(0, sys.argv[4])
import epistemics, triggers

target = sys.argv[5]
rule, why = sys.argv[6], sys.argv[7]
when_specs = json.loads(sys.argv[8])
seen_in = [p.strip() for p in sys.argv[9].split(",") if p.strip()]
scope = sys.argv[10].strip()
promoted_from = os.path.basename(sys.argv[11].rstrip("/")) or sys.argv[11]

# Read source lessons. A retracted claim is not promoted to a wider audience,
# and a correction row is not a lesson anyone can act on.
retracted = {
    record["id"]
    for record in epistemics.analyze(lessons_file, "les-")["claims"]
    if record["retraction"] is not None
}

entries, _ = epistemics.assign_ids(epistemics.load(lessons_file), "les-")
lessons = []
for i, (_, obj) in enumerate(entries, 1):
    if obj is None or epistemics.is_correction(obj):
        continue
    if obj.get("id") in retracted:
        continue
    lessons.append((i, obj))

# Select lessons to promote
selected = []
if source.replace(",", "").isdigit():
    line_nums = set(int(n.strip()) for n in source.split(",") if n.strip())
    for i, obj in lessons:
        if i in line_nums:
            selected.append(obj)
else:
    for i, obj in lessons:
        if source in obj.get("tags", []):
            selected.append(obj)


def key_of(obj):
    return (obj.get("date", ""), obj.get("context", ""), obj.get("problem", ""))


def refuse(lines):
    print(json.dumps({"refused": True, "reasons": lines, "selected": len(selected)}))
    sys.exit(2)


if target == "global":
    # The gate. One row at a time: a machine-wide lesson is promoted on
    # purpose, with its own rule and why, never as a batch.
    if not selected:
        refuse([f"nothing selected by '{source}' (a line number or a tag of a live lesson)"])
    if len(selected) != 1:
        refuse([f"'{source}' selects {len(selected)} lessons; promote to global one at a time, "
                "each with its own --rule, --why and --when"])
    try:
        whens = [triggers.parse_when(spec) for spec in when_specs]
    except triggers.TriggerError as exc:
        refuse([str(exc)])
    missing = triggers.gate(selected[0], rule=rule, why=why, whens=whens,
                            seen_in=seen_in, scope=scope)
    if missing:
        refuse(missing)
    selected = [triggers.stamp(selected[0], rule=rule, why=why, whens=whens,
                               seen_in=seen_in, scope=scope, promoted_from=promoted_from)]

# Existing destination rows, by the identity promote has always used.
existing = {}
dest_entries = epistemics.load(dest_file) if os.path.exists(dest_file) else []
for raw, obj in dest_entries:
    if obj is None or epistemics.is_correction(obj):
        continue
    existing[key_of(obj)] = obj

promoted = updated = skipped = 0
if target == "global":
    # A row already there is re-promoted with its gate fields: this is how a
    # lesson promoted before triggers existed gets its rule, why and when
    # without a retract-and-reissue. The stored id is kept.
    obj = selected[0]
    k = key_of(obj)
    if k in existing:
        rewritten = []
        for raw, parsed in dest_entries:
            if parsed is not None and not epistemics.is_correction(parsed) and key_of(parsed) == k:
                merged = dict(parsed)
                for field in ("rule", "why", "when", "seen_in", "scope", "promoted_from", "promoted_at"):
                    merged.pop(field, None)
                    if field in obj:
                        merged[field] = obj[field]
                rewritten.append((json.dumps(merged, ensure_ascii=False), merged))
                updated += 1
            else:
                rewritten.append((raw, parsed))
        epistemics.write_atomic(dest_file, rewritten)
    else:
        with open(dest_file, "a") as f:
            f.write(json.dumps(obj, ensure_ascii=False) + "\n")
        promoted += 1
else:
    with open(dest_file, "a") as f:
        for obj in selected:
            k = key_of(obj)
            if k not in existing:
                f.write(json.dumps(obj) + "\n")
                existing[k] = obj
                promoted += 1
            else:
                skipped += 1

print(json.dumps({"promoted": promoted, "updated": updated, "skipped": skipped,
                  "total_selected": len(selected), "target": target}))
PYTHON
    ) || rc=$?

    if [[ "$rc" == "$ZPC_RETRACT_REFUSED" ]]; then
        if [[ "${OUTPUT_FORMAT:-text}" == "json" ]]; then
            json_error "$result" "$ZPC_RETRACT_REFUSED" || true
        else
            python3 << 'PYTHON' - "$result" "$source" >&2
import json, sys
data = json.loads(sys.argv[1])
print(f"Refused: '{sys.argv[2]}' may not go machine-wide as filed. Nothing was written.")
print()
for reason in data["reasons"]:
    print(f"  - {reason}")
print()
print("A global lesson rides into every session on this machine. It carries what to do,")
print("why, and the situation that summons it, or it stays a project lesson.")
print("  agent-zpc promote <line> --to global --rule \"...\" --why \"...\" \\")
print("      --when prompt:\"<regex>\" [--when command:\"<regex>\"] [--when path:\"<glob>\"] \\")
print("      --seen-in proj-a,proj-b | --scope machine|user")
PYTHON
        fi
        exit "$ZPC_RETRACT_REFUSED"
    elif [[ "$rc" != 0 ]]; then
        die "Promotion failed; nothing was written."
    fi

    if [[ "${OUTPUT_FORMAT:-text}" == "json" ]]; then
        json_result "$result"
    else
        python3 << 'PYTHON' - "$result" "$target"
import json, sys
data = json.loads(sys.argv[1])
target = sys.argv[2]
if data.get("updated"):
    print(f"Updated {data['updated']} {target} lesson with its rule, why and trigger")
else:
    print(f"Promoted {data['promoted']} lessons to {target}")
if data["skipped"]:
    print(f"  ({data['skipped']} duplicates skipped)")
if target == "global" and (data.get("promoted") or data.get("updated")):
    print("  It fires when its trigger matches; session start carries only `always` rows and a count.")
PYTHON
    fi
}

_promote_help() {
    cat << 'EOF'
Usage: agent-zpc promote <line-number|tag> --to team
       agent-zpc promote <line-number> --to global --rule "<instruction>" --why "<reason>" \
           --when <kind:match> [--when ...] (--seen-in <proj,proj> | --scope machine|user)

A machine-wide lesson rides into every session on this machine, so it has to
earn the seat. Promotion to global refuses (exit 2, nothing written) unless
the row carries:

  --rule      what to do, as an instruction a session can follow
  --why       the reason, so a session can tell when the rule does not apply
  --when      the situation that summons it, one or more of:
                prompt:<regex>     words in what the user typed
                command:<regex>    a shell command about to run
                path:<glob>        a file just edited
                always             every session's opening context (rare)
  --seen-in   two or more project names it bit in, or
  --scope     machine|user when it is about this machine or this user

Rows a machine wrote (mined, auto-captured) are never eligible. Re-promoting a
row already in the global store updates its rule/why/when in place under the
same id. Team promotion is unchanged: promote <lines|tag> --to team.

Delivery follows from --when: `always` rows render at session start; the rest
wait, and the hook that fires at that moment injects them
(agent-zpc inject --trigger prompt|command|path <value>).

Examples:
  agent-zpc promote 14 --to global \
      --rule "Prove a test's premise inside the test before asserting the behavior" \
      --why "a test that fakes its own premise can assert nothing and still pass" \
      --when path:"test_*.py" --when path:"*.test.*" --scope user
EOF
}

