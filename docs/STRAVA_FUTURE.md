# agent-strava: Future Plans

`agent-strava` is a personal, local-first Strava integration. Each person uses
their own Strava app, local profile, OS-backed secrets, cache, and dashboard;
there is no shared agent-do data service.

For first-time connection instructions, see
[STRAVA_SETUP.md](STRAVA_SETUP.md).

## Repository fit

Strava is a distinct fitness-data domain, rather than a new verb on an existing
agent-do family, so it is a top-level tool. Its command surface, credentials,
safety contract, generated tool reference, and focused tests are maintained in
the same way as other registry tools.

## Current slice

The first implementation stores a local profile and activity cache under
`$AGENT_DO_HOME/strava/`, syncs activities on demand, and serves a responsive
localhost dashboard from that cache. The browser does not call Strava itself;
its explicit Sync button asks the local server to refresh the cache.

The current dashboard has 1-week, 1-month, 3-month, and 1-year selectors;
header summaries for distance, moving time, elevation, activity count, and
pace or speed; paginated recent activities; and weekly distance and moving-time
charts for ranges longer than one week. It also supports table-column resizing
and hoverable full-value cells, local-time-zone timestamps, and on-demand
activity summaries with available elevation and heart-rate streams. Detail
charts use smoothed paths, value tooltips, and a zero lower bound for
non-negative metrics. It does not persist those detailed responses after the
browser request completes.

## Product principles

- Keep the source data and generated artifacts on the user's device by default.
- Ask for the smallest Strava OAuth scope needed; start read-only.
- Never put refresh tokens, client secrets, or raw activity data in the repo.
- Make every external AI request explicit, inspectable, and easy to decline.
- Prefer useful training context over a social-feed clone.

## Planned work

### 1. Dynamic local dashboard

`agent-do strava serve` now runs a localhost-only server that exposes a
read-only API over the local cache and serves the dashboard UI. A lightweight
browser client refreshes data after a sync without regenerating an HTML file.

The next dynamic-interface additions could include:

- a custom date range;
- weekly/monthly consistency and training-load summaries;
- user-owned goals and progress; and
- a visible "last synced" state alongside the existing explicit sync action.

Use plain JavaScript first. Introduce React or another UI framework only when
interactive state, views, and component complexity justify the dependency.

### 2. Reliable incremental sync

Evolve `sync` from its initial time-window fetch into an incremental process:

- persist a cursor or latest observed activity/update timestamp;
- upsert activities by Strava activity ID instead of replacing a time window;
- preserve a local sync receipt: started/finished time, record count, and any
  partial failure;
- respect API limits and back off on `429` responses; and
- optionally support webhooks when the user's own Strava app has a reachable,
  secure callback endpoint.

The dashboard must remain usable from the last successful cache when Strava is
offline or authorization expires.

### 3. Optional AI training observations

Add an opt-in `agent-do strava insights` command that sends a deliberately
small, selected aggregate dataset to an AI provider and returns observations,
not medical or coaching prescriptions.

The command should:

- show the selected date range and exact summary payload before sending it;
- default to aggregate metrics and omit route polylines, precise locations,
  activity titles, and raw notes;
- support a chosen provider/model only when that provider's credential is
  configured locally;
- save an attributed local insight receipt containing model, timestamp, input
  summary, and output; and
- clearly frame results as reflective prompts (for example, consistency,
  load changes, or recovery patterns), not health advice.

Potential prompts include: "What changed over the past four weeks?", "Which
training habits are most consistent?", and "What questions should I consider
before setting next month's goal?"

### 4. Shoe mileage

Add a dashboard view that attributes running and walking distance to each
Strava gear item, so a person can see the accumulated mileage for every pair
of shoes. Use the activity's gear association when Strava provides it, show
unassigned distance separately rather than guessing, and keep any user-set
retirement threshold as local profile data. The view should show the shoe
name, total distance in the selected unit, last-used date, and progress toward
the optional threshold; it must not change gear assignments in Strava.

## Decisions to make before implementation

1. Whether goals are simple local values or a richer editable plan format.
2. Whether the local UI needs a durable server process or starts only on demand.
3. Which AI providers to support, and whether local-only models are a priority.
4. Whether webhook support is worth the public callback and operational burden
   for a personal, bring-your-own Strava app.
5. Whether shoe mileage should use Strava's lifetime gear distance, the local
   activity cache, or both when their totals differ.
