# Runtime and deployment evidence (milestone 4)

`agent-do security runtime` adds runtime assessment alongside source dependency
scanning. A POM's `java.version=17` is a declaration, not proof that production is
running a particular patched JDK. The new command keeps those facts separate.

Use the [combined milestone 3/4 test checklist](SECURITY_MILESTONE_3_4_TESTING.md)
to test monitoring and runtime assessment together.

Milestone 4 includes static hints, explicit local Java probing, imported evidence,
NVD matching, Adoptium Temurin VDR assessment, explicit Syft/Trivy image/rootfs
collection and read-only Kubernetes pod image discovery. See
[collection setup and examples](RUNTIME_COLLECTION.md) and the
[completion scope](SECURITY_MILESTONE_4_COMPLETION.md). Milestone 5 remains
remediation/update PRs. Nothing updates your project.

## Test a local Java project

First collect evidence without contacting any advisory service:

```bash
agent-do security runtime --path ~/workspace/map-managed-bff \
  --local-java --inventory-only --json
```

`--local-java` explicitly executes the installed `java` with
`-XshowSettings:properties -version`. Select a different trusted executable with
`--java /path/to/jdk/bin/java`. It captures only vendor, Java version, runtime
version and VM name; raw properties, environment and process output are not saved.
The report identifies the executable and observation time. It does not execute
Maven, Gradle or project wrappers, or establish which JDK those builds use.

Then assess the observed runtime:

```bash
agent-do security runtime --path ~/workspace/map-managed-bff \
  --local-java --cvss-min 7 --include-unscored --json
```

Oracle Corporation HotSpot observations on Java 11+ map to `oracle:jdk`.
Older Oracle releases require an explicit JDK/JRE identity because the VM name
alone does not distinguish those installed artifacts. OpenJDK builds
require a verified explicit identity; the VM name alone does not establish that
artifact mapping. Eclipse Adoptium maps separately to Temurin and its official VDR.
Other vendors remain **unmapped**, with
incomplete coverage, unless you supply a distribution identity you have verified:

```bash
agent-do security runtime --local-java --java /path/to/oracle-jdk/bin/java \
  --java-cpe 'cpe:2.3:a:oracle:jdk:*:*:*:*:*:*:*:*' --json
```

That example is an **Oracle Java identity**, not a generic identity for Temurin,
Corretto, Debian, GraalVM or every other Java distribution. Do not force it onto a
different vendor to obtain results. Oracle Java identities are rejected before
lookup when the probe reports a non-Oracle vendor, including Adoptium/Temurin.
Other unmapped distributions still need verified identity/adapter work; an
inventory-only success does not establish CVE coverage. An explicit identity is marked caller-selected;
the plugin does not independently verify the mapping. Vendor mappings are kept
narrow to avoid false claims of affected or patched distributions.

Modern Java patch versions and build metadata are preserved. Java 8 observations
such as `1.8.0_422` become CPE version `1.8.0`, update `update_422`; supported
numeric range comparison accounts for the update number. Historical Java CPE
versions such as `7u321` and `8u311` normalize to the equivalent update form; they
do not become uncertain candidates for a modern Java 21 runtime. Early-access and
vendor-specific ordering are not guessed.

## Oracle identities and negative results

Modern Oracle JDK advisories use `oracle:jdk` (and Oracle JRE uses `oracle:jre`).
The earlier `oracle:java_se` example was too narrow for modern JDK assessment.
Legacy java_se queries now explicitly have limited/incomplete coverage rather
than allowing a zero-result report to imply complete JDK coverage. Existing saved
reports are not rewritten; verify your artifact and rerun with the correct CPE.
Identity changes create a separate monitor comparison scope.

The public NVD mirror fixture for CVE-2024-21235 explicitly lists Oracle JDK
17.0.12. It provides a positive matching regression alongside the historical
XStream exclusion. A query returning six records for legacy java_se is not proof
that this JDK version is unaffected. There is **no default severity threshold**:
unscored findings are retained unless a supplied filter excludes them. Zero shown
findings means no matches in the assessed identity/source window and filters;
it is never a general claim that a version is secure.

## Project declarations

`--path DIR` reads the root `pom.xml`, `build.gradle`, `build.gradle.kts`,
`.java-version`, `.tool-versions`, and `Dockerfile` when present. It reports POM
Java/compiler properties and compiler-plugin settings; recognized Gradle literals;
tool version hints; and Docker `FROM` references. Gradle expressions it cannot
statically interpret are labeled unresolved. It does not evaluate scripts,
resolve POM parents/properties, traverse submodules or guarantee effective settings.
Only version expressions are captured from Gradle, not whole source lines.

```bash
agent-do security runtime --path /path/to/project --inventory-only
agent-do security runtime --path /path/to/project --json
```

The second command is deliberately **incomplete** without runtime evidence:
project declarations and mutable image tags cannot establish an installed patch
version. The first is a completed inventory operation, explicitly labeled
`runtime_inventory_only`; it has not assessed CVEs.

`security scan --resolve maven` continues to assess resolved library dependencies.
Run both commands to assess dependency versions and explicit runtime evidence.
A Spring Boot or Angular library scan is not automatically a Java or Node binary
assessment.

## Import deployment or image inventory

Create a local JSON file with exact CPE identities and provenance. This example
shows the schema, not a recommended JDK version or a claim that it is secure:

```json
{
  "schema_version": 1,
  "components": [
    {
      "id": "bff-prod-jdk",
      "cpe": "cpe:2.3:a:oracle:jdk:17.0.12:*:*:*:*:*:*:*",
      "evidence": {
        "kind": "deployment_inventory",
        "source": "Observed java.version and vendor in the selected deployment",
        "observed_at": "2026-10-22T09:00:00Z"
      },
      "deployment": {
        "environment": "production",
        "cluster": "team-cluster",
        "namespace": "services",
        "workload": "bff"
      }
    }
  ]
}
```

```bash
agent-do security runtime --inventory ~/runtime-inventory.json --json
agent-do security runtime --inventory ~/runtime-inventory.json \
  --package oracle:jdk --cvss-min 7 --include-unscored --json
agent-do security runtime --inventory ~/runtime-inventory.json \
  --cve CVE-2021-44228 --json
```

The last example demonstrates a CVE filter; it does not imply that a library CVE
applies to the JDK. Nonmatching configurations are excluded.

Every component requires a unique nonempty `id`, a CPE 2.3 string with explicit
part/vendor/product/version, and `evidence` containing exactly `kind`, `source`
and an ISO `observed_at`. Future observation times are rejected. Evidence kinds
are `manual`, `deployment_inventory`, or `image_inventory`. Imported evidence is
always marked `user_supplied_not_independently_verified`; recurring assessment does
not refresh its observation time or prove a deployment changed. Use exact versions
from your collector, not broad major-version tags or a desired configuration.

Optional `deployment` fields are `environment`, `cluster`, `namespace`, `workload`,
`image`, `image_digest`, and `host`, all strings. For an image, include its immutable
digest and actual component evidence. A GitHub URL or a Docker tag alone cannot
supply that evidence. This command does not pull images or invoke kubectl/SSH.

The schema can represent Node, Python, PHP, OS and platform CPEs too. Verify the
vendor/product identity and exact version against NVD. Numeric version ranges are
supported; distro revisions, backports, complex escaped CPEs and unsupported
version schemes remain candidates/incomplete instead of guessed matches. This
is not an OS package advisory scanner. General CycloneDX/SPDX files are not directly
accepted here; convert verified runtime CPE evidence into the documented schema.
Do not put credentials in inventory provenance or deployment labels.

## Match strength and coverage

NVD is queried by explicit CPE product, with bounded pagination. Original
configuration trees are retained as evidence. AND/OR, negation, vulnerable flags,
exact versions and inclusive/exclusive numeric bounds are evaluated. A matching
range boundary is not reported as a published fix.

- `inventory_match`: supplied version/identity evidence satisfies the supported
  NVD conditions. It does not prove exploitability, reachability or independent
  verification of an imported deployment.
- `candidate`: applicability cannot be established because evidence or supported
  matching semantics are missing. The assessment is incomplete, not an all-clear.
- A supported nonmatch is excluded. Rejected advisories are excluded.

Environmental prerequisites can use other inventory components only when they
have identical deployment labels and those labels include a `host`, an
`image_digest`, or all of `cluster`/`namespace`/`workload`. A shared environment
name alone does not establish co-location. Local Java is not implicitly co-located
with imported evidence. Unknown OS prerequisites never become true simply because
some other server in the portfolio has that OS.

`--limit` defaults to 1000 NVD records **per runtime component**. A truncated product
query remains incomplete; increase the limit or narrow the assessment to a specific
CVE. Score/date filters apply after applicability assessment and never narrow the
saved evidence silently. Missing data, failed pages, stale cache and unknown
conditions are explicit coverage gaps. Cache freshness is not advisory database
publication time or deployment inventory freshness.

Reports use the existing private append-only report store and support
`security report --list`, `--file`, `--latest`, `--latest-complete` and filters.
Latest-complete selection spans commands, including inventory-only reports; inspect
`command`, `scope`, target and timestamp. Exit 0 means the requested assessment
completed, even with findings; exit 1 means incomplete coverage; invalid CLI input
returns 2. Inventory-only exit 0 makes no CVE claim.

## Historical Java bounds and matcher revisions

Wildcard versions can be constrained by NVD range fields; a wildcard alone is
not a reason to label a match uncertain. A JDK appearing only as a non-vulnerable
platform prerequisite is not itself a vulnerable JDK match.

The v10 laptop examples exposed a parser gap: the public NVD mirror records for
CVE-2012-1723 and CVE-2012-1531 contain upper bounds `1.4.2_37` and `1.4.2_38`.
The latter also contains vulnerable JDK entries, not only JavaFX. Earlier matching
could not parse these pre-Java-5 bounds and retained candidates for Java 17.
The updated matcher understands legacy `1.x.y_N` updates, including separate
CPE update fields and leading zeroes. Both records exclude Java 17/21 while
retaining matches at their affected historical Java 1.4 patch boundaries.
Unknown vendor/EA/build suffixes still remain uncertain rather than guessed.
These two examples do not establish the cause of every other candidate.

New runtime reports identify `runtime_matcher_schema: 2`. Runtime monitoring
starts a separate comparison baseline when matching rules change; old baseline
issues remain unverified, never described as deployment fixes. Source monitoring
is unaffected. Existing saved reports and history are not rewritten. Use a fresh
monitor config when testing only the new baseline's counts, or inspect both
assessment and comparison status on an existing monitor.

## Include runtimes in a recurring portfolio

```bash
agent-do security monitor init --config ~/runtime-monitor.json \
  --runtime-inventory ~/runtime-inventory.json --interval-hours 24
agent-do security monitor run --config ~/runtime-monitor.json --runtime-limit 2000 --json
agent-do security monitor report --config ~/runtime-monitor.json --json
agent-do security monitor schedule --config ~/runtime-monitor.json --runtime-limit 2000 --json
```

Create a mixed local Maven/runtime portfolio directly:

```bash
agent-do security monitor init --config ~/mixed-security.json \
  --path ~/workspace/map-managed-bff --resolve maven \
  --runtime-inventory ~/runtime-inventory.json
agent-do security monitor run --config ~/mixed-security.json --allow-builds --json
```

Or add `{"runtime_inventory": "/path/to/runtime-inventory.json"}` to an existing
portfolio's `targets` array alongside source repositories. Relative inventory paths
resolve beside the monitor configuration. Runtime targets accept only that field;
there is no implicit local executable probe in scheduled monitoring. Update the
inventory with your approved collector before scanning when you need fresh runtime
evidence. Existing notify delivery remains explicitly opt-in.

Component IDs keep runtime issues separate even when CVEs and products are shared.
Version updates compare in the same scope, so a no-longer-matching advisory can be
resolved against complete evidence. Changes to component membership, product
identity, deployment labels or evidence kind create a new scope: prior findings
remain unverified. Missing inventory files, partial queries and unknown conditions
cannot resolve prior findings. "Resolved" remains an evidence comparison, not
independent proof of deployment remediation.

## Validation

```bash
python3 tests/test_security_runtime.py
```

Tests cover numeric boundaries, Java 8 updates, actual local Java probing when
installed, privacy, declarations, missing vendor mapping, NVD conditions,
cross-host isolation, truncation/failure/staleness, the public XStream historical
Java regression, vendor mismatch guards, report reuse and mixed source/runtime monitor
lifecycle safety. Advisory matching tests use offline NVD fixtures; real NVD and
your deployment evidence still need host validation.
