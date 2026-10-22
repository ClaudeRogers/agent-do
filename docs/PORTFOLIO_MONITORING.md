# Portfolio monitoring (milestone 3)

`agent-do security monitor` scans a saved portfolio, compares compatible evidence,
and writes a digest of **new**, **ongoing**, **resolved**, and **unverified** issues.
It supports GitHub repository links and trusted local projects, including explicit
Maven/Gradle resolution. It exports a cron job for recurring execution on your
scan host; it never installs a scheduler automatically. Notifications are opt-in.

Use the [combined milestone 3/4 test checklist](SECURITY_MILESTONE_3_4_TESTING.md)
for automated and host acceptance checks.

## Start with your repository list

```bash
agent-do security monitor init --config ~/team-security.json \
  --repos-file ~/team-repos.txt --interval-hours 24 --json
agent-do security monitor run --config ~/team-security.json --json
agent-do security monitor report --config ~/team-security.json --json
```

Initialization copies the normalized repository/ref entries from your existing
[text/JSON repository list](REPOSITORY_LIST_SCANNING.md). It does not scan or
execute project code. The configuration is a private local JSON file; an existing
file is never overwritten. Edit its `targets` array when your portfolio changes;
later changes to the original repository-list file are not imported automatically.

## Monitor your local Spring Boot project

```bash
agent-do security monitor init --config ~/bff-security.json \
  --path ~/workspace/map-managed-bff --resolve maven
agent-do security monitor run --config ~/bff-security.json --allow-builds \
  --cvss-min 7 --include-unscored --json
agent-do security monitor report --config ~/bff-security.json --severity critical,high
```

`--allow-builds` is mandatory on each execution that runs configured local build
resolution. Without it, that target is incomplete, no build runs, other targets
continue, and earlier findings cannot be resolved. Exporting a scheduled build
also requires the flag so the reviewable job makes that authorization explicit.
Use only trusted local projects. Build wrappers/extensions can execute project
code, contact configured repositories and write build files/caches.

The existing [setup guide](SECURITY_SCANNING.md) covers OSV-Scanner v2, `gh` access,
optional CVSS scoring and read-only file scans. GitHub monitoring uses isolated
file snapshots; it does not remotely execute Maven/Gradle.

## Create a mixed portfolio from the CLI

`--runtime-inventory` can accompany either one local `--path` or a GitHub
`--repos-file`. Path and repos-file remain mutually exclusive; at least one
source/inventory input is required. For example:

```bash
agent-do security monitor init --config ~/mixed-security.json \
  --path ~/workspace/map-managed-bff --resolve maven \
  --runtime-inventory ~/runtime-inventory.json --json
agent-do security monitor run --config ~/mixed-security.json --allow-builds --json
agent-do security monitor init --config ~/team-and-runtimes.json \
  --repos-file ~/team-repos.txt --runtime-inventory ~/runtime-inventory.json --json
```

A single init call accepts one local path; additional heterogeneous targets can
be added to the generated configuration's `targets` array. Preserve its
`schema_version: 1` and generated 32-character hexadecimal `monitor_id`. A
handwritten file missing those fields is invalid regardless of whether its
targets are mixed; the data model accepts mixed targets. Do not change the ID
when editing an existing monitor if you want to preserve its history.

## Configuration and scope

Keep the generated `schema_version: 1` and `monitor_id` (a unique 32-character
identifier). Reusing the same ID reuses the same history and lock; initialize a
new file if you want an independent monitor. `interval_hours` is a positive whole
number (default 24). Relative target/settings paths resolve beside the config.

A `targets` array can mix entries such as:

```json
[
  {"repo": "my-team/backend", "ref": "main"},
  {"repo": "my-team/frontend"},
  {
    "path": "/path/to/offer-service",
    "resolve": "maven",
    "options": {
      "maven_settings": "/path/to/settings.xml",
      "maven_profile": ["prod"],
      "build_property": ["example=production"]
    }
  },
  {
    "path": "/path/to/gradle-project",
    "resolve": "gradle",
    "options": {"gradle_configuration": ["runtimeClasspath", "testRuntimeClasspath"]}
  }
]
```

Each source entry accepts exactly one `repo` or `path`. A runtime entry accepts
only `runtime_inventory`, pointing to the versioned inventory JSON described in
[runtime assessment](RUNTIME_ASSESSMENT.md). Initialize a runtime-only portfolio
with `monitor init --config PATH --runtime-inventory PATH`. Use
`monitor run --runtime-limit N` for the per-component NVD record bound (default
1000). Runtime issue IDs remain distinct; changed membership/deployment identity
keeps earlier findings unverified.

For source entries, GitHub `ref` is optional and
otherwise selects the default branch. `resolve` is local-only. Local `options`
accept `maven`, `gradle`, `maven_settings` executable/settings strings and
`maven_profile`, `gradle_configuration`, `build_property` arrays of strings.
Normal scan validation rejects incompatible options and reserved properties.
Unknown fields and duplicate repository/ref or path identities are rejected
before scanning. Credentials belong in normal build/gh credential mechanisms,
not repository URLs or properties. Property values are fingerprinted rather than
copied into digests or state. Explicit settings contents are hashed for scope
comparison, not stored in reports.

Repository/ref and local path identities are tracked independently. Comparisons
require the same configuration/build options, explicit settings content,
scanner version, build version and effective branch. A version/scope change
creates a separate baseline. Existing active issues in other scopes, or removed
portfolio targets, remain **unverified**, never silently resolved. Older scope
ledgers remain retained for audit and can be compared if that scope returns.

This compares observed dependencies under the configured build environment;
it does not independently enumerate every implicitly activated profile or prove
that ambient credentials/environment stayed identical. Use consistent build
settings and environment when evaluating the same scope over time. Runtime/JDK,
OS, container and deployed-artifact evidence can now be supplied through
[runtime inventory targets](RUNTIME_ASSESSMENT.md). This does not automatically
collect live runtime or deployment evidence.

## What the changes mean

| Category | Meaning |
| --- | --- |
| `new` | First detected in this monitor/scope, or reappeared after resolution (`reopened: true`). It does not mean newly announced. |
| `ongoing` | Present in the current assessment and previously active in the same scope. A changed vulnerable package version remains ongoing. |
| `resolved` | No longer detected in a **complete compatible source assessment**. It does not prove deployment remediation or exploitability. |
| `unverified` | Earlier evidence retained because the current scan failed, scope changed, or the target was not scanned. |

CVE/GHSA aliases are matched transitively. Multiple versions/occurrences of the
same advisory/package within a target form one tracked issue; different package
names/ecosystems or repositories remain separate. Issue IDs and first-detected
UTC timestamps persist through version changes and reopening. Advisory publication
and modification dates remain on the original findings and are never used as
first detection. Positive evidence from an incomplete scan is retained; absence
from that scan cannot resolve earlier findings.

The digest has two distinct status fields:

- `status`: completeness of the current requested assessment (and explicit
  notification delivery, if requested). Exit 0 can include vulnerabilities;
  exit 1 means incomplete; exit 2 means invalid configuration/state/input.
- `comparison_status`: `partial` when prior issues remain unverified, otherwise
  `complete`. A current scan can complete while older scopes are not comparable.
  Inspect both fields and the counts; exit 0 is not an all-clear signal.

## Evidence, filtering and failure recovery

Each run saves an unfiltered schema-version-1 source report in the usual
`$AGENT_DO_HOME/security/reports` directory and a digest under
`$AGENT_DO_HOME/security/monitors/<monitor_id>/digests`. Default home is
`~/.agent-do`. State and its latest embedded digest are committed together by
atomic replacement under a per-monitor nonblocking POSIX lock. Concurrent runs
of the same monitor are rejected; malformed state is not silently reset.
A state-write failure cannot advance the baseline. The raw assessment remains
available. If a crash interrupts the separate historical digest-file write,
`monitor report` can still recover the latest digest embedded in committed state.

```bash
agent-do security monitor report --config ~/team-security.json --cvss-min 9 --json
agent-do security monitor report --config ~/team-security.json \
  --file /path/to/older-digest.json --severity critical,high --json
```

Shared score, severity, package, CVE, date, fix and exploitation filters apply to
display only; saved evidence/history and `counts` remain unfiltered.
`shown_counts` reports the filtered view. Resolved/unverified filters use their
last-seen evidence. `--known-exploited` needs known KEV status in that evidence;
use `--kev` on runs to collect enrichment. `--target` is a curated advisory-search
option and is not a monitor selector. `security report --latest` can read the raw
aggregate source report, but `monitor report --config ...` selects this portfolio's
latest committed digest rather than a global report from another project.

## Recurring execution on your machine

Generate the job **on the machine that will run it**:

```bash
agent-do security monitor schedule --config ~/team-security.json
agent-do security monitor schedule --config ~/bff-security.json --allow-builds --json
```

Review the emitted `cron` line and install it using `crontab -e`. No cron entry
is installed by the plugin. It checks hourly and invokes `monitor run --due`;
actual scans occur only after `interval_hours` since the last committed attempt.
A failed attempt also advances the due interval to avoid tight retry loops.
To retry immediately, run without `--due`:

```bash
agent-do security monitor run --config ~/team-security.json --due --json
agent-do security monitor run --config ~/team-security.json --json
```

The export pins the current Python/tool/config paths, PATH, and AGENT_DO_HOME;
it does not embed tokens or copy authentication variables. Make existing `gh`,
Maven/Gradle, network and credential setup available to the scheduler account.
Jobs require the machine to be awake. A missed interval is checked at the next
hourly invocation; this is not a hosted scheduler or catch-up queue. macOS/Linux
POSIX locking and a working cron service are required. Run `monitor schedule`
again after relocating the checkout or Python environment. The exported PATH is
a snapshot of this session on this machine, not a portable CI setup. Regenerate
on the intended host/account and review its tool paths and credentials instead
of copying a laptop command unchanged to another machine.

## Optional notifications

No message is sent unless explicitly requested. Use an already configured
`agent-do notify` recipient/provider; normal notification credentials and any
provider approval requirements still apply:

```bash
agent-do security monitor run --config ~/team-security.json \
  --notify-recipient security-team --notify-via slack --cvss-min 7 --include-unscored
agent-do security monitor schedule --config ~/team-security.json \
  --notify-recipient security-team --notify-via slack --json
```

Notifications contain filtered change counts, assessment/comparison status and
the local digest path, not raw findings/build logs. Defaults send no notification.
Delivery is best-effort, not exactly-once; a failed notification makes the monitor
command incomplete without undoing committed scan evidence. There is no automatic
notification retry, and `--due` skips do not notify. Schedule export only includes
the explicit notification arguments; nothing is sent while exporting a job.

## Validation and remaining scope

```bash
python3 tests/test_security_monitor.py
```

Tests exercise transitions, failures, alias/version changes, new scopes, removed
targets, due intervals, locks, failed state writes, config rejection, opt-in
notifications, cron export and a local Maven/scanner fixture pipeline. They do
not establish live multi-repository compatibility, actual cron execution, or
notification delivery on your host. Milestone 4 now adds explicit runtime/deployment inventory; automatic collectors remain follow-up work;
milestone 5 adds remediation/update PRs. Monitoring never automatically updates,
publishes or deploys a repository.
