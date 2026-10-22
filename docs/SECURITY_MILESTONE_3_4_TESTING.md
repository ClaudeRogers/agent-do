# Security monitoring and runtime acceptance

Use the checks relevant to the change under review. Do not repeat all live
repository, registry and cluster scans for a documentation edit or a focused fix.
Command parameters and workflows live in the [CLI reference](SECURITY_CLI_REFERENCE.md),
[monitoring guide](PORTFOLIO_MONITORING.md) and [runtime collection guide](RUNTIME_COLLECTION.md).

## Run the automated suite

```bash
python3 -m unittest discover -s tests -p 'test_security*.py'
```

The suite uses private temporary state, offline advisory data and executable
scanner doubles. It probes installed Java when available, but sends no
notifications, installs no jobs and changes no deployments. It covers:

| Area | Required behavior |
| --- | --- |
| Source/regression | File snapshots, selected Maven/Gradle versions, transitive paths, filters, report persistence and isolated repository failures. |
| Monitor lifecycle | New then ongoing; absence resolves only after a complete compatible assessment. Candidates are retained; failed scans keep earlier evidence unverified. |
| Monitor operation | Overwrite protection, due gating, locks, atomic writes, changed scopes/settings/helpers, removed targets and explicit build/collector authorization. |
| Runtime evidence | Declarations remain hints; observed/imported evidence keeps its identity, timestamp and deployment scope. Oracle identity is rejected on a non-Oracle JDK. |
| NVD matching | Numeric/legacy Java bounds, AND/OR/negation, missing prerequisites, unsupported related predicates and unrelated complex CPEs. |
| Vendor/collectors | Temurin VDR integrity/version matching; pinned image agreement; private YAML config lifetime; helper failures; stale/EOL databases; explicit Kubernetes context/namespace and missing image IDs. |

Public CVE regression extracts preserve affected-version positives as well as
modern/patched negatives. Their [fixture notes](../tests/fixtures/security/README.md)
explain the retained source predicates. They are not a complete advisory database.

## Host regression checks

Install OSV-Scanner v2 and use a trusted local project. Resolution explicitly
executes its build code. Replace the sample path and config names as needed.

```bash
./agent-do security doctor --json
./agent-do security scan --path ~/workspace/map-managed-bff \
  --resolve maven --include-unscored --json
./agent-do security report --list --json
```

Reopen the scan using `report --file PATH`, with its returned `saved_report` path.
`--latest-complete` spans projects and commands, including inventory-only results.
Record each exit code: 0 means the requested scope completed, 1 is incomplete,
2 is invalid input/state. Complete does not mean no vulnerabilities. Never use a
fixed finding count as a permanent success criterion against changing live data.

## Milestone 3 host checks

Use a new config filename; initialization does not overwrite existing files.

```bash
./agent-do security monitor init --config ~/bff-security-test.json \
  --path ~/workspace/map-managed-bff --resolve maven --interval-hours 24 --json
./agent-do security monitor run --config ~/bff-security-test.json --allow-builds --json
./agent-do security monitor run --config ~/bff-security-test.json --allow-builds --json
./agent-do security monitor run --config ~/bff-security-test.json --due --json
./agent-do security monitor report --config ~/bff-security-test.json --severity critical --json
./agent-do security monitor schedule --config ~/bff-security-test.json --allow-builds --json
```

Expect new then ongoing evidence, preserved first-detection times, a not-due skip,
a filtered saved digest, and a cron entry with `installed: false`. Repeat init
must fail without altering the config. Run without `--allow-builds` **after** the
baseline checks: assessment is incomplete, prior evidence unverified, none resolved.
Schedule export also requires build authorization. Actual cron execution and live
notification delivery are separate tests; export enables neither automatically.

## Milestone 4 host checks

```bash
./agent-do security runtime --path ~/workspace/map-managed-bff --inventory-only --json
./agent-do security runtime --local-java --inventory-only --json
./agent-do security runtime --local-java --timeout 60 --json
./agent-do security runtime --inventory ~/runtime-inventory.json --json
```

Declarations must not become installed versions. A supported observed Oracle JDK
uses its verified CPE; Temurin uses the official Adoptium VDR. Unknown distributions
stay unmapped. Inventory-only makes no CVE claim; explicit image/cluster collection
can still contact registries/APIs. Imported observations are not refreshed by scanning.
Use the [inventory schema](RUNTIME_ASSESSMENT.md#import-deployment-or-image-inventory)
with identities and timestamps verified for your environment.

For a known-positive Oracle JDK 17.0.12 inventory, the targeted live regression is
`runtime --inventory FILE --cve CVE-2024-21235 --json`. Historical Java exclusions
are covered offline; live NVD queries are not required for every parser change.
Matcher revisions create separate comparison baselines. Earlier evidence remains
unverified, never described as a deployment fix when the matching rules change.

## Check failed acquisition separately from candidate findings

Read `assessment_summary` before lifecycle counts. It separates unfiltered current
observations, inventory matches, candidates and source coverage errors. A first-run
timeout can have all zero lifecycle counts while the assessment failed. A retained
candidate can be new/ongoing on incomplete runs, then unverified after a timeout.
A removed target/component, changed deployment, missing inventory or partial scan
must not silently resolve earlier evidence. Mixed portfolios retain per-target status.

## Milestone 4 completion: vendor and collectors

For collector changes, choose the smallest relevant check. This rootfs probe
validates the installed Syft directly without a wrapper or advisory lookup:

```bash
./agent-do security runtime \
  --rootfs /Library/Java/JavaVirtualMachines/temurin-21.jdk/Contents/Home \
  --syft /opt/homebrew/bin/syft --inventory-only --json
```

For image/advisory changes, use a verified image and current Syft/Trivy:

```bash
./agent-do security runtime --image eclipse-temurin:21-jre --inventory-only --json
./agent-do security runtime --image eclipse-temurin:21-jre --json
```

Check the immutable repository digest, JVM release identity, vendor source receipt,
helper versions and vulnerability DB age. No image environment/config or raw helper
stderr should be persisted. An inventory-only success does not establish advisory
coverage; a macOS JDK directory does not exercise Linux vendor/backport assessment.

For Kubernetes changes, use a reachable approved context and namespace:

```bash
./agent-do security runtime --kube-context team-aks --namespace services \
  --selector app=bff --inventory-only --json
```

Confirm normal/init/ephemeral container image IDs against pod status. Empty/pending
pods, absent pullable digests, RBAC/registry failures and helper errors must remain
incomplete. Full assessment additionally requires a successful Trivy image path.
Node OS, managed control planes and writable container layers are outside scope.

Collector monitoring uses `monitor init --config PATH --image REF` (or rootfs/
Kubernetes selections), followed by two `monitor run --allow-collectors` invocations.
When findings exist, expect new then ongoing. A final run without authorization
must execute no collectors and retain previous evidence as unverified. This also
applies in mixed source/runtime portfolios; builds require their own authorization.

## Accepted scope and deferred validation

Milestone 4 is accepted for the tested scope. Host checks established source/JVM
resolution, Oracle matching, live authenticated Temurin VDR digest verification,
rootfs JVM identity and new/ongoing/unverified retention. The focused post-fix probe
confirmed Syft 1.55.0 works directly with temporary YAML config, without a wrapper.
Syft also acquired a registry image with immutable digest evidence.

Positive live Kubernetes collection and a complete remote Trivy image scan remain
**deferred** because of unavailable cluster/registry transport. They are not passed
acceptance checks. These deferred paths do not block the [planned remediation
feature](PLANNED_UPGRADES.md). Host-specific cron PATHs are expected; regenerate
schedules for the actual scan host/account.

## Record the result accurately

Record commit, command, helper versions, exit code, status, comparison status,
observation/change counts and coverage reasons. Distinguish passed, failed,
skipped and infrastructure-blocked tests. Keep reports private and redact before
sharing. A successful acquisition, a candidate and a confirmed inventory match are
separate outcomes; none by itself establishes runtime exploitability.
