# agent-do Contracts Inventory (v2)

Generated: 2026-07-22T15:16:31Z

REGENERABLE BUILD PRODUCT — do not hand-edit. Produced by
`agent-do harness contracts propose --out <file>` from `registry.yaml`
+ `lib/contracts-lexicon.yaml`. To change a classification, change the
lexicon (or its `overrides:`) and regenerate.

- Tools: 95 (95 declared, 0 proposed)
- Classified verbs: 0
- Unclassified verbs: 0 across 0 tools
- Read surface (snapshot/verify only — safe to parallelize): 487 verbs
- Write surface (connect/interact/save): 488 verbs

## Safety surface

The classifications that change agent behavior: what destroys data,
what emits or persists secrets, what runs opaque payloads, and what
never returns. Review these first — a missing entry here is the
dangerous kind of error.

### destructive (55) — irreversible data loss; confirm before auto-running

`agent kill`, `appleevents cache`, `auth clear`, `browse api delete`, `browse session delete`, `calendar delete`, `clipboard clear`, `cloudflare dns-del`, `context cache clear`, `context maintain`, `context remove-source`, `coord bye`, `coord need clear`, `coord publish clear`, `creds delete`, `excel sheet delete`, `gcp secret-del`, `git snap restore`, `git sweep`, `git worktree remove`, `jupyter kernel`, `manna delete`, `namecheap dns-del`, `obsidian delete`, `psql restore`, `render blueprint delete`, `render cache-purge`, `render dedicated-ip delete`, `render delete`, `render disk delete`, `render env-del`, `render env-group del-var`, `render env-group delete`, `render environment delete`, `render header del`, `render kv delete`, `render registry delete`, `render route del`, `render secret del`, `render webhook delete`, `repl kill`, `supabase addon-remove`, `supabase branch-delete`, `supabase branch-reset`, `supabase delete`, `supabase domain-delete`, `supabase function-delete`, `supabase replica-remove`, `supabase secret-del`, `supabase vanity-delete`, `tail prune`, `tui kill`, `unbrowse delete`, `vector link`, `vercel env-del`

### sensitive (24) — emits or persists secret material; guard output

`auth import-browser`, `browse auth get-creds`, `browse auth store-creds`, `creds delete`, `creds store`, `email code`, `email link`, `gcp auth token`, `gcp sa-key-create`, `gcp secret-get`, `gcp secrets`, `okta app-create-oidc service`, `okta app-create-oidc web`, `okta app-creds`, `okta app-creds-rotate`, `render db`, `render env-group secret`, `render kv connect-info`, `render secret get`, `sms code`, `sms link`, `supabase api-keys`, `supabase db-connect`, `supabase secrets`

### passthrough (11) — arbitrary-payload escape hatch; beat decided by the argument

`android shell`, `appleevents run`, `appleevents tell`, `docker exec`, `docker shell`, `ide run`, `ide terminal`, `k8s exec`, `ssh exec`, `tail run`, `tail start`

### long_running (27) — daemon/stream/session; may never return

`audio transcribe`, `auth ensure`, `browse agent`, `browse capture`, `context serve`, `gcp oauth-setup`, `hardware midi monitor`, `hardware serial monitor`, `k8s port-forward`, `lab start`, `latex watch`, `logs tail`, `meetings chat`, `obsidian chat`, `obsidian embed refresh`, `serial monitor`, `tail follow`, `tail run`, `tail start`, `teams chat`, `transcribe transcribe`, `tui spawn`, `unbrowse capture`, `voice listen`, `voice record`, `voice transcribe`, `wireshark capture`

### polymorphic (27) — beat decided by payload or flag at call time

`appleevents cache`, `context retrieve`, `coord guard`, `coord interrupts`, `db query`, `docker compose`, `git branch`, `git sweep`, `hardware printer default`, `harness contracts propose`, `harness manifest`, `manna reconcile`, `meetings meet`, `meetings teams`, `meetings zoom`, `psql exec`, `psql query`, `render db`, `supabase query`, `supabase rest`, `supabase sql`, `unbrowse replay`, `vector intake`, `vector members`, `vision detect`, `zpc harvest`, `zpc review`

### composite (37) — one call performs several beats internally

`appleevents permissions`, `audio transcribe`, `auth advance`, `auth ensure`, `auth import-browser`, `auth probe`, `browse agent`, `context crawl`, `context maintain`, `coord touch`, `dpt baseline`, `email code`, `email link`, `eval run`, `gcp oauth-setup`, `harness contracts audit`, `harness contracts drift`, `harness evidence`, `models doctor`, `notion bootstrap-team`, `notion doctor`, `notion webhooks doctor`, `notion webhooks ingest`, `obsidian doctor`, `slack dm`, `sms code`, `sms link`, `supabase db-connect`, `swarm parallel`, `swarm pipeline`, `swarm spawn`, `transcribe cost`, `transcribe doctor`, `transcribe transcribe`, `vector intake`, `voice transcribe`, `zpc checkpoint`

### own_state (27) — writes only its own cache/state; parallel-safe

`debug break`, `debug continue`, `debug step`, `dpt baseline`, `dpt build`, `eval create`, `eval run`, `figma export`, `ghidra analyze`, `ghidra decompile`, `ide goto`, `ide open`, `pdf2md batch`, `pdf2md convert`, `prompt save`, `tail prune`, `tail stop`, `vision detect`, `vision source file`, `vision source image`, `vision source ios`, `vision source rtsp`, `vision source screen`, `vision source webcam`, `vision source window`, `wireshark capture`, `wireshark filter`

## Exceptions for review

Verbs the lexicon could not classify. THIS SECTION IS THE REVIEW
ARTIFACT: resolve each by adding a lexicon rule or per-tool override.

- none — full coverage

## Proposed declarations

### 3d

Existing `contracts:` block in registry.yaml — preserved verbatim.

### agent

Existing `contracts:` block in registry.yaml — preserved verbatim.

### android

Existing `contracts:` block in registry.yaml — preserved verbatim.

### api

Existing `contracts:` block in registry.yaml — preserved verbatim.

### appleevents

Existing `contracts:` block in registry.yaml — preserved verbatim.

### audio

Existing `contracts:` block in registry.yaml — preserved verbatim.

### auth

Existing `contracts:` block in registry.yaml — preserved verbatim.

### bluetooth

Existing `contracts:` block in registry.yaml — preserved verbatim.

### browse

Existing `contracts:` block in registry.yaml — preserved verbatim.

### burp

Existing `contracts:` block in registry.yaml — preserved verbatim.

### cad

Existing `contracts:` block in registry.yaml — preserved verbatim.

### calendar

Existing `contracts:` block in registry.yaml — preserved verbatim.

### ci

Existing `contracts:` block in registry.yaml — preserved verbatim.

### clerk

Existing `contracts:` block in registry.yaml — preserved verbatim.

### clipboard

Existing `contracts:` block in registry.yaml — preserved verbatim.

### cloud

Existing `contracts:` block in registry.yaml — preserved verbatim.

### cloudflare

Existing `contracts:` block in registry.yaml — preserved verbatim.

### colab

Existing `contracts:` block in registry.yaml — preserved verbatim.

### context

Existing `contracts:` block in registry.yaml — preserved verbatim.

### coord

Existing `contracts:` block in registry.yaml — preserved verbatim.

### creds

Existing `contracts:` block in registry.yaml — preserved verbatim.

### db

Existing `contracts:` block in registry.yaml — preserved verbatim.

### debug

Existing `contracts:` block in registry.yaml — preserved verbatim.

### discord

Existing `contracts:` block in registry.yaml — preserved verbatim.

### dns

Existing `contracts:` block in registry.yaml — preserved verbatim.

### docker

Existing `contracts:` block in registry.yaml — preserved verbatim.

### dpt

Existing `contracts:` block in registry.yaml — preserved verbatim.

### email

Existing `contracts:` block in registry.yaml — preserved verbatim.

### eval

Existing `contracts:` block in registry.yaml — preserved verbatim.

### excel

Existing `contracts:` block in registry.yaml — preserved verbatim.

### figma

Existing `contracts:` block in registry.yaml — preserved verbatim.

### gcp

Existing `contracts:` block in registry.yaml — preserved verbatim.

### gh

Existing `contracts:` block in registry.yaml — preserved verbatim.

### ghidra

Existing `contracts:` block in registry.yaml — preserved verbatim.

### git

Existing `contracts:` block in registry.yaml — preserved verbatim.

### hardware

Existing `contracts:` block in registry.yaml — preserved verbatim.

### harness

Existing `contracts:` block in registry.yaml — preserved verbatim.

### homekit

Existing `contracts:` block in registry.yaml — preserved verbatim.

### ide

Existing `contracts:` block in registry.yaml — preserved verbatim.

### image

Existing `contracts:` block in registry.yaml — preserved verbatim.

### ios

Existing `contracts:` block in registry.yaml — preserved verbatim.

### jupyter

Existing `contracts:` block in registry.yaml — preserved verbatim.

### k8s

Existing `contracts:` block in registry.yaml — preserved verbatim.

### lab

Existing `contracts:` block in registry.yaml — preserved verbatim.

### latex

Existing `contracts:` block in registry.yaml — preserved verbatim.

### learn

Existing `contracts:` block in registry.yaml — preserved verbatim.

### linear

Existing `contracts:` block in registry.yaml — preserved verbatim.

### logs

Existing `contracts:` block in registry.yaml — preserved verbatim.

### macos

Existing `contracts:` block in registry.yaml — preserved verbatim.

### manna

Existing `contracts:` block in registry.yaml — preserved verbatim.

### meet

Existing `contracts:` block in registry.yaml — preserved verbatim.

### meetings

Existing `contracts:` block in registry.yaml — preserved verbatim.

### memory

Existing `contracts:` block in registry.yaml — preserved verbatim.

### metrics

Existing `contracts:` block in registry.yaml — preserved verbatim.

### midi

Existing `contracts:` block in registry.yaml — preserved verbatim.

### models

Existing `contracts:` block in registry.yaml — preserved verbatim.

### namecheap

Existing `contracts:` block in registry.yaml — preserved verbatim.

### network

Existing `contracts:` block in registry.yaml — preserved verbatim.

### notion

Existing `contracts:` block in registry.yaml — preserved verbatim.

### obsidian

Existing `contracts:` block in registry.yaml — preserved verbatim.

### ocr

Existing `contracts:` block in registry.yaml — preserved verbatim.

### okta

Existing `contracts:` block in registry.yaml — preserved verbatim.

### pdf

Existing `contracts:` block in registry.yaml — preserved verbatim.

### pdf2md

Existing `contracts:` block in registry.yaml — preserved verbatim.

### printer

Existing `contracts:` block in registry.yaml — preserved verbatim.

### prompt

Existing `contracts:` block in registry.yaml — preserved verbatim.

### psql

Existing `contracts:` block in registry.yaml — preserved verbatim.

### render

Existing `contracts:` block in registry.yaml — preserved verbatim.

### repl

Existing `contracts:` block in registry.yaml — preserved verbatim.

### resend

Existing `contracts:` block in registry.yaml — preserved verbatim.

### screen

Existing `contracts:` block in registry.yaml — preserved verbatim.

### serial

Existing `contracts:` block in registry.yaml — preserved verbatim.

### sessions

Existing `contracts:` block in registry.yaml — preserved verbatim.

### sheets

Existing `contracts:` block in registry.yaml — preserved verbatim.

### slack

Existing `contracts:` block in registry.yaml — preserved verbatim.

### sms

Existing `contracts:` block in registry.yaml — preserved verbatim.

### spec

Existing `contracts:` block in registry.yaml — preserved verbatim.

### ssh

Existing `contracts:` block in registry.yaml — preserved verbatim.

### supabase

Existing `contracts:` block in registry.yaml — preserved verbatim.

### swarm

Existing `contracts:` block in registry.yaml — preserved verbatim.

### tail

Existing `contracts:` block in registry.yaml — preserved verbatim.

### teams

Existing `contracts:` block in registry.yaml — preserved verbatim.

### transcribe

Existing `contracts:` block in registry.yaml — preserved verbatim.

### tui

Existing `contracts:` block in registry.yaml — preserved verbatim.

### unbrowse

Existing `contracts:` block in registry.yaml — preserved verbatim.

### usb

Existing `contracts:` block in registry.yaml — preserved verbatim.

### vector

Existing `contracts:` block in registry.yaml — preserved verbatim.

### vercel

Existing `contracts:` block in registry.yaml — preserved verbatim.

### video

Existing `contracts:` block in registry.yaml — preserved verbatim.

### vision

Existing `contracts:` block in registry.yaml — preserved verbatim.

### vm

Existing `contracts:` block in registry.yaml — preserved verbatim.

### voice

Existing `contracts:` block in registry.yaml — preserved verbatim.

### wireshark

Existing `contracts:` block in registry.yaml — preserved verbatim.

### zoom

Existing `contracts:` block in registry.yaml — preserved verbatim.

### zpc

Existing `contracts:` block in registry.yaml — preserved verbatim.

