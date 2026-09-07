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
browser request completes. The Gear page shows Strava's lifetime distance for
each synced equipment item, opens its locally cached activity history, and can
export a workbook with a gear summary followed by one activity sheet per item.
Workbook durations use MM:SS below an hour and HH:MM:SS otherwise; calories use
Strava's value when available and otherwise a kilojoule-derived estimate.

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

### 3. V2 plan: private AI guidance and repeat-route trends

V2 adds an opt-in `agent-do strava insights` experience in both the CLI and
local dashboard. It should turn a selected period (for example, 1 week, 1
month, 3 months, or a custom range) into useful training observations while
keeping route geometry and other sensitive raw data on the user's device.
Insights are reflective training prompts, not medical advice or authoritative
coaching prescriptions.

Build it in these independently shippable segments:

1. **Define the local insight contract.** Add a versioned, deterministic
   summary builder for a date range and activity filter: weekly volume,
   frequency, moving time, elevation, pace or speed, and optional heart-rate
   and power trends. Define minimum-data and comparability rules up front, so
   the result says when there is insufficient evidence rather than guessing.
   Add fixtures and unit tests for empty, sparse, mixed-sport, and improving
   datasets.

2. **Derive private repeat-route groups.** Decode each activity's local
   summary polyline and create a stable local route-group identifier from
   sport type, direction, distance, and path-overlap thresholds. Store only
   the derived group and comparison metrics needed for insight history; retain
   exact polylines only in the existing local activity cache. Require enough
   matching activities before reporting a trend, and compare like-for-like
   distance/elevation profiles. Use Strava segment efforts as an optional
   second signal when available, not as a requirement.

3. **Expose local analysis before any AI call.** Add
   `agent-do strava insights --days N --activity TYPE --preview` to print the
   selected time range, aggregate metrics, repeat-route findings, and the
   exact redacted payload. The default payload must omit activity names,
   notes, photos, raw streams, precise locations, route polylines, and OAuth
   material. The user explicitly chooses whether to continue after preview.

4. **Add provider adapters and credential handling.** Support a configured
   OpenAI API or Anthropic API provider behind a small provider interface;
   store API keys in OS secure storage and never in profile JSON, receipts, or
   command output. Send only the reviewed payload and a fixed prompt that asks
   for evidence-qualified observations about consistency, load, pace/speed,
   recovery questions, and comparable repeat-route performance. Treat API
   failures, limits, and unavailable credentials as clear local errors.

5. **Persist transparent local receipts.** Save a permission-safe receipt
   containing the schema version, provider/model, timestamp, selected filters,
   redacted input summary, output, and any uncertainty/disclaimer markers.
   Provide `insights history` and `insights show` commands without requiring a
   new provider call. Never persist the provider API key or raw route geometry
   in a receipt.

6. **Add the dashboard flow.** Put an **AI guidance** action beside the
   existing range and activity selectors. Show the local preview and privacy
   notice first, require an explicit **Generate guidance** confirmation, then
   render the returned observation with its evidence and receipt timestamp.
   Keep the server localhost-only and make prior local receipts viewable from
   the UI.

7. **Harden and document the feature.** Cover provider calls with mocked
   transport tests; cover route grouping against GPS jitter, reversed routes,
   partial overlaps, and mixed activity types; update registry contracts,
   command help, `docs/TOOLS.md`, and `STRAVA_SETUP.md`. Validate that preview
   and receipt output contain no prohibited raw fields, and manually verify
   both the CLI and dashboard consent paths.

Example observations the feature may produce, when the data supports them:

- "You completed this local route group five times; median moving pace improved
  from 9:42/mi to 9:18/mi on comparable efforts."
- "Your weekly running time has been more consistent over the last month, but
  the recent volume increase is large enough to make recovery worth watching."
- "There is not enough comparable route or heart-rate data to support a claim
  about speed or fitness change."

## Decisions to make before implementation

1. Whether goals are simple local values or a richer editable plan format.
2. Whether the local UI needs a durable server process or starts only on demand.
3. Which AI providers to support, and whether local-only models are a priority.
4. Whether webhook support is worth the public callback and operational burden
   for a personal, bring-your-own Strava app.
5. Whether shoe mileage should use Strava's lifetime gear distance, the local
   activity cache, or both when their totals differ.
