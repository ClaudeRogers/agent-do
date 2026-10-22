# Test milestones 3 and 4 together

Use this checklist after pulling `feat/security-cve-scanning` for PR #64. It covers
milestone 3 portfolio monitoring, the implemented portion of milestone 4 runtime
assessment, and the existing scan/report regression checks. It does **not** treat
an exported cron line as proof of scheduling or an inventory-only report as a CVE
assessment. Automatic image/cluster collectors and vendor/backport integrations
remain milestone 4 follow-up work.

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
For Eclipse Adoptium/Temurin, inventory-only can pass while runtime CVE assessment
remains unavailable until a verified distribution identity/adapter is provided.
That is a coverage limitation, not a passed CVE scan. Do not substitute Oracle's
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
