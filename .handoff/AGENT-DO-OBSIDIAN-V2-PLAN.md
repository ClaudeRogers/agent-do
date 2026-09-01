# agent-do obsidian v2: build Erik's vault into a fully agentic knowledge surface

**Author:** Claude Opus 4.7 (1M context) for Erik Fritsch.
**For:** Codex / Chris / whoever implements. Erik's call.
**Status:** Implementation brief. Self-contained. Built on agent-do contracts (Connect → Snapshot → Interact → Verify → Save) and the context redesign in `.handoff/SESSION-HANDOFF-2026-05-15-2.md`.

---

## 0. TL;DR

The current `agent-do obsidian` is a clean ~1,000-line bash wrapper around Obsidian's official CLI. It exposes obsidian-cli's surface verbatim, gates power-user operations behind `+live`, and adds little above. Solid foundation, narrow ambition.

This plan rebuilds it as Erik's full vault-management surface: a tool the inner-harness agent uses to read, write, reason over, and maintain a vault with tens of thousands of notes, without Erik ever opening Obsidian himself. Natural-language CLI hits the target. Never blind. Never lazy.

The shape of the change:

1. **Local vault index.** A SQLite FTS5 index at `<vault>/.agent-do/obsidian/index.db`. Incrementally maintained. Powers fast reads, queries, graph ops, and aggregations without going through obsidian-cli for every operation. This is a derived local cache, rebuilt per machine from vault markdown, never team-shared truth.
2. **Per-vault conventions config.** `<vault>/.agent-do/conventions.yaml` defines inbox folder, frontmatter defaults, folder roles, task style, related-find scope. Falls back to `~/.agent-do/obsidian/conventions.yaml`. Travels with the vault.
3. **Unified Task model.** Both Tasks-plugin inline syntax and frontmatter-on-note tasks normalize into one Task record. Query surface is identical regardless of underlying representation.
4. **`save` verb.** Absorbs the entire `save-to-obsidian` skill responsibility. It shadow-runs against the skill until parity is proven across real saves. Only then does the skill deprecate. Deletion is a later cleanup, not a Phase B gate.
5. **AI-grounded reasoning verbs.** `relate`, `tasks next`, `summarize`, `audit`. The tool exposes structured data; the inner-harness agent reasons. (Optional Pattern-B AI calls inside the tool for summarize, see §10.)
6. **Five-beat contract declaration** in `registry.yaml`. Tool grades against the contracts plan from `.handoff/AGENT-DO-CONTRACTS-PLAN.md`.

After v2: Erik says "what should I work on this morning" or "save this and link it to the Trinity Site work" or "find every note where I've touched on Saoshyant" or "rename Project X to Project Y across the whole vault" or "what's gone stale in my goals folder" → the inner-harness agent calls one or two `agent-do obsidian` verbs and returns a precise, complete answer. No Obsidian app open. No agent guessing.

---

## 1. The orienting principle

Erik never types `agent-do obsidian` commands. The inner-harness agent does. Every verb is the agent's verb. Every read returns enough structured metadata that the agent can reason without re-querying. Every write is journaled and provenance-tagged.

**Never blind.** Vault state is indexed and queryable. The agent does not have to guess what's in the vault or where.

**Never lazy.** Read commands return rich records (paths, snippets, mtimes, frontmatter, link counts) by default in JSON. The agent gets one round-trip's worth of context, not a stub.

**Never fails on scale.** Tens of thousands of notes. Every query path must be O(index) or O(matches), never O(vault).

---

## 2. Architecture

```
                        agent-do obsidian <verb>
                                  │
                ┌─────────────────┼─────────────────┐
                │                 │                 │
            READS                WRITES         REASONING
                │                 │                 │
        Local SQLite        obsidian-cli         AI-gated
        FTS5 index          (live IPC to         (relate, next,
        (per vault)         Obsidian app)        summarize, audit)
                │                 │                 │
                ▼                 ▼                 ▼
        Fast structured    Live in Obsidian    Structured answers
        JSON results       (re-indexed by      from the index +
                           Obsidian)            optional Claude call
                                  │
                                  ▼
                          Local index re-syncs
                          (mtime-based, incremental)
```

**Key architectural decisions:**

- **Reads hit the local index** by default. obsidian-cli's read path goes through the running app via IPC: too slow at vault scale and requires Obsidian to be running. The local index is rebuilt from filesystem walk + frontmatter parse + tag/link/task extraction. Fully functional with Obsidian closed.
- **Search and query prefer the local index during app startup.** Obsidian process running and plugin indices ready are different states. When Obsidian is mid-launch or plugin caches are rebuilding, `search` and safe `query` use the local SQLite index rather than plugin-backed IPC paths.
- **Writes use a per-command write-path policy.** Some verbs can use obsidian-cli when the app is ready. Some verbs, such as multi-file link rewrites, need direct filesystem writes with journaled rollback. Power-user surgery remains `+live`. See the write-path table in §5.
- **A vault write-lock protects same-machine writes.** Every write path takes `<vault>/.agent-do/obsidian/.write-lock` with PID, timestamp, operation, and affected paths. Multi-file operations also re-stat each target before write to catch cross-machine sync drift from Obsidian Sync, iCloud, Git, or another editor.
- **Incremental refresh** uses file mtime, size, and optional hash verification for changed files. A `refresh` command does a full rescan; the daemon-less default is opportunistic refresh on read miss.
- **The index is per-vault** and lives inside the vault at `<vault>/.agent-do/obsidian/index.db`. It is Obsidian-safe (`.agent-do/` is hidden from Obsidian's default file scan), but it is a derived local cache. Each machine rebuilds its own DB. `index.db`, `embeddings.db`, operation journals, backups, and `.write-lock` are gitignored; `conventions.yaml` and templates are tracked when the vault is shared.
- **Storage backend is SQLite + FTS5.** No daemon. Native Python `sqlite3`. Index size for ~50k notes is ~50–100 MB. Query latency sub-100ms on M-series hardware.
- **Optional embeddings backend** (later phase). An `embeddings.db` next to `index.db` populated on demand. Enables semantic similarity for `relate` and `query`. Not in v2 done criteria; v2 leaves the hook.

---

## 3. Per-vault conventions config

`<vault>/.agent-do/conventions.yaml`. Falls back to `~/.agent-do/obsidian/conventions.yaml`. Falls back to built-in defaults if neither exists.

Schema:

```yaml
# Where new notes land by default
inbox_folder: "+"

# Frontmatter shape applied by `save` and `create` when --frontmatter is not
# fully specified. Values support {today}, {now}, {project}, {user} tokens.
default_frontmatter:
  up: ""
  related: []
  created: "{today}"
  log: "[[{today}]]"
  tags: []
  scope: "local"  # composes with the context redesign's scope tiers

# Folders with semantic roles. The agent uses these to place notes.
folders:
  inbox: "+"
  projects: "Projects"
  daily: "Daily"
  meetings: "Meetings"
  people: "People"
  goals: "0 - Atomic Life Work"
  archive: "Archive"

# Task model preference: agents create tasks in this style by default.
# Query surface returns both styles regardless.
task_default_style: "frontmatter"   # "frontmatter" | "inline"
task_inline:
  use_emojis: true
  priority_map:
    highest: "⏫"
    high: "🔼"
    medium: "🔽"
    low: "⏬"
  due_emoji: "📅"
  scheduled_emoji: "⏳"
  start_emoji: "🛫"
  done_emoji: "✅"
task_frontmatter:
  type_field: "type"
  type_value: "task"
  priority_field: "priority"
  due_field: "due"
  scheduled_field: "scheduled"
  status_field: "status"
  project_field: "project"
  resonance_field: "resonance"

# Related-find behavior
related_find:
  default_limit: 5
  scope: "inbox"            # "inbox" | "vault" | folder list
  score_weights:
    title_similarity: 0.4
    tag_overlap: 0.3
    folder_proximity: 0.15
    link_graph: 0.15
  validation_corpus: ".agent-do/obsidian/relate-validation.jsonl"

# Next-action scoring. Defaults live in code; vaults can tune them.
task_next_weights:
  priority_weight: 0.35
  due_proximity_weight: 0.30
  resonance_weight: 0.20
  project_focus_weight: 0.15

# Save behavior
save:
  default_folder_token: "inbox"
  auto_related: true
  auto_related_limit: 5
```

Erik confirmed per-vault conventions. Config and templates travel with the vault and can be team-shared when the vault is in a private repo. Derived DBs and locks remain local.

---

## 4. Tasks model (unified)

Two underlying representations supported. One unified Task record returned by all query verbs.

### 4.1 Inline (Tasks-plugin style)

In any note:

```markdown
- [ ] Review Codex's audit findings 🔼 📅 2026-05-25 #project/agent-do
```

Extracted into:

```json
{
  "id": "<source_path>:<line>",
  "text": "Review Codex's audit findings",
  "status": "todo",
  "priority": "high",
  "due": "2026-05-25",
  "scheduled": null,
  "project": "agent-do",
  "tags": ["project/agent-do"],
  "source_note": "Daily/2026-05-18.md",
  "source_line": 42,
  "style": "inline"
}
```

### 4.2 Frontmatter (dedicated task note)

A note like `Tasks/Review Codex Audit.md`:

```yaml
---
type: task
status: open
priority: high
due: 2026-05-25
project: agent-do
resonance: 8
tags: [project/agent-do]
---

# Review Codex's audit findings

Notes on what to look for...
```

Extracted into:

```json
{
  "id": "Tasks/Review Codex Audit.md",
  "text": "Review Codex's audit findings",
  "status": "open",
  "priority": "high",
  "due": "2026-05-25",
  "scheduled": null,
  "project": "agent-do",
  "resonance": 8,
  "tags": ["project/agent-do"],
  "source_note": "Tasks/Review Codex Audit.md",
  "source_line": null,
  "style": "frontmatter"
}
```

### 4.3 Unified query surface

All `tasks` commands return the unified shape. Filtering and sorting work identically across both styles.

```bash
agent-do obsidian tasks list \
    --status open \
    --priority highest,high \
    --due-before 2026-06-01 \
    --project agent-do \
    --sort priority,due,resonance \
    --limit 20 \
    --json
```

Creation defaults to `task_default_style` from conventions config. Override with `--style inline|frontmatter`.

---

## 5. v2 command surface (full)

Marked with the contract beat (C/S/I/V/Sa) and a short status note.

### 5.1 Environment

| Command | Beat | Notes |
|---|---|---|
| `doctor [--fix] [--json]` | V | existing; extend to also report index health (last refresh, row count, drift since rescan) |
| `snapshot [--json]` | S | existing; extend with vault stats (note count, tag count, task counts by status, recent activity) |
| `refresh [--full] [--vault V] [--json]` | C/I | NEW: incremental rescan of index (default) or full rebuild |

### 5.2 Notes

| Command | Beat | Notes |
|---|---|---|
| `read <name> [--path] [--json]` | S | existing; `--json` returns full structured record (path, frontmatter, body, tags, outgoing links, backlinks count, mtime) |
| `create <name> [--content T] [--folder F] [--frontmatter k=v,...] [--up X] [--related auto\|<list>] [--tags <list>] [--template T] [--overwrite] [--open] [--json]` | I | upgrade existing: add structured-frontmatter flags and related-find auto-population |
| `append <name> [text...] [--content T] [--path] [--section <header>] [--json]` | I | upgrade existing: `--section` appends under a specific markdown header instead of end-of-note |
| `move <from> <to> [--update-links] [--json]` | I | NEW: rename or move a note, journal the write plan, update all `[[wikilinks]]` across the vault, verify, then rollback or expose repair if verification fails |
| `delete <name> [--confirm] [--json]` | I | NEW: trash a note (use Obsidian's `.trash/` convention) with backlink warnings |

### 5.3 Save (replaces the save-to-obsidian skill)

| Command | Beat | Notes |
|---|---|---|
| `save --content <text> [--title <auto-or-given>] [--folder <token-or-path>] [--up <wikilink>] [--related auto\|<list>] [--tags <list>] [--scope local\|team\|public] [--json]` | Sa | NEW: full skill-replacement. Composes frontmatter from conventions config + flags. Auto-globs vault for related when `--related auto`. Returns the full structured note record. |
| `save-group <hub-name> --child <name>:<content> [--child <name>:<content>]... [--folder F] [--tags <list>] [--scope ...] [--child-scope <name>:local\|team\|public] [--json]` | Sa | NEW: creates the hub + each child, cross-links them all via `related:`, sets `up:` on children. Group scope applies to all children unless a child-level scope override is supplied. |

### 5.4 Search and query

| Command | Beat | Notes |
|---|---|---|
| `search <query> [--limit N] [--folder F] [--tag T] [--mode fts\|exact] [--json]` | S | upgrade existing: structured JSON with snippets, score, path, mtime |
| `query <dql-subset> [--json]` | S | NEW: parse a safe Dataview DQL subset (`FROM`, `WHERE`, `SORT`, `LIMIT`, basic `FLATTEN`) and translate it to SQL against the local index. Full Dataview execution stays behind `+live eval`. |
| `relate <name-or-content> [--limit N] [--scope inbox\|vault\|folder] [--json]` | S | NEW: given a note name or raw content, return ranked wikilink candidates (title similarity + tag overlap + folder proximity + link graph) |
| `summarize <topic> [--limit N] [--style brief\|long] [--json]` | S | NEW: pull top matching notes, summarize across them. Uses `lib/ai_router.py` (Pattern B). Cites every source note. |

### 5.5 Properties (frontmatter)

| Command | Beat | Notes |
|---|---|---|
| `prop get <name> [--file F] [--json]` | S | upgrade existing: `--json` returns typed values |
| `prop set <name> <value> [--file F] [--json]` | I | existing |
| `prop list <file> [--json]` | S | NEW: dump all frontmatter for a file |
| `prop batch <query> --set k=v,k=v... [--json] [--dry-run]` | I | NEW: bulk-set properties on every file matching a query. `--dry-run` returns affected files without writing. |

### 5.6 Tasks

| Command | Beat | Notes |
|---|---|---|
| `tasks list [--status ...] [--priority ...] [--due-before D] [--due-after D] [--scheduled-before D] [--project P] [--tag T] [--folder F] [--sort field1,field2,...] [--limit N] [--json]` | S | rewrite existing: unified across styles, multi-dimensional filtering, JSON-default |
| `tasks add "<text>" [--priority P] [--due D] [--scheduled D] [--project P] [--tags <list>] [--resonance N] [--into <note>] [--style inline\|frontmatter] [--json]` | I | NEW: append a task to a note (`--into`) or create a frontmatter task note |
| `tasks complete <id> [--json]` | I | NEW: mark complete by Task id |
| `tasks update <id> --set k=v,... [--json]` | I | NEW: change priority/due/project/etc. on an existing task |
| `tasks next [--context <space>] [--horizon today\|week\|month] [--limit N] [--json]` | S | NEW: returns ranked next-action recommendations. Composite score uses priority + due-proximity + resonance + project-focus. Pure data; agent reasons. |

### 5.7 Tags

| Command | Beat | Notes |
|---|---|---|
| `tags list [--counts] [--sort name\|count] [--prefix P] [--json]` | S | upgrade existing: JSON-default, hierarchical filtering by `--prefix` |
| `tags rename <from> <to> [--update-notes] [--json]` | I | NEW: rename a tag across the vault, optionally update inline `#tag` references |
| `tags merge <from1,from2,...> <to> [--json]` | I | NEW: merge multiple tags into one |

### 5.8 Backlinks and graph

| Command | Beat | Notes |
|---|---|---|
| `backlinks <name> [--json]` | S | upgrade existing: JSON-default |
| `graph orphans [--folder F] [--json]` | S | NEW: notes with no backlinks (and optionally no outgoing links either) |
| `graph broken-links [--json]` | S | NEW: `[[wikilinks]]` pointing at nonexistent notes |
| `graph clusters [--min-size N] [--json]` | S | NEW: connected components in the link graph |
| `graph cluster <name> [--depth N] [--json]` | S | NEW: notes within N hops of a given note |
| `graph tag-usage <tag> [--json]` | S | NEW: where a tag is used, how often, in which folders |

### 5.9 Calendar / daily / periodic

| Command | Beat | Notes |
|---|---|---|
| `daily read [--date YYYY-MM-DD] [--json]` | S | upgrade existing: `--date` for arbitrary date, JSON-default |
| `daily append [text...] [--date YYYY-MM-DD] [--section H] [--json]` | I | upgrade existing |
| `daily list [--since 7d\|30d\|90d] [--json]` | S | NEW: list daily notes in a window |
| `weekly read \| append \| list ...` | S/I | NEW: same shape for weekly notes |
| `period read --from YYYY-MM-DD --to YYYY-MM-DD [--json]` | S | NEW: aggregate notes (any) created or modified in a window |

### 5.10 Templates

| Command | Beat | Notes |
|---|---|---|
| `templates list [--json]` | S | NEW: list registered templates |
| `templates show <name> [--json]` | S | NEW: dump template + its parameter schema |
| `templates apply <name> --target <path> [--param k=v,...] [--json]` | I | NEW: instantiate a template with parameter substitution |
| `templates register <name> --from <path> [--param-schema schema.yaml]` | I | NEW: register a vault file as a template; ships with optional schema for parameters |

Templates live under `<vault>/.agent-do/obsidian/templates/`. Each is a `.md` file with `{{PARAM}}` substitution. Optional sibling `<name>.yaml` defines parameter schema.

### 5.11 Audit (vault hygiene)

| Command | Beat | Notes |
|---|---|---|
| `audit [--scope folder] [--json]` | V | NEW: run all vault-health checks (orphans, broken links, tag misuse, missing required frontmatter, stale daily notes, etc.) and return a structured report |
| `audit fix <issue-id> [--dry-run] [--json]` | I | NEW: apply the recommended fix for a specific audit finding |

### 5.12 +live escape hatches (kept)

| Command | Beat | Notes |
|---|---|---|
| `eval <code>` | I | existing; +live-gated. Arbitrary JS in Obsidian app context. |
| `dev errors\|screenshot\|dom\|console\|css\|mobile` | S/I | existing; +live-gated dev tools |
| `plugin reload <id>` | I | existing; +live-gated plugin management |

These stay as escape hatches for power-user surgery. Common cases (Dataview queries, link rename, plugin-data reads) get promoted into stable, scoped commands above.

### 5.13 Write-path policy

Each Interact or Save command declares exactly one primary write path and one fallback. The implementation must not rely on the coarse rule "CLI when running, filesystem when closed."

| Command family | Primary path | Fallback | Required safety |
|---|---|---|---|
| `create`, `append`, `daily append`, `weekly append` | obsidian-cli when app and plugin index are ready | direct filesystem write | write-lock, frontmatter validation, local index refresh |
| `save`, `save-group` | direct filesystem write | obsidian-cli only when needed for live open-note behavior | write-lock, shadow parity with `save-to-obsidian`, full record return |
| `move`, `tags rename`, `tags merge`, `prop batch` | direct filesystem write | none for multi-file rewrites | write-lock, preflight, write plan, backups, apply, verify, rollback or repair-by-id |
| `delete` | filesystem move to Obsidian `.trash/` convention | obsidian-cli trash if exposed and verified | write-lock, backlink warnings, reversible trash move |
| `eval`, `dev`, `plugin reload` | `+live` app context | none | explicit `+live` gate |

For every multi-file operation, preflight records path, mtime, size, and hash when cheap. Immediately before each write, the tool re-stats the target. If the file changed since preflight, it aborts with exit 2 and structured JSON explaining the drift. This handles cross-machine sync races that the local write-lock cannot see.

---

## 6. Contracts declaration

Per `.handoff/AGENT-DO-CONTRACTS-PLAN.md`, the tool's `registry.yaml` entry adds the first contract block in Phase A, then expands it in the same phase that adds each new verb. Contracts are not a final cleanup phase.

```yaml
contracts:
  connect:
    - doctor
  snapshot:
    - snapshot
    - read
    - search
    - query
    - relate
    - summarize
    - tasks list
    - tasks next
    - tags list
    - backlinks
    - graph orphans
    - graph broken-links
    - graph clusters
    - graph cluster
    - graph tag-usage
    - daily read
    - daily list
    - weekly read
    - weekly list
    - period read
    - prop get
    - prop list
    - templates list
    - templates show
  interact:
    - refresh
    - create
    - append
    - move
    - delete
    - prop set
    - prop batch
    - tasks add
    - tasks complete
    - tasks update
    - tags rename
    - tags merge
    - daily append
    - weekly append
    - templates apply
    - templates register
    - audit fix
  verify:
    - doctor
    - audit
  save:
    - save
    - save-group
```

Concurrency class stays `mixed`. Connect/Snapshot are read; Interact/Save are write.

Routing is classifier-fed, not a parallel keyword cascade. The registry declares labels and examples, and the prompt-router adds those labels to `ai_route_prompt` with examples. Do not add a separate regex or keyword path for Obsidian intents.

```yaml
routing:
  intents:
    - label: vault_save_intent
      examples:
        - "save this to my vault"
        - "put that in obsidian"
        - "lock this in"
      recommended_entrypoint: "agent-do obsidian save --content ..."
    - label: vault_find_intent
      examples:
        - "find every note about X"
        - "where did I write about Y"
      recommended_entrypoint: "agent-do obsidian search \"...\" --json"
    - label: vault_ask_intent
      examples:
        - "summarize my thinking on X"
        - "what do my notes say about Y"
      recommended_entrypoint: "agent-do obsidian summarize \"...\" --json"
    - label: vault_organize_intent
      examples:
        - "what should I work on next"
        - "what's gone stale"
      recommended_entrypoint: "agent-do obsidian tasks next --json"
    - label: vault_refactor_intent
      examples:
        - "rename X to Y across my vault"
        - "merge tags A and B"
      recommended_entrypoint: "agent-do obsidian move ..."
```

---

## 7. Storage shape

```
<vault>/
├── .agent-do/
│   ├── conventions.yaml          # per-vault config (§3)
│   ├── .gitignore                # ignores local cache and lock files
│   └── obsidian/
│       ├── index.db              # derived local SQLite FTS5 cache, gitignored
│       ├── embeddings.db         # derived local cache, optional later phase, gitignored
│       ├── .write-lock           # transient same-machine write lock, gitignored
│       ├── operations/
│       │   ├── journals/         # preflight, write-plan, apply, verify logs, gitignored
│       │   └── backups/          # rollback material for multi-file rewrites, gitignored
│       ├── relate-validation.jsonl # local tuning corpus unless explicitly shared
│       └── templates/
│       │   ├── project.md
│       │   ├── project.yaml      # optional parameter schema
│       │   ├── meeting.md
│       │   └── ...

~/.agent-do/obsidian/
├── conventions.yaml              # home default (fallback)
└── templates/                    # global templates
```

The vault markdown files are the source of truth. `index.db`, `embeddings.db`, `.write-lock`, operation journals, backups, and generated validation artifacts are local by default and gitignored. Track `conventions.yaml` and `templates/` in private/shared vault repos when the team should share conventions. Audit findings are durable records in the context ledger, not an unstructured local history file.

Index schema (SQLite):

```sql
CREATE TABLE notes (
  path TEXT PRIMARY KEY,
  title TEXT,
  folder TEXT,
  mtime INTEGER,
  size INTEGER,
  frontmatter_json TEXT,
  body_excerpt TEXT,
  scope TEXT
);

CREATE VIRTUAL TABLE notes_fts USING fts5 (
  title, body, content='notes', content_rowid='rowid'
);

CREATE TABLE tags (
  tag TEXT,
  note_path TEXT,
  PRIMARY KEY (tag, note_path)
);

CREATE TABLE links (
  src_path TEXT,
  target_name TEXT,
  resolved_path TEXT,
  PRIMARY KEY (src_path, target_name)
);

CREATE TABLE tasks (
  id TEXT PRIMARY KEY,
  text TEXT,
  status TEXT,
  priority TEXT,
  due TEXT,
  scheduled TEXT,
  project TEXT,
  resonance INTEGER,
  tags_json TEXT,
  source_note TEXT,
  source_line INTEGER,
  style TEXT
);

CREATE INDEX notes_mtime ON notes (mtime);
CREATE INDEX notes_folder ON notes (folder);
CREATE INDEX notes_scope ON notes (scope);
CREATE INDEX tags_tag ON tags (tag);
CREATE INDEX links_target ON links (target_name);
CREATE INDEX tasks_status ON tasks (status);
CREATE INDEX tasks_due ON tasks (due);
CREATE INDEX tasks_project ON tasks (project);
```

Refresh strategy:
- **Full rebuild** (`refresh --full`): walk the vault, parse every file, re-populate every table. Runs in batches; reports progress in `--json`.
- **Incremental** (`refresh`, default): walk files whose mtime or size changed since the index's last scan. Updates changed rows and removes deleted files from every dependent table.
- **Opportunistic** (automatic): every read command checks the target file's mtime against the index; if stale, re-parses that file before returning. Bounded staleness without forcing full rebuilds.

For ~50,000 notes:
- Full rebuild target: under 60 seconds
- Incremental refresh target: under 2 seconds for a normal session's worth of changes
- Query latency target: under 100ms for any single command

---

## 8. Implementation phases

### Phase A: Index foundation, contracts, and routing
Build the SQLite schema, the indexer (filesystem walk + frontmatter parse + tag/link/task extraction), and the `refresh` command. Ship `read` and `search` re-implemented against the index. Add the first `contracts:` block and the first `routing.intents:` labels in `registry.yaml` immediately. Wire those labels into the AI classifier prompt template as labels with examples, not as regex or keyword matching.

### Phase B: Save replaces the skill
Build `save` and `save-group`. Wire frontmatter conventions config. Implement `--related auto` against the index. Shadow-run against `save-to-obsidian` for real saves and compare path, title, frontmatter, related links, tags, and body. Erik can move default agent routing to `agent-do obsidian save` only after parity is proven; the skill deprecates later.

### Phase C: Tasks model
Implement the unified Task record. Rewrite `tasks list`. Add `tasks add`, `tasks complete`, `tasks update`, `tasks next`. Both styles supported. `tasks next` returns ranked recommendations using the composite score; no AI required yet.

### Phase D: Search/query/relate/summarize
Add `query` as a safe DQL-to-SQL subset over the local index. Full Dataview execution stays behind `+live eval`. Add `relate`, then build a 20-30 example validation set from real saves where Erik confirms or corrects suggested backlinks. Store those corrections in `<vault>/.agent-do/obsidian/relate-validation.jsonl` and tune the default weights before locking them in conventions. Add `summarize` (uses `lib/ai_router.py` through a dedicated summarization prompt for the cross-note synthesis). Ship the `--json` upgrade across all read commands.

### Phase E: Graph + audit + tags + templates
Build the graph commands (`graph orphans`, `broken-links`, `clusters`, `cluster`, `tag-usage`). Add `tags rename`, `tags merge`. Add `templates` subcommands. Add `audit` and `audit fix`. Audit writes findings to the vault-audit context ledger with stable finding id, severity, first-seen, last-seen, and resolution status, so "current findings" and "since last audit" are both answerable.

### Phase F: Calendar + move + delete
`daily list`, `weekly`, `period`. `move`, `delete`. `prop batch`.

### Final hardening
No standalone contracts or routing phase. By this point each shipped verb already has its contract and classifier-routed intent metadata. Final hardening is only for full-suite validation, documentation, and measured vault-scale proof.

Phases A and B are the critical path: after A+B, Erik can route new saves to `agent-do obsidian save` only if shadow parity against `save-to-obsidian` is proven. Phases C and D unlock the "ask the vault anything" experience. E and F round out the surface before final hardening.

---

## 9. Done criteria

1. `./test.sh` passes from repo root throughout all phases.
2. `agent-do obsidian doctor --json` reports index health alongside CLI wiring.
3. `agent-do obsidian refresh --full` rebuilds the index. Reports note count, task count, tag count, link count, broken-link count, runtime.
4. `agent-do obsidian search "<query>" --json` returns structured records with snippets, ranks, mtimes, and tags, under 100ms on a 50k-note vault.
5. `agent-do obsidian save --content "test note body" --tags test,demo --related auto --json` creates a note with conventions-config frontmatter, auto-populated `related:`, in the configured inbox folder. Returns the full structured note record.
6. `agent-do obsidian save-group "Hub" --child "Child A":body --child "Child B":body --scope team --child-scope "Child B":local --json` creates 3 notes cross-linked correctly, applies group scope by default, and honors child scope override.
7. `agent-do obsidian tasks list --status open --priority high,highest --sort due,priority --json` returns the unified task records across both styles.
8. `agent-do obsidian tasks next --horizon today --json` returns ranked recommendations with reasoning fields (priority, due-proximity, resonance, project-focus components of the composite score).
9. `agent-do obsidian relate "<title or content>" --json` returns ranked backlink candidates.
10. `agent-do obsidian summarize "Saoshyant" --json` returns a synthesis with cited source notes.
11. `agent-do obsidian audit --json` returns a structured vault-health report (orphans, broken links, tag misuse, missing-frontmatter notes).
12. `agent-do obsidian move "<from>" "<to>" --update-links --json` uses preflight, write plan, backups, apply, verify, and rollback or repair-by-move-id. It does not claim filesystem atomicity across the whole vault.
13. `agent-do obsidian query "FROM #project WHERE status=active SORT due ASC" --json` runs the safe DQL-to-SQL subset and returns rows. Full Dataview execution remains `+live`.
14. New integration tests under `tools/agent-obsidian/test/` cover: index round-trip, save with conventions, save-to-obsidian shadow parity, tasks unified surface, DQL subset query, relate, move with link updates, sync-race mtime drift, audit findings.
15. `registry.yaml` `obsidian` entry has phase-current `contracts:` block (§6) and classifier-fed `routing.intents:` block.
16. Prompt-router AI classifier recognizes obsidian intents (save / find-in-vault / ask-the-vault / organize / refactor) through AI labels and examples, with no separate keyword or regex cascade.
17. `README.md`, `CLAUDE.md`, and `docs/TOOLS.md` updated. `save-to-obsidian` skill is marked deprecated only after shadow parity is proven. It is not deleted in v2.
18. Vault scale: index a 10,000-note test vault end-to-end. `tasks list` returns in <100ms. `audit` returns in <5s.

---

## 10. Anti-goals (v2 will not do)

- **No daemon.** No long-running process maintaining the index. Refresh happens on demand or opportunistically per-file on read.
- **No vault format invention.** All notes stay as Obsidian-readable markdown with standard frontmatter. The index is derived, never authoritative.
- **No unjournaled multi-file writes.** Move/delete/rename use Obsidian's expected paths where relevant and write through the per-command policy in §5.13.
- **No blanket replacement of obsidian-cli.** The write path is per command. The implementation must not pretend every write is safer through IPC or every write is safer through raw filesystem access.
- **No eval-based Dataview outside `+live`.** v2 promotes only a safe DQL-to-SQL subset. Full Dataview execution stays gated.
- **No derived cache as source of truth.** Index DBs, embedding DBs, operation journals, and lock files are rebuildable local state.
- **No embeddings in v2.** Architecture leaves the hook (`embeddings.db`). Implementation deferred to v3.
- **No multi-vault aggregation in v2.** Each vault has its own index. Cross-vault queries deferred.
- **No tool-internal AI loops** beyond `summarize` (and optional reranking in `relate`). The tool returns structured data; the inner-harness agent reasons. This keeps the tool fast and deterministic except where AI is genuinely earning its keep.
- **No new top-level tool.** Everything lives under `agent-do obsidian`. No `agent-do vault`, no `agent-do notes`. Per the contracts plan: namespace stays flat; meaning lives in metadata.

---

## 11. Composition with the rest of agent-do

### Contracts plan
The tool declares its `contracts:` block (§6) in Phase A and keeps it current as verbs land. Audit grades against the five-beat contracts. Every Snapshot verb returns JSON. Every Save verb is journaled, returns a full record, and records provenance.

### Context redesign
A vault is a `context docs internal` source (per the v2 handoff's context redesign). `agent-do context retrieve "<query>"` calls into `agent-do obsidian search` for vault hits and merges with upstream-docs hits in one ranked result set. Frontmatter `scope:` field maps to the context scope tiers (local/team/public). Vault-as-team-scope works automatically when the vault is in a private repo.

Audit findings compose with the context ledger primitive. `agent-do obsidian audit` writes durable vault-audit ledger entries with stable ids, severity, first-seen, last-seen, status, source paths, and suggested fix. The local index can compute findings quickly, but the ledger is what preserves history.

### Prompt-router intent classifier
Add obsidian intents to the AI classifier's output schema:
- `vault_save_intent`: "save this to my vault," "lock this in," "put that in obsidian"
- `vault_find_intent`: "find every note about X," "where did I write about Y"
- `vault_ask_intent`: "summarize my thinking on X," "what do my notes say about Y"
- `vault_organize_intent`: "what should I work on next," "what's overdue," "what's gone stale"
- `vault_refactor_intent`: "rename X to Y across my vault," "merge tags A and B"

When the classifier returns these, the hook nudges toward the right obsidian verb. Per the recent hook fix, false positives stop at the classifier; keyword paths don't exist. Adding Obsidian routing by regex would reintroduce the deleted misfire class.

### agent-do creds
Obsidian Sync API credentials (if Erik enables it) live in `agent-do creds` under a declared `OBSIDIAN_SYNC_TOKEN` env. Not v2 done criteria; just leave the hook.

### agent-do coord
When multiple agents are working in the same vault (Erik + Chris), they each maintain their own index but share the vault's `.agent-do/conventions.yaml`. coord can claim notes for write-conflict avoidance. Not v2 done criteria.

coord does not replace the vault write-lock. coord is a social coordination surface across agents. The write-lock and mtime re-stat checks are the mechanical corruption guard.

---

## 12. Design decisions locked by review

1. **Index location.** `<vault>/.agent-do/obsidian/index.db` keeps the index inside the vault, but it is a derived local cache. Gitignore DBs, locks, operation journals, backups, and generated tuning artifacts by default. Track `conventions.yaml` and `templates/` when the vault is private or team-shared.
2. **`save` filename derivation.** When `--title` is not provided, the tool needs to derive a filename from content. Sentence-extraction heuristic? Or call AI? My read: heuristic first (first H1 if present, else first sentence under 60 chars), AI fallback only when heuristic fails.
3. **`tasks next` scoring weights.** Composite score is `priority_weight × priority + due_proximity × urgency + resonance_weight × resonance + project_focus × in_focus_bonus`. Weights live in conventions config? Hardcoded with overrides? My read: defaults hardcoded, overridable per-vault in `conventions.yaml` under `task_next_weights`.
4. **Move link rewrites.** Updating `[[wikilinks]]` across a 50k-note vault is not atomic at the filesystem level. Use a journaled operation: preflight, write plan, backups, apply, verify, and rollback or `audit fix link-rewrite <move-id>`.
5. **Read-only Dataview without `+live`.** DQL parsing is tractable, but eval-based execution is unsafe to make read-only. v2 implements a small DQL-to-SQL translator against the local index. Full Dataview stays behind `+live eval`; v3 can expand the grammar.
6. **Embeddings provider.** When v3 adds semantic search, what embeds the notes? OpenAI's text-embedding-3-small? Anthropic's (when available)? Local model? My read: pluggable via `agent-do creds`-declared providers; default to OpenAI text-embedding-3-small for cost.
7. **`save` return shape.** Return the full structured record by default (path + frontmatter + body + related links), not just the path. This saves the agent a second read.
8. **Tasks plugin emoji parsing robustness.** The plugin's emoji syntax has multiple variants and ordering rules. Parsing must be forgiving. My read: build a tested parser against a corpus of real inline tasks from Erik's vault before relying on it.
9. **Classifier-fed routing.** Routing intents live in the AI classifier prompt as labels with examples. They do not get implemented as a second regex or keyword path.
10. **Plugin index readiness.** Obsidian running does not mean Omnisearch, Tasks, or Dataview plugin caches are ready. Search/query prefer the local SQLite index while the app is launching or plugin caches are stale.
11. **Relate tuning.** Initial weights are guesses. Phase D must gather 20-30 real confirmations/corrections from Erik and tune weights from `<vault>/.agent-do/obsidian/relate-validation.jsonl`.
12. **Sync races.** The write-lock only protects one machine. Every multi-file operation re-stats targets before write and fails closed with structured JSON when mtime or size drifted since preflight.
13. **Audit history.** Audit findings are ledger records, not one-shot output. Store finding history in the context ledger with stable ids and status.
14. **Save-group scope.** `save-group --scope team` applies to the hub and all children unless a child-level scope override is supplied.

---

## 13. Suggested sequence for whoever implements

1. Read §0 (TL;DR) and §1 (orienting principle). Internalize: every verb is the agent's, never blind, never lazy.
2. Spike Phase A (index foundation, contracts, classifier-fed routing) on a sample of Erik's vault to validate the schema and refresh strategy. Confirm <100ms query latency.
3. Ship Phase A and B together only with shadow parity against `save-to-obsidian`. Deprecate the skill later after real-save parity is proven. Do not delete it in v2.
4. Ship Phase C (tasks). Run `tasks list` and `tasks next` against the full vault.
5. Ship Phase D. `summarize` and `relate` come online.
6. Ship E and F in parallel or sequence as bandwidth allows, then run final hardening. Final hardening is not delayed contracts or delayed routing.
7. Write `.handoff/agent-do-obsidian-v2-built.md` summarizing what shipped, the actual query latencies measured at vault scale, and any deviations from this brief.

The done criteria in §9 are the gates. The anti-goals in §10 are the boundaries. The conventions config in §3 is the user-facing contract. Everything else is implementation choice.

---

## 14. The end state Erik named

> "I want AI to manage my entire vault of tens of thousands of notes, to know everything, I can ask about anything and it can link my thinking, organize, etc. I shouldn't even have to open up Obsidian, I can just come to the CLI and ask in natural language and it's 100% hitting the target, never fails, never blind, never lazy."

After v2:

- **"What's on my plate today?"** → inner-harness agent calls `agent-do obsidian tasks next --horizon today --json`, returns ranked recommendations with reasoning.
- **"Save this to my vault, link it to the Trinity Site work."** → agent calls `agent-do obsidian save --content "<...>" --up "Trinity Site" --related auto --json`.
- **"Find every note where I've touched on Saoshyant."** → agent calls `agent-do obsidian search "Saoshyant" --json` and `agent-do obsidian relate "Saoshyant" --json`.
- **"What's gone stale in my goals folder?"** → agent calls `agent-do obsidian audit --scope "0 - Atomic Life Work" --json`.
- **"Rename Project X to Project Y across the vault."** → agent calls `agent-do obsidian move "Project X" "Project Y" --update-links --json`.
- **"Summarize my thinking on the Sword and Rose Matrix this year."** → agent calls `agent-do obsidian summarize "Sword and Rose Matrix" --json`.
- **"What did I write about Kit on May 12th?"** → agent calls `agent-do obsidian daily read --date 2026-05-12 --json` plus a search filtered to that date.

You never type a CLI command. The inner-harness agent does. The tool returns structured truth. The agent answers in conversation.

That's the end state. v2 is what builds it.
