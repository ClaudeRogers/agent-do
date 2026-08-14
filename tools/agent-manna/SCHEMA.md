# Manna JSONL Schema

This document defines the exact JSONL (JSON Lines) format for Manna's storage files.

## Storage Location

All data is stored in `.manna/` directory:
- `.manna/issues.jsonl` - Issue records (one JSON object per line)
- `.manna/sessions.jsonl` - Session event log (one JSON object per line)
- `.manna/drift.yaml` - Latest reconcile findings (written by `reconcile --write-drift`)
- `.manna/workflow.yaml` - Strict workflow version and canonical handoff root

Durable work orders live in tracked `.handoff/`:
- `.handoff/README.md` - Generated ownership and usage contract
- `.handoff/mn-xxxxxx-<slug>.md` - One generated work order per actionable item

## issues.jsonl

Each line is a complete JSON object representing one issue.

### Example
```jsonl
{"id":"mn-a1b2c3","title":"Fix login","status":"open","description":null,"created_at":"2026-01-29T10:00:00Z","updated_at":"2026-01-29T10:00:00Z","blocked_by":[],"claimed_by":null,"claimed_at":null}
```

### Field Definitions

| Field | Type | Required | Constraints | Description |
|-------|------|----------|-------------|-------------|
| `id` | String | Yes | Format: `mn-{6-hex}`, auto-extends on collision | Unique issue identifier |
| `title` | String | Yes | 1-500 characters | Issue title/summary |
| `status` | String | Yes | Enum: `open`, `in_progress`, `blocked`, `done` | Current issue state |
| `description` | String or null | No | Optional long-form text | Detailed description |
| `created_at` | String | Yes | ISO8601 timestamp | When issue was created |
| `updated_at` | String | Yes | ISO8601 timestamp | Last modification time |
| `blocked_by` | Array | Yes | Array of issue IDs (strings) | Issues blocking this one |
| `claimed_by` | String or null | No | Session ID or null | Who is working on this |
| `claimed_at` | String or null | No | ISO8601 timestamp or null | When it was claimed |
| `type` | String | No | Enum: `track`, `item`, `dream`; omitted when `item` (default) | Issue type: umbrella track, work item, or intake spark |
| `track` | String or null | No | ID of an existing `type: track` issue; tracks don't nest | Track this issue belongs to |
| `source` | String or null | No | Free text (note path, URL, conversation) | Where this issue came from |
| `prompt` | String or null | No | Strict boards require repository-relative Markdown below `.handoff/` | Work-order file paired with this item |

v1 rows carry none of the new optional fields (`type`, `track`, `source`,
`prompt`); they deserialize as `type: item` and re-serialize unchanged (lazy
upgrade — the file is never rewritten just to add defaults).

### Workflow and handoff pairing

New or empty boards initialized by Manna are strict workflow version 1.
`create` generates the item handoff and writes its path into `prompt`; neither
side is optional for an active item. The handoff contains the item's scope and
exactly one `agent-do manna claim <id>` target. Tracks and dreams do not carry
handoffs. A strict pointer cannot be repointed or cleared through `update`.

`claim` enforces the pair before state changes. The file must exist, be
Git-visible, remain below `.handoff/`, and claim only its own item. A violation
exits 2 and leaves the board unchanged. `lint` applies the same contract, and
`reconcile` (kind `prompt_pairing`) checks both directions:

- **Forward**: an issue's pointer resolves to an existing file that never
  mentions the issue's id.
- **Reverse**: a claim command in `.handoff/**/*.md` — a line
  containing `manna claim mn-xxxxxx`, any invocation prefix
  (`agent-do manna claim`, absolute-path binary, `MANNA_SESSION_ID=...`
  pins) — targets a board issue whose pointer is missing or does not
  resolve back to that file. The claim relationship is the signal: bare id
  mentions elsewhere in a prompt file are data, not pairing promises.
  Foreign-board ids are ignored (cross-repo prompts are legal).

Strict reconcile also reports `workflow_sprawl` when an active local id is
claimed from `.handoffs/`, `.dev/session-prompts/`, or a nested
`handoff-prompts/` directory, or when an active item points outside
`.handoff/`.

Nonempty boards without `.manna/workflow.yaml` stay in legacy mode. They keep
the prior absolute-pointer behavior, the description-first-line
`PROMPT: <path>` fallback, and the `.dev/session-prompts/` reverse scan. Init
does not rearrange those boards implicitly.

Done issues are exempt from all of it, so archived or renamed prompts never
nag history.

### Status Transitions

```
open → in_progress (via claim)
in_progress → done (via done)
in_progress → open (via abandon)
* → blocked (when blocked_by is non-empty)
blocked → * (when blocked_by becomes empty)
```

### The dream gate

A `type: dream` row has no entry into that diagram. `claim` refuses it — exit
2, nothing written — and names the conversion; the refusal, not hiding, is the
gate. Dreams stay visible in `list` and `context` throughout, every row marked
`[DREAM: not claimable, needs conversion]`, so an agent reads the idea and its
un-actionable status in the same glance.

`update <id> --type item` is the authorization act (Erik's to make) and prints
an explicit `AUTHORIZED:` line saying the row is now claimable work; the
reverse prints `PARKED:`. Every other verb still works on a dream, and
`update --status done` remains the way a dream is closed with a reason.

### ID Format

- Prefix: `mn-` (manna)
- Hash: 6 hexadecimal characters (lowercase)
- Collision handling: Auto-extend to 7, 8, ... characters
- Example: `mn-a1b2c3`, `mn-f4e5d6c`

## sessions.jsonl

Each line is a session event (append-only log).

### Example
```jsonl
{"session_id":"ses_abc123","event":"start","timestamp":"2026-01-29T10:00:00Z","context":{}}
{"session_id":"ses_abc123","event":"claim","timestamp":"2026-01-29T10:01:00Z","issue_id":"mn-a1b2c3"}
{"session_id":"ses_abc123","event":"done","timestamp":"2026-01-29T10:05:00Z","issue_id":"mn-a1b2c3"}
{"session_id":"ses_abc123","event":"end","timestamp":"2026-01-29T11:00:00Z","context":{}}
```

### Field Definitions

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `session_id` | String | Yes | Session identifier (from `$MANNA_SESSION_ID`) |
| `event` | String | Yes | Event type (see below) |
| `timestamp` | String | Yes | ISO8601 timestamp of event |
| `issue_id` | String | Conditional | Required for `claim`, `release`, `done` events |
| `context` | Object | Conditional | Required for `start`, `end` events (can be empty) |

### Event Types

| Event | Description | Required Fields |
|-------|-------------|-----------------|
| `start` | Session begins | `session_id`, `event`, `timestamp`, `context` |
| `claim` | Issue claimed for work | `session_id`, `event`, `timestamp`, `issue_id` |
| `release` | Issue unclaimed (abandoned) | `session_id`, `event`, `timestamp`, `issue_id` |
| `done` | Issue completed | `session_id`, `event`, `timestamp`, `issue_id` |
| `end` | Session ends | `session_id`, `event`, `timestamp`, `context` |

## drift.yaml

Written atomically (temp + rename) by `reconcile --write-drift`. Shape:

```yaml
generated_at: "<ISO8601 UTC>"
session: "<session id or null>"   # MANNA_SESSION_ID if pinned, else null
findings:
  - kind: landed_open|dead_claim|blocker_desync|stale_dream|dangling_track|doc_reference|prompt_pairing|skipped
    issue_id: "mn-xxxxxx"   # optional
    detail: "one line"
    evidence: "sha / file:line / pid"   # optional
    proposed_fix: "one line"            # optional
```

Commit trailers feeding the `landed_open` check are body lines of exactly
`Manna: mn-xxxxxx` (key case-sensitive, one ID per line, multiple lines allowed).

## File Format Rules

1. **One JSON object per line** - No pretty printing, no multi-line JSON
2. **Append-only** - New records are always appended to the end
3. **No deletion** - Records are never removed (issues can be marked `done`)
4. **UTF-8 encoding** - All files must be UTF-8
5. **Newline terminated** - Each line ends with `\n`

## Corruption Handling

If a line cannot be parsed as valid JSON:
- Skip the malformed line
- Log a warning to stderr
- Continue processing remaining lines

This allows recovery from partial writes or corruption.

## Concurrency

All writes must acquire an exclusive file lock (flock) before modifying JSONL files.

See DESIGN.md for implementation details.
