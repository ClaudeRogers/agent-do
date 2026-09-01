# agent-do Contracts Inventory

Generated: 2026-05-19T02:06:48Z

Status: Phase A inventory draft. This file is intentionally ignored under `.handoff/` and is for review before registry-wide declaration changes.

## Rules Used

- Tools in registry: 92
- Tools missing contracts today: 90
- Tools with ambiguous/unclassified commands: 78

- Source of truth: current `registry.yaml` loaded through `lib/registry.py`.
- Existing explicit `contracts:` blocks are preserved.
- Obvious command names are classified mechanically. Ambiguous verbs are left in notes for review.
- Stateless tools should omit `connect` unless they own a real session or attachment lifecycle.
- `concurrency` stays independent from contracts.

## 3d

- Description: 3D modeling and rendering control
- Concurrency: `mixed`
- Commands: `view, convert, render, info`
- Current contracts block: `missing`
- Proposed contracts:
  - snapshot: `info`
  - interact: `convert`
- Review needed: unclassified commands `view, render`

## agent

- Description: Control AI coding agent sessions (Claude, OpenCode, Droid, Amp)
- Concurrency: `mixed`
- Commands: `spawn, list, send, snapshot, status, accept, reject, cancel, kill, attach`
- Current contracts block: `missing`
- Proposed contracts:
  - connect: `attach`
  - snapshot: `list, snapshot, status`
  - interact: `spawn, send`
  - verify: `status`
- Review needed: unclassified commands `accept, reject, cancel, kill`

## android

- Description: Control Android Emulator
- Concurrency: `mixed`
- Commands: `tap, screenshot, launch, install, shell`
- Current contracts block: `missing`
- Proposed contracts:
  - review: no obvious contract classification from declared command names
- Review needed: unclassified commands `tap, screenshot, launch, install, shell`

## api

- Description: API testing and interaction
- Concurrency: `read`
- Commands: `get, post, put, delete, test`
- Current contracts block: `missing`
- Proposed contracts:
  - snapshot: `get`
  - interact: `delete`
  - verify: `test`
- Review needed: unclassified commands `post, put`

## audio

- Description: Audio processing
- Concurrency: `mixed`
- Commands: `convert, trim, transcribe`
- Current contracts block: `missing`
- Proposed contracts:
  - interact: `convert, trim, transcribe`

## auth

- Description: Site-level authentication orchestration over encrypted session bundles, browser import, and secure credentials
- Concurrency: `mixed`
- Commands: `init, list, show, status, probe, advance, ensure, save, load, import-browser, clear, validate, instructions`
- Current contracts block: `missing`
- Proposed contracts:
  - connect: `ensure`
  - snapshot: `probe, status`
  - interact: `advance`
  - save: `save`
- Review needed: unclassified commands `init, list, show, load, import-browser, clear, validate, instructions`

## bluetooth

- Description: Bluetooth control
- Concurrency: `mixed`
- Commands: `scan, connect, disconnect`
- Current contracts block: `missing`
- Proposed contracts:
  - connect: `connect`
- Review needed: unclassified commands `scan, disconnect`

## browse

- Description: AI-first headless browser automation with @ref element selection, SSO/MFA login handoff, persistent sessions
- Concurrency: `mixed`
- Commands: `open, snapshot, click, fill, type, press, get, clipboard, wait, login, session, capture, api, auth, tab, viewport, screenshot, vision, agent`
- Current contracts block: `missing`
- Proposed contracts:
  - connect: `open, login`
  - snapshot: `snapshot, screenshot`
  - interact: `click, fill, type, press, viewport`
  - verify: `wait`
  - save: `session save, capture stop`
- Review needed: unclassified commands `get, clipboard, session, capture, api, auth, tab, vision, agent`

## burp

- Description: Burp Suite automation
- Concurrency: `mixed`
- Commands: `launch, proxy, scan, issues`
- Current contracts block: `missing`
- Proposed contracts:
  - review: no obvious contract classification from declared command names
- Review needed: unclassified commands `launch, proxy, scan, issues`

## cad

- Description: CAD file operations
- Concurrency: `mixed`
- Commands: `view, convert, measure, info`
- Current contracts block: `missing`
- Proposed contracts:
  - snapshot: `info`
  - interact: `convert`
- Review needed: unclassified commands `view, measure`

## calendar

- Description: Control calendar
- Concurrency: `mixed`
- Commands: `create, list, delete`
- Current contracts block: `missing`
- Proposed contracts:
  - snapshot: `list`
  - interact: `create, delete`

## ci

- Description: Control CI/CD pipelines
- Concurrency: `write`
- Commands: `trigger, status, logs`
- Current contracts block: `missing`
- Proposed contracts:
  - snapshot: `status, logs`
  - verify: `status, logs`
- Review needed: unclassified commands `trigger`

## clerk

- Description: Clerk authentication platform — users, organizations, sessions, OAuth apps, enterprise SSO, JWT templates, roles
- Concurrency: `mixed`
- Commands: `users, user, user-create, orgs, org, org-members, org-add-member, roles, sessions, oauth-apps, oauth-app-create, enterprise-connections, jwt-templates, snapshot`
- Current contracts block: `missing`
- Proposed contracts:
  - snapshot: `users, snapshot`
- Review needed: unclassified commands `user, user-create, orgs, org, org-members, org-add-member, roles, sessions, oauth-apps, oauth-app-create, enterprise-connections, jwt-templates`

## clipboard

- Description: Cross-app clipboard management
- Concurrency: `read`
- Commands: `copy, paste, history, clear`
- Current contracts block: `missing`
- Proposed contracts:
  - snapshot: `history`
- Review needed: unclassified commands `copy, paste, clear`

## cloud

- Description: Control cloud providers (AWS, GCP, Azure)
- Concurrency: `mixed`
- Commands: `list, deploy, logs`
- Current contracts block: `missing`
- Proposed contracts:
  - snapshot: `list, logs`
  - interact: `deploy`
  - verify: `logs`

## cloudflare

- Description: Cloudflare account management — zones, analytics (GraphQL), DNS, Workers, Pages, R2, security events
- Concurrency: `mixed`
- Commands: `zones, zone, visitors, top-pages, top-countries, requests, bandwidth, threats, analytics, dns, dns-add, dns-del, dns-update, workers, pages, r2-buckets, firewall-events, snapshot`
- Current contracts block: `missing`
- Proposed contracts:
  - snapshot: `zones, visitors, top-pages, top-countries, requests, bandwidth, threats, analytics, dns, workers, pages, r2-buckets, firewall-events, snapshot`
  - interact: `dns-add, dns-del, dns-update`
- Review needed: unclassified commands `zone`

## colab

- Description: Google Colab notebook management
- Concurrency: `mixed`
- Commands: `open, convert, run, new`
- Current contracts block: `missing`
- Proposed contracts:
  - connect: `open`
  - interact: `convert, new`
- Review needed: unclassified commands `run`

## context

- Description: Knowledge library — fetch, index, and serve external reference docs. Complementary to zpc (experience journal).
- Concurrency: `mixed`
- Commands: `search, retrieve, get, list, fetch, crawl, fetch-llms, fetch-repo, refresh, scan-local, scan-skills, sources, add-source, remove-source, cache, annotate, feedback, budget, inject, build, validate, status, stale, versions, serve, maintain, init`
- Current contracts block: `missing`
- Proposed contracts:
  - snapshot: `retrieve, list, get, search, sources, status, stale, versions`
  - interact: `add-source, fetch, fetch-llms, fetch-repo, crawl, refresh, maintain`
  - save: `annotate, feedback`
- Review needed: unclassified commands `scan-local, scan-skills, remove-source, cache, budget, inject, build, validate, serve, init`

## coord

- Description: Project-local agent state and interrupt broker
- Concurrency: `mixed`
- Commands: `touch, whoami, alias, aliases, peers, status, interrupts, focus, claims, claim, release, need, publishes, publish`
- Current contracts block: `missing`
- Proposed contracts:
  - snapshot: `status`
  - interact: `touch, focus, claim, need, publish`
  - verify: `status`
- Review needed: unclassified commands `whoami, alias, aliases, peers, interrupts, claims, release, publishes`

## creds

- Description: Secure credential storage and resolution for agent-do tools
- Concurrency: `read`
- Commands: `store, get, delete, list, check, required, export, platform`
- Current contracts block: `missing`
- Proposed contracts:
  - snapshot: `required, check, list`
  - interact: `delete`
  - save: `store`
- Review needed: unclassified commands `get, export, platform`

## db

- Description: Control database clients
- Concurrency: `mixed`
- Commands: `connect, query, export, tables, describe`
- Current contracts block: `missing`
- Proposed contracts:
  - connect: `connect`
  - snapshot: `query`
  - interact: `query`
- Review needed: unclassified commands `export, tables, describe`

## debug

- Description: Control debuggers
- Concurrency: `read`
- Commands: `break, continue, step, print, backtrace`
- Current contracts block: `missing`
- Proposed contracts:
  - review: no obvious contract classification from declared command names
- Review needed: unclassified commands `break, continue, step, print, backtrace`

## discord

- Description: Control Discord
- Concurrency: `mixed`
- Commands: `send, read, join`
- Current contracts block: `missing`
- Proposed contracts:
  - connect: `join`
  - snapshot: `read`
  - interact: `send`

## dns

- Description: DNS management
- Concurrency: `read`
- Commands: `lookup, update, list`
- Current contracts block: `missing`
- Proposed contracts:
  - snapshot: `list`
  - interact: `update`
- Review needed: unclassified commands `lookup`

## docker

- Description: Control Docker containers
- Concurrency: `write`
- Commands: `ps, logs, exec, shell, start, stop, compose`
- Current contracts block: `missing`
- Proposed contracts:
  - connect: `start`
  - snapshot: `logs`
  - interact: `exec`
  - verify: `logs`
- Review needed: unclassified commands `ps, shell, stop, compose`

## dpt

- Description: Design Perception Tensor - automated design quality scoring
- Concurrency: `read`
- Commands: `scan, score, report, violations, baseline, diff, build`
- Current contracts block: `missing`
- Proposed contracts:
  - snapshot: `diff`
  - verify: `score, violations, baseline, diff`
  - save: `baseline`
- Review needed: unclassified commands `scan, report, build`

## email

- Description: Control email
- Concurrency: `mixed`
- Commands: `send, read, search, snapshot, latest, wait, get, export, code, link, mailboxes, status`
- Current contracts block: `missing`
- Proposed contracts:
  - snapshot: `read, search, snapshot, latest, get, mailboxes, status`
  - interact: `send, export`
  - verify: `wait, status`
  - save: `export`
- Review needed: unclassified commands `code, link`

## eval

- Description: LLM output evaluation and testing
- Concurrency: `read`
- Commands: `run, create, results, compare`
- Current contracts block: `missing`
- Proposed contracts:
  - interact: `create`
- Review needed: unclassified commands `run, results, compare`

## excel

- Description: AI-first Excel CLI for workbook automation
- Concurrency: `mixed`
- Commands: `open, new, save, snapshot, get, set, fill, formula, sheets, sheet, export`
- Current contracts block: `missing`
- Proposed contracts:
  - connect: `open`
  - snapshot: `snapshot, get`
  - interact: `new, set, fill, formula, sheet, export`
  - save: `save, export`
- Review needed: unclassified commands `sheets`

## figma

- Description: Control Figma
- Concurrency: `read`
- Commands: `export, inspect, list`
- Current contracts block: `missing`
- Proposed contracts:
  - snapshot: `inspect, list`
  - interact: `export`
  - save: `export`

## gcp

- Description: Google Cloud Platform management — REST API for projects, APIs, secrets, service accounts + Console automation for OAuth credentials
- Concurrency: `mixed`
- Commands: `auth status, auth token, projects, project show, apis, api-enable, api-disable, service-accounts, sa-create, sa-key-create, sa-key-list, secrets, secret-get, secret-set, secret-del, oauth-setup, oauth-create, oauth-list, snapshot`
- Current contracts block: `missing`
- Proposed contracts:
  - connect: `auth status, auth token`
  - snapshot: `projects, snapshot`
  - interact: `api-enable, api-disable, sa-create, sa-key-create, secret-set, secret-del, oauth-setup, oauth-create`
- Review needed: unclassified commands `project show, apis, service-accounts, sa-key-list, secrets, secret-get, oauth-list`

## gh

- Description: GitHub repository, pull request, review, and merge work-state across accessible repos
- Concurrency: `mixed`
- Commands: `whoami, repos, inbox, awaiting, prs, pr, diff, threads, checks, review, audit, approve, request-changes, comment, close, reopen, checkout, edit, update-branch, merge, ready, draft`
- Current contracts block: `missing`
- Proposed contracts:
  - snapshot: `inbox, awaiting, prs, pr, diff, threads, checks`
  - interact: `review, approve, request-changes, comment, merge, ready, draft, checkout, edit, update-branch`
  - verify: `audit`
- Review needed: unclassified commands `whoami, repos, close, reopen`

## ghidra

- Description: Ghidra reverse engineering automation
- Concurrency: `read`
- Commands: `analyze, decompile, functions, strings`
- Current contracts block: `missing`
- Proposed contracts:
  - review: no obvious contract classification from declared command names
- Review needed: unclassified commands `analyze, decompile, functions, strings`

## git

- Description: Enhanced git operations
- Concurrency: `mixed`
- Commands: `commit, branch, diff, log, stash`
- Current contracts block: `missing`
- Proposed contracts:
  - snapshot: `diff`
  - verify: `diff`
- Review needed: unclassified commands `commit, branch, log, stash`

## hardware

- Description: Unified hardware device control across serial, bluetooth, USB, printers, and MIDI
- Concurrency: `mixed`
- Commands: `snapshot, serial, bluetooth, usb, printer, midi`
- Current contracts block: `missing`
- Proposed contracts:
  - snapshot: `snapshot`
- Review needed: unclassified commands `serial, bluetooth, usb, printer, midi`

## harness

- Description: Observable agent-do harness inventory, evidence, and change-manifest front door
- Concurrency: `read`
- Commands: `inspect, nudges, evidence, manifest`
- Current contracts block: `missing`
- Proposed contracts:
  - snapshot: `inspect, nudges, evidence`
  - interact: `manifest`
  - verify: `manifest verify`

## homekit

- Description: HomeKit/smart home control
- Concurrency: `mixed`
- Commands: `list, set, scene`
- Current contracts block: `missing`
- Proposed contracts:
  - snapshot: `list`
  - interact: `set`
- Review needed: unclassified commands `scene`

## ide

- Description: Control VS Code/Cursor editor
- Concurrency: `read`
- Commands: `open, run, goto, search, terminal`
- Current contracts block: `missing`
- Proposed contracts:
  - connect: `open`
  - snapshot: `search`
- Review needed: unclassified commands `run, goto, terminal`

## image

- Description: Image processing
- Concurrency: `mixed`
- Commands: `resize, crop, convert`
- Current contracts block: `missing`
- Proposed contracts:
  - interact: `convert`
- Review needed: unclassified commands `resize, crop`

## ios

- Description: Control iOS Simulator
- Concurrency: `mixed`
- Commands: `tap, screenshot, launch, tree, swipe, type, boot, shutdown, list, status`
- Current contracts block: `missing`
- Proposed contracts:
  - connect: `boot`
  - snapshot: `list, status`
  - interact: `type`
  - verify: `status`
- Review needed: unclassified commands `tap, screenshot, launch, tree, swipe, shutdown`

## jupyter

- Description: Control Jupyter notebooks
- Concurrency: `mixed`
- Commands: `run, create, export, kernel`
- Current contracts block: `missing`
- Proposed contracts:
  - interact: `create, export`
  - save: `export`
- Review needed: unclassified commands `run, kernel`

## k8s

- Description: Control Kubernetes clusters
- Concurrency: `write`
- Commands: `pods, logs, exec, apply, port-forward`
- Current contracts block: `missing`
- Proposed contracts:
  - snapshot: `logs`
  - interact: `exec`
  - verify: `logs`
- Review needed: unclassified commands `pods, apply, port-forward`

## lab

- Description: JupyterLab management
- Concurrency: `mixed`
- Commands: `start, stop, open, extensions`
- Current contracts block: `missing`
- Proposed contracts:
  - connect: `start, open`
  - snapshot: `extensions`
- Review needed: unclassified commands `stop`

## latex

- Description: LaTeX document compilation
- Concurrency: `write`
- Commands: `compile, watch, preview, template`
- Current contracts block: `missing`
- Proposed contracts:
  - review: no obvious contract classification from declared command names
- Review needed: unclassified commands `compile, watch, preview, template`

## learn

- Description: Learning and pattern improvement
- Concurrency: `write`
- Commands: `correct, feedback, patterns, stats`
- Current contracts block: `missing`
- Proposed contracts:
  - snapshot: `stats`
  - save: `feedback`
- Review needed: unclassified commands `correct, patterns`

## linear

- Description: Control Linear
- Concurrency: `mixed`
- Commands: `create, update, list`
- Current contracts block: `missing`
- Proposed contracts:
  - snapshot: `list`
  - interact: `create, update`

## logs

- Description: Control log aggregation
- Concurrency: `read`
- Commands: `search, tail, filter`
- Current contracts block: `missing`
- Proposed contracts:
  - snapshot: `search`
- Review needed: unclassified commands `tail, filter`

## macos

- Description: Control native macOS desktop applications via accessibility APIs
- Concurrency: `mixed`
- Commands: `click, type, tree, find, focus, menu`
- Current contracts block: `missing`
- Proposed contracts:
  - snapshot: `find`
  - interact: `click, type, focus`
- Review needed: unclassified commands `tree, menu`

## manna

- Description: Git-backed issue tracking and context management for AI agents
- Concurrency: `write`
- Commands: `init, create, list, show, update, delete, context`
- Current contracts block: `missing`
- Proposed contracts:
  - connect: `init`
  - snapshot: `list, show, context`
  - interact: `create, update, delete`

## meet

- Description: Google Meet control
- Concurrency: `mixed`
- Commands: `new, join, mute, video`
- Current contracts block: `missing`
- Proposed contracts:
  - connect: `join`
  - interact: `new`
- Review needed: unclassified commands `mute, video`

## meetings

- Description: Unified enterprise meeting orchestration across Zoom, Google Meet, and Microsoft Teams
- Concurrency: `mixed`
- Commands: `snapshot, providers, active, join, new, schedule, mute, video, share, chat, end, zoom, meet, teams`
- Current contracts block: `missing`
- Proposed contracts:
  - connect: `join`
  - snapshot: `snapshot`
  - interact: `new`
- Review needed: unclassified commands `providers, active, schedule, mute, video, share, chat, end, zoom, meet, teams`

## memory

- Description: Persistent memory and context
- Concurrency: `mixed`
- Commands: `store, recall, search, list`
- Current contracts block: `missing`
- Proposed contracts:
  - snapshot: `search, list`
  - save: `store`
- Review needed: unclassified commands `recall`

## metrics

- Description: Control metrics/monitoring
- Concurrency: `read`
- Commands: `query, dashboard, alert`
- Current contracts block: `missing`
- Proposed contracts:
  - snapshot: `query`
  - interact: `query`
- Review needed: unclassified commands `dashboard, alert`

## midi

- Description: MIDI control
- Concurrency: `mixed`
- Commands: `list, send, play`
- Current contracts block: `missing`
- Proposed contracts:
  - snapshot: `list`
  - interact: `send`
- Review needed: unclassified commands `play`

## namecheap

- Description: Namecheap domain and DNS management — domains, DNS records (safe upsert with exact verification), nameservers, SSL, availability
- Concurrency: `write`
- Commands: `domains, domain, domain-check, domain-renew, dns, dns-add, dns-update, dns-verify, dns-del, nameservers, nameservers-set, ssl-list, snapshot`
- Current contracts block: `missing`
- Proposed contracts:
  - snapshot: `dns, snapshot`
  - interact: `dns-add, dns-update, dns-del`
  - verify: `dns-verify`
- Review needed: unclassified commands `domains, domain, domain-check, domain-renew, nameservers, nameservers-set, ssl-list`

## network

- Description: Network diagnostics
- Concurrency: `read`
- Commands: `ping, trace, scan, whois`
- Current contracts block: `missing`
- Proposed contracts:
  - review: no obvious contract classification from declared command names
- Review needed: unclassified commands `ping, trace, scan, whois`

## notion

- Description: Control Notion
- Concurrency: `mixed`
- Commands: `create, update, query`
- Current contracts block: `missing`
- Proposed contracts:
  - snapshot: `query`
  - interact: `create, update, query`

## obsidian

- Description: Obsidian vault integration with a local SQLite vault index plus official Obsidian CLI fallback
- Concurrency: `mixed`
- Commands: `doctor, snapshot, refresh, embed, read, create, append, search, context, chat, connections, query, relate, summarize, save, save-group, daily, weekly, period, prop, tasks, tags, backlinks, graph, templates, audit, move, delete, eval, dev, plugin`
- Current contracts block: `present`
- Proposed contracts:
  - connect: `doctor`
  - snapshot: `snapshot, read, search, embed status, context build, connections, query, relate, summarize, tasks list, tasks next, tags, backlinks, graph orphans, graph broken-links, graph clusters, graph cluster, graph tag-usage, daily read, daily list, weekly read, weekly list, period read, prop get, prop list, templates list, templates show`
  - interact: `refresh, embed refresh, chat, create, append, move, delete, prop set, prop batch, tasks add, tasks complete, tasks update, tags rename, tags merge, daily append, weekly append, templates apply, templates register, audit fix`
  - verify: `doctor, audit`
  - save: `save, save-group`
- Review needed: unclassified commands `embed, context, daily, weekly, period, prop, tasks, graph, templates, eval, dev, plugin`

## ocr

- Description: Screen text extraction
- Concurrency: `read`
- Commands: `screen, region, file, find`
- Current contracts block: `missing`
- Proposed contracts:
  - snapshot: `find`
- Review needed: unclassified commands `screen, region, file`

## okta

- Description: Okta tenant management — applications (OIDC/SAML), SSO configuration, users, groups, authorization servers, system logs
- Concurrency: `mixed`
- Commands: `apps, app, app-create-oidc, app-create-saml, app-update, app-creds, app-creds-rotate, app-assign-group, users, groups, auth-servers, logs, trusted-origins, snapshot`
- Current contracts block: `missing`
- Proposed contracts:
  - snapshot: `users, groups, logs, snapshot`
  - verify: `logs`
- Review needed: unclassified commands `apps, app, app-create-oidc, app-create-saml, app-update, app-creds, app-creds-rotate, app-assign-group, auth-servers, trusted-origins`

## pdf

- Description: Control PDF operations
- Concurrency: `mixed`
- Commands: `read, merge, split, extract`
- Current contracts block: `missing`
- Proposed contracts:
  - snapshot: `read`
  - interact: `merge, extract`
- Review needed: unclassified commands `split`

## pdf2md

- Description: Convert PDF files to Markdown
- Concurrency: `read`
- Commands: `convert, batch, snapshot`
- Current contracts block: `missing`
- Proposed contracts:
  - snapshot: `snapshot`
  - interact: `convert`
- Review needed: unclassified commands `batch`

## printer

- Description: Printer control
- Concurrency: `write`
- Commands: `list, print, status`
- Current contracts block: `missing`
- Proposed contracts:
  - snapshot: `list, status`
  - verify: `status`
- Review needed: unclassified commands `print`

## prompt

- Description: Prompt management and templating
- Concurrency: `read`
- Commands: `save, load, run, list`
- Current contracts block: `missing`
- Proposed contracts:
  - snapshot: `list`
  - save: `save`
- Review needed: unclassified commands `load, run`

## render

- Description: Control Render.com services, deploys, databases, and env vars
- Concurrency: `write`
- Commands: `services, show, deploy, deploys, logs, restart, suspend, resume, scale, env, env-set, env-del, db, domains, metrics, projects, snapshot`
- Current contracts block: `missing`
- Proposed contracts:
  - snapshot: `services, deploys, logs, env`
  - interact: `deploy, restart, env-set`
  - verify: `logs`
- Review needed: unclassified commands `show, suspend, resume, scale, env-del, db, domains, metrics, projects, snapshot`

## repl

- Description: Control interactive REPLs (Python, Node, psql, etc.)
- Concurrency: `mixed`
- Commands: `spawn, send, read, list, kill`
- Current contracts block: `missing`
- Proposed contracts:
  - snapshot: `read, list`
  - interact: `spawn, send`
- Review needed: unclassified commands `kill`

## resend

- Description: Resend domain management and DNS verification — exact records, verification state, and public DNS checks
- Concurrency: `read`
- Commands: `domains, domain, add, records, status, verify, dns-check`
- Current contracts block: `missing`
- Proposed contracts:
  - snapshot: `status`
  - interact: `add`
  - verify: `status, verify`
- Review needed: unclassified commands `domains, domain, records, dns-check`

## screen

- Description: Vision-based screen perception and control (macOS)
- Concurrency: `read`
- Commands: `snapshot, displays, elements, find, click, type, press, cursor, scroll`
- Current contracts block: `missing`
- Proposed contracts:
  - snapshot: `snapshot, find`
  - interact: `click, type, press`
- Review needed: unclassified commands `displays, elements, cursor, scroll`

## serial

- Description: Serial port communication
- Concurrency: `mixed`
- Commands: `list, send, monitor`
- Current contracts block: `missing`
- Proposed contracts:
  - snapshot: `list`
  - interact: `send`
- Review needed: unclassified commands `monitor`

## sessions

- Description: Search and retrieve AI coding session history
- Concurrency: `read`
- Commands: `search, list, show, context, projects, stats, snapshot, grep, turns`
- Current contracts block: `missing`
- Proposed contracts:
  - snapshot: `search, list, show, context, projects, stats, snapshot`
- Review needed: unclassified commands `grep, turns`

## sheets

- Description: Control Google Sheets
- Concurrency: `mixed`
- Commands: `read, write, create`
- Current contracts block: `missing`
- Proposed contracts:
  - snapshot: `read`
  - interact: `write, create`

## slack

- Description: Control Slack
- Concurrency: `mixed`
- Commands: `send, read, react, upload`
- Current contracts block: `missing`
- Proposed contracts:
  - snapshot: `read`
  - interact: `send, react, upload`

## sms

- Description: SMS messaging
- Concurrency: `write`
- Commands: `send, list, search, snapshot, latest, wait, code, link`
- Current contracts block: `missing`
- Proposed contracts:
  - snapshot: `list, search, snapshot, latest`
  - interact: `send`
  - verify: `wait`
- Review needed: unclassified commands `code, link`

## spec

- Description: Repo-local specifications and change artifacts for intended behavior, change deltas, and archive readiness
- Concurrency: `mixed`
- Commands: `init, list, show, new, status`
- Current contracts block: `missing`
- Proposed contracts:
  - connect: `init`
  - snapshot: `list, show, status`
  - interact: `new`
  - verify: `status`

## ssh

- Description: Control remote server sessions
- Concurrency: `write`
- Commands: `connect, exec, upload, download, list`
- Current contracts block: `missing`
- Proposed contracts:
  - connect: `connect`
  - snapshot: `list`
  - interact: `exec, upload`
- Review needed: unclassified commands `download`

## supabase

- Description: Supabase project management + data access (REST API, SQL via Management API, and SQL via agent-db)
- Concurrency: `write`
- Commands: `projects, show, pause, restore, health, api-keys, secrets, secret-set, secret-del, functions, function-show, domains, types, orgs, regions, postgrest, snapshot, rest, sql, db-connect, db-status, query, tables, describe, sample`
- Current contracts block: `missing`
- Proposed contracts:
  - snapshot: `projects, tables, query`
  - interact: `query`
- Review needed: unclassified commands `show, pause, restore, health, api-keys, secrets, secret-set, secret-del, functions, function-show, domains, types, orgs, regions, postgrest, snapshot, rest, sql, db-connect, db-status, describe, sample`

## swarm

- Description: Multi-agent orchestration
- Concurrency: `write`
- Commands: `spawn, parallel, pipeline, status`
- Current contracts block: `missing`
- Proposed contracts:
  - snapshot: `status`
  - interact: `spawn`
  - verify: `status`
- Review needed: unclassified commands `parallel, pipeline`

## tail

- Description: Wrap dev commands, capture output to log files for AI agents
- Concurrency: `read`
- Commands: `run, start, stop, read, follow, grep, errors, list, sessions, prune, snapshot`
- Current contracts block: `missing`
- Proposed contracts:
  - connect: `start`
  - snapshot: `read, list, snapshot`
- Review needed: unclassified commands `run, stop, follow, grep, errors, sessions, prune`

## teams

- Description: Microsoft Teams control
- Concurrency: `mixed`
- Commands: `join, new, chat, mute`
- Current contracts block: `missing`
- Proposed contracts:
  - connect: `join`
  - interact: `new`
- Review needed: unclassified commands `chat, mute`

## transcribe

- Description: Source-to-transcript ingestion pipeline (YouTube URLs, authenticated downloads, Whisper API + local Whisper + caption fallbacks, batch, cost preflight, structured JSON)
- Concurrency: `mixed`
- Commands: `doctor, snapshot, cost, transcribe`
- Current contracts block: `declared`
- Proposed contracts:
  - connect: `doctor`
  - snapshot: `snapshot, cost`
  - interact: `transcribe`
  - verify: `doctor, cost`
  - save: `transcribe`

## tui

- Description: Control any terminal/TUI application via tmux
- Concurrency: `mixed`
- Commands: `spawn, snapshot, send, type, wait, kill, list`
- Current contracts block: `missing`
- Proposed contracts:
  - snapshot: `snapshot, list`
  - interact: `spawn, send, type`
  - verify: `wait`
- Review needed: unclassified commands `kill`

## unbrowse

- Description: Standalone API traffic capture → reusable curl-based skills. For SSO/MFA → headless handoff, use browse login instead.
- Concurrency: `mixed`
- Commands: `capture, stop, status, close, list, show, replay, test, delete`
- Current contracts block: `missing`
- Proposed contracts:
  - snapshot: `status, list, show`
  - interact: `delete`
  - verify: `status, test`
- Review needed: unclassified commands `capture, stop, close, replay`

## usb

- Description: USB device management
- Concurrency: `read`
- Commands: `list, mount, eject`
- Current contracts block: `missing`
- Proposed contracts:
  - snapshot: `list`
- Review needed: unclassified commands `mount, eject`

## vector

- Description: Operate Versova Vector portfolio command center
- Concurrency: `write`
- Commands: `today, inbox, ls, show, snapshot, decide, work, support, ask, link, open, sync, bind, members, feed, intake`
- Current contracts block: `missing`
- Proposed contracts:
  - connect: `open, bind`
  - snapshot: `inbox, show, snapshot`
  - interact: `decide, sync`
  - save: `decide`
- Review needed: unclassified commands `today, ls, work, support, ask, link, members, feed, intake`

## vercel

- Description: Control Vercel projects, deployments, domains, and env vars
- Concurrency: `write`
- Commands: `projects, show, deployments, deploy, inspect, logs, cancel, promote, env, env-set, env-del, domains, teams, snapshot`
- Current contracts block: `missing`
- Proposed contracts:
  - snapshot: `projects, deployments, logs, env, domains`
  - interact: `deploy, env-set`
  - verify: `logs`
- Review needed: unclassified commands `show, inspect, cancel, promote, env-del, teams, snapshot`

## video

- Description: Video processing
- Concurrency: `mixed`
- Commands: `trim, merge, extract`
- Current contracts block: `missing`
- Proposed contracts:
  - interact: `trim, merge, extract`

## vision

- Description: AI-first visual perception with object detection, OCR, and face detection
- Concurrency: `read`
- Commands: `source, snapshot, detect, count, ocr, faces, status`
- Current contracts block: `missing`
- Proposed contracts:
  - snapshot: `source, snapshot, count, status`
  - verify: `status`
- Review needed: unclassified commands `detect, ocr, faces`

## vm

- Description: Control virtual machines
- Concurrency: `write`
- Commands: `start, stop, snapshot, list`
- Current contracts block: `missing`
- Proposed contracts:
  - connect: `start`
  - snapshot: `snapshot, list`
- Review needed: unclassified commands `stop`

## voice

- Description: Voice synthesis and recognition
- Concurrency: `write`
- Commands: `speak, listen, record, transcribe`
- Current contracts block: `missing`
- Proposed contracts:
  - interact: `record, transcribe`
  - save: `transcribe`
- Review needed: unclassified commands `speak, listen`

## wireshark

- Description: Network packet capture and analysis
- Concurrency: `read`
- Commands: `capture, read, filter, stats`
- Current contracts block: `missing`
- Proposed contracts:
  - snapshot: `read, stats`
- Review needed: unclassified commands `capture, filter`

## zoom

- Description: Zoom meeting control
- Concurrency: `mixed`
- Commands: `join, start, mute, video, share`
- Current contracts block: `missing`
- Proposed contracts:
  - connect: `join, start`
- Review needed: unclassified commands `mute, video, share`

## zpc

- Description: Experience journal — structured lessons, decisions, patterns per project. Complementary to context (knowledge library).
- Concurrency: `mixed`
- Commands: `learn, decide, decide-batch, harvest, query, patterns, review, promote, inject, init, status, checkpoint, profile`
- Current contracts block: `missing`
- Proposed contracts:
  - connect: `init`
  - snapshot: `query, status, profile`
  - interact: `learn, decide, harvest, query`
  - verify: `status`
  - save: `learn, decide`
- Review needed: unclassified commands `decide-batch, patterns, review, promote, inject, checkpoint`

## Immediate Findings

- Only 1 of 92 tools currently declare contracts.
- `transcribe` exists in the registry and tests, but does not yet declare contracts. It should be the first proof that the new-tool rule needs enforcement.
- `audio` and `transcribe` should remain separate contracts: `audio` is low-level media operations; `transcribe` is source-to-transcript ingestion with auth, cost, cache, and saved outputs.
- Several commands are intentionally multi-beat, especially `query`, `logs`, `status`, `transcribe`, and `manifest`. The registry schema needs to allow duplicate verb membership with notes or disambiguators.
