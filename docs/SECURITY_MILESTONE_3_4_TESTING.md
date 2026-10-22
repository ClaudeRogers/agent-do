# Test milestones 3 and 4 together

The [milestone 4 completion scope](SECURITY_MILESTONE_4_COMPLETION.md) and
[collector/vendor guide](RUNTIME_COLLECTION.md) define the newly implemented
acceptance boundary. Complete the additional host checks at the end of this guide
before marking live collectors accepted. Offline fixture success alone is insufficient.

Use this checklist after pulling `feat/security-cve-scanning` for PR #64. It covers
milestone 3 portfolio monitoring, the implemented portion of milestone 4 runtime
assessment, and the existing scan/report regression checks. It does **not** treat
an exported cron line as proof of scheduling or an inventory-only report as a CVE
assessment. Explicit image/rootfs/Kubernetes collectors and Temurin/vendor advisory
paths now have a separate acceptance section below. Their offline fixture tests
are not proof of registry, cluster or vendor-network access on the user's host.

## Run the automated suite

From the agent-do checkout:

```bash
python3 -m unittest discover -s tests -p 'test_security*.py'
```

This includes both `test_security_monitor.py` and `test_security_runtime.py`, plus
source-scanning, resolution, discovery, batch and report regressions. The suite
uses offline advisory/scanner fixtures and private temporary state. It probes
installed Java when available; it sends no notifications and installs no jobs.
No real vulnerable application or deployment changes are required.

The combined tests include:

| Area | Required behavior |
| --- | --- |
| M3 lifecycle | First detection is new; repeat is ongoing; absence resolves only after a complete compatible assessment; partial scans retain unverified evidence. |
| M3 configuration | Overwrite is refused without changing bytes; removed targets and changed settings/scanner/build scopes never silently resolve findings. |
| M3 operation | Due gating skips safely, concurrent runs lock, failed state writes retain the baseline, report filters do not rescan, and cron export preserves execution guards. |
| M4 evidence | POM Java 17 remains a declaration when observed Java is 21; inventory-only makes no requests; unknown vendors remain unmapped. |
| M4 identities | Oracle identity on an observed non-Oracle JDK fails before NVD lookup; malformed identities show a usable format example and offline inspection command. |
| M4 matching | Numeric bounds, legacy `7u`/`8u` versions, CPE update representations, AND/OR/negation, OS prerequisites, cross-host isolation, truncation and stale data are tested. |
| M4 XStream regression | A public NVD mirror snapshot of CVE-2021-21349 excludes Java 21.0.8 while preserving its explicitly affected historical Java 7/8 versions. This is a general version fix, not a CVE-specific suppression. |
| M3 + M4 integration | One portfolio scans a source target and runtime inventory; a runtime version fix resolves its issue while the library issue stays ongoing. Runtime failure cannot claim remediation. |
| Runtime monitoring | Component IDs stay distinct; membership/deployment changes retain unverified history; scheduled runtime record bounds are preserved. |

## Host regression checks

Install OSV-Scanner v2 separately and use your trusted local project. The examples
use `map-managed-bff`; replace the path if necessary. Keep normal Maven credentials
in settings/environment. Use `./agent-do` when running from the checkout.

```bash
./agent-do security doctor --json
./agent-do security scan --path ~/workspace/map-managed-bff \
  --resolve maven --include-unscored --json
./agent-do security report --latest-complete --json
./agent-do security report --list --json
```

Expected: successful resolution/scanning reports complete, even with findings or
unscored CVSS. Record the actual shell exit code immediately after each command
(`echo $?` in bash/zsh). Exit 0 means complete coverage for the requested scope,
not absence of vulnerabilities; 1 means incomplete assessment; 2 means invalid
input/state. Use `report --file` with the scan's `saved_report` path to avoid
selecting another project's or command's newer report.

`--fix-available` keeps findings **with** published fixes. If every finding has a
fix, the shown count is unchanged. This clarification is already in the
[parameter reference](SECURITY_CLI_REFERENCE.md#shared-finding-filters).

## Milestone 3 host checks

Choose a new config filename for this test; initialization never overwrites it:

```bash
./agent-do security monitor init --config ~/bff-m3-test.json \
  --path ~/workspace/map-managed-bff --resolve maven --interval-hours 24 --json
./agent-do security monitor run --config ~/bff-m3-test.json \
  --allow-builds --include-unscored --json
./agent-do security monitor run --config ~/bff-m3-test.json \
  --allow-builds --include-unscored --json
./agent-do security monitor run --config ~/bff-m3-test.json --due --json
./agent-do security monitor report --config ~/bff-m3-test.json \
  --severity critical --json
./agent-do security monitor schedule --config ~/bff-m3-test.json --allow-builds --json
```

Expected in order: create; new issues; ongoing issues with retained first-detection
times; skipped/not due; filtered saved digest without a rescan; reviewable cron
with `installed: false`. Real advisory/inventory changes between runs can
legitimately introduce changes; do not hard-code 17 findings as the success rule.

Negative checks: repeat init with that config (exit 2, friendly already-exists
message, unchanged file); export its Maven schedule without `--allow-builds`
(exit 2); run without `--allow-builds` (exit 1, prior evidence unverified rather
than resolved). Run the last negative check **after** the successful baseline
checks because it becomes the latest committed digest.

The cron export pins this host's Python, checkout, PATH, config and state paths.
Regenerate it on the actual scheduling host/account. Do not copy a laptop's PATH
unchanged to CI or another machine. Actual cron execution and live notification
delivery remain separate host tests; no notification is enabled by this checklist.

## Milestone 4 host checks

```bash
./agent-do security runtime --local-java --inventory-only --json
./agent-do security runtime --path ~/workspace/map-managed-bff --inventory-only --json
./agent-do security runtime --path ~/workspace/map-managed-bff --local-java --json
```

Expected: the selected local JDK vendor/patch is observed; POM/image references
remain declaration-only hints; the final command either assesses a supported
Oracle runtime identity or explicitly reports incomplete/unmapped vendor coverage.
Eclipse Adoptium/Temurin now uses the official Adoptium VDR adapter. A VDR fetch
failure remains incomplete and is not a passed CVE scan. Do not substitute Oracle's
identity to make the command return findings. An explicit Oracle identity on an
observed non-Oracle JDK now returns incomplete before any NVD query.

On an actual Oracle JDK, the identity syntax is:

```bash
./agent-do security runtime --local-java --java /path/to/oracle-jdk/bin/java \
  --java-cpe 'cpe:2.3:a:oracle:jdk:*:*:*:*:*:*:*:*' \
  --include-unscored --json
```

This is an Oracle-only example. Exact versions, embedded wildcards and malformed
CPE templates are rejected with an inline format hint. Inventory-only combined
with advisory filters is rejected rather than silently ignoring them.

For deployed/image evidence, use the JSON schema in the
[runtime guide](RUNTIME_ASSESSMENT.md#import-deployment-or-image-inventory), populated
with your verified identities and observation times:

```bash
./agent-do security runtime --inventory ~/runtime-inventory.json --json
./agent-do security monitor init --config ~/runtime-m4-test.json \
  --runtime-inventory ~/runtime-inventory.json --interval-hours 24 --json
./agent-do security monitor run --config ~/runtime-m4-test.json --runtime-limit 2000 --json
./agent-do security monitor run --config ~/runtime-m4-test.json --runtime-limit 2000 --json
./agent-do security monitor report --config ~/runtime-m4-test.json --json
```

Expected: imported evidence remains labeled user-supplied, with original age and
deployment labels; first/repeat findings are new/ongoing; report reads the digest.
Create a mixed source/runtime portfolio directly:

```bash
./agent-do security monitor init --config ~/mixed-m3-m4-test.json \
  --path ~/workspace/map-managed-bff --resolve maven \
  --runtime-inventory ~/runtime-inventory.json --json
./agent-do security monitor run --config ~/mixed-m3-m4-test.json --allow-builds --json
```

This runs both scopes without hand-writing a config or monitor ID. To edit a
config instead, preserve the generated schema_version and monitor_id; missing
metadata causes rejection, not the presence of mixed targets. A complete supported version change can resolve a runtime issue;
a removed component, changed deployment, missing file or uncertain match cannot
silently resolve earlier evidence. Automated fixtures exercise these transitions
without changing your real deployments. Reusing old inventory is not proof that
a deployment was patched or freshly observed.

For a positive runtime applicability check with a verified Oracle JDK inventory
whose version is 17.0.12, use its `oracle:jdk` CPE and this published advisory:

```bash
./agent-do security runtime --inventory ~/runtime-inventory.json \
  --cve CVE-2024-21235 --json
```

The offline public NVD mirror fixture confirms this version is listed. This host
command still requires NVD access/current data. Legacy `oracle:java_se` inventory
now produces an explicit limited-coverage status; replace that example only after
verifying the actual Oracle JDK identity. There is no default severity threshold
that would explain away zero findings. Do not classify a zero-result identity
query as proof that Java 17.0.12 is secure.

The automated suite also covers canonical paths and can be run with a symlinked
temporary directory to reproduce macOS-style temp path aliases. Fixtures use
canonical paths for lookup/argument assertions; Gradle containment canonicalizes
both root and manifest, while retaining outside-root rejection.

## Check the historical Java candidate regression

For verified modern Oracle JDK inventory, these targeted queries should examine
the records and exclude the historical CVEs:

```bash
./agent-do security runtime --inventory ~/runtime-inventory-v8.json \
  --cve CVE-2012-1723 --timeout 60 --json
./agent-do security runtime --inventory ~/runtime-inventory-v8.json \
  --cve CVE-2012-1531 --timeout 60 --json
```

The public regression fixtures include the actual legacy upper bounds
`1.4.2_37`/`1.4.2_38`. Tests retain affected historical Java 1.4 matches as well as
excluding modern Java. Also rerun the positive CVE-2024-21235 check above; the fix
does not suppress historical CVEs by identifier or suppress all wildcard matches.

Runtime matcher revision 2 uses a new monitor comparison baseline. Earlier
baseline findings remain unverified on an existing monitor; a new baseline's
complete assessment does not claim they were patched. A fresh disposable monitor
config can isolate new/ongoing counts for acceptance testing. Remaining broad-scan
candidates still require their own evidence review; these two cases do not explain
all candidate causes automatically.

## Check failed acquisition separately from candidate findings

Read `assessment_summary` in monitor run/report JSON and its prominently printed
text equivalent. Source errors appear before lifecycle counts, including NVD
`TimeoutError: advisory fetch failed`. With no earlier history, a failed scan can
have zero new/ongoing/resolved/unverified counts; that is not a clean assessment.

An uncertain candidate list and a network failure are different outcomes. The
automated suite verifies that a candidate is committed as new, remains ongoing
on a repeated incomplete assessment, and becomes unverified after a later timeout.
The timeout summary reports zero current observations and an explicit source
error while preserving historical evidence. It never claims the prior candidate
was resolved. The summary's observed counts are unfiltered; normal lifecycle
presentation filters still apply independently.

## Record the result accurately

Record branch commit, command, exit code, report status, comparison status, counts
and coverage reasons. Mark tests separately as passed, failed, skipped/not exercised,
or blocked by missing evidence/environment. Do not count a deliberate unmapped
vendor result as successful CVE matching or label remaining milestone 4 collectors
complete. Preserve private reports locally; review/redact evidence before sharing.

The v6 laptop report covers M3's basic host workflow and M4's local hints/probe.
It does not yet exercise imported deployment inventory, mixed portfolios, real
scheduled execution, live delivery, or deployment collection. Automated coverage
and the host checklist above make those distinctions explicit.

## Milestone 4 completion: vendor and collectors

New automated tests are in `tests/test_security_collectors.py`. They cover
Temurin exact/older/newer/unsupported patch listings and vendor integrity; private
asset redirects; Syft-to-Trivy digest agreement; JVM release-file identity without
Oracle substitution; backport fix preservation; stale/EOL databases; missing
helper/registry errors; explicit Kubernetes scope and missing/pending image IDs;
and collector monitoring authorization, lifecycle and failure retention.
The four v11 Oracle candidates have matching-only public NVD fixtures in the
runtime suite: unrelated escaped NetApp/WebKit predicates no longer poison Java
branches. Related unsupported semantics still stay uncertain. Matcher revision 3
creates a separate baseline; an old candidate becoming unverified is not a patch.

Run this compact host acceptance pass after pulling the completion commit:

```bash
./agent-do security doctor --json
./agent-do security runtime --local-java --inventory-only --json
./agent-do security runtime --local-java --timeout 60 --json
./agent-do security runtime --inventory ~/runtime-inventory-v8.json \
  --limit 2000 --cache-ttl 86400 --include-unscored --json

# Install current Syft/Trivy first (macOS: brew install syft trivy).
./agent-do security runtime --image eclipse-temurin:21-jre --inventory-only --json
./agent-do security runtime --image eclipse-temurin:21-jre --collect-timeout 600 --json
./agent-do security monitor init --config ~/image-m4-completion.json \
  --image eclipse-temurin:21-jre --interval-hours 24 --json
./agent-do security monitor run --config ~/image-m4-completion.json --allow-collectors --json
./agent-do security monitor run --config ~/image-m4-completion.json --allow-collectors --json
./agent-do security monitor run --config ~/image-m4-completion.json --json
```

Expected evidence:

- Adoptium observations map to Temurin, never Oracle; live assessment has an official
  VDR release tag/digest/receipts or an explicit acquisition error. Do not count a
  fetch failure as successful vendor assessment. A candidate is not confirmed
  exposure. A zero result is scoped to the supplied version and vendor report.
- Reusing the v11 Oracle dataset excludes those four unrelated-complex-CPE
  candidates; new NVD data can legitimately change counts. Check IDs and matching
  evidence rather than assuming a permanent count of four.
- Image reports preserve one pinned repository digest, JVM vendor/release metadata,
  Syft/Trivy versions and DB age, without image environment/config secrets. Both
  collectors must confirm the immutable reference. Nonempty helper diagnostics or
  missing/stale metadata stay incomplete; investigate rather than accepting them.
- Two image monitor runs produce new then ongoing evidence when findings exist.
  The final run without authorization is incomplete and retains earlier evidence
  as unverified; it executes no collectors. Zero findings cannot exercise a positive
  lifecycle test—retain the fixture test result separately.

For a mounted host/image root, select a disposable snapshot explicitly:

```bash
./agent-do security runtime --rootfs /mnt/approved-snapshot --inventory-only --json
./agent-do security runtime --rootfs /mnt/approved-snapshot --json
```

For Kubernetes/AKS, use an explicitly approved context and namespace with an
existing workload; no cluster mutation is performed:

```bash
./agent-do security runtime --kube-context team-aks --namespace services \
  --selector app=bff --inventory-only --json
./agent-do security runtime --kube-context team-aks --namespace services \
  --selector app=bff --json
```

Check normal/init/ephemeral container coverage and confirm reported image digests
against pod status. Pending pods, missing pullable digests, denied RBAC, no matching
pods and unavailable registry credentials must remain incomplete. Node operating
systems, managed control planes and writable container layers are outside this
collector's scope. If you lack cluster access, mark the live Kubernetes test
**not run**, not passed or a known-good feature. Never paste raw credentials,
image config or pod environment into a test report.

Record helper versions, command, exit code, status, evidence and actual coverage
errors. Report vendor/image/rootfs/Kubernetes live checks separately from the
fixture suite. Full milestone closure requires host acceptance for the collection
paths the team intends to use; milestone 5 implementation has not started.
