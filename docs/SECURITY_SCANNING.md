# Vulnerability discovery and source dependency scanning

For every flag, its defaults, supported commands and example usage, see the
[complete command and parameter reference](SECURITY_CLI_REFERENCE.md).

`agent-do security` finds published advisories and assesses source dependency
inventories. It supports local directories and GitHub repositories. Ordinary
file scans write only private caches and reports. The explicit local
`--resolve maven|gradle` mode executes trusted project build code and permits
build/cache writes to obtain resolved dependency versions. No deployment or
automatic dependency upgrade is requested.

## Setup

```bash
agent-do security doctor --json
```

Install [OSV-Scanner v2](https://google.github.io/osv-scanner/installation/)
separately for source scans; it is **required** and not bundled with agent-do.
On macOS with Homebrew:

```bash
brew install osv-scanner
agent-do security doctor --json
```

Choose a trusted installed executable with `--scanner PATH`.
GitHub repository acquisition also requires `gh` and suitable repository access.
The command never starts an interactive login.

For local advisory-vector scoring, install the optional maintained CVSS library:

```bash
python3 -m pip install -r tools/agent-security/requirements.txt
```

Without this dependency, numeric advisory scores still work, and uncomputed
vectors remain visible as unscored evidence. A score filter excludes unscored
records unless `--include-unscored` is supplied. Always inspect the unscored count.

`NVD_API_KEY` is optional for NVD reads. `GH_TOKEN` or `GITHUB_TOKEN` is optional
for public GitHub advisory reads. Store credentials with `agent-do creds`, using
its stdin interface. GitHub acquisition uses the installed `gh` authentication.
Doctor reports presence and local prerequisites, not proven authorization or
network availability; it performs no network requests.

## Find published advisories

Combine predefined languages/platforms with repeatable `--target` flags, for
example `find --target java --target springboot --target angular --target node
--target aks --json`. See [multi-target discovery](MULTI_TARGET_DISCOVERY.md) for
exact curated coverage, per-query limits, match reasons, and saved-report filters.

```bash
# Exact NVD CPE components: vendor and product, not natural-language aliases.
agent-do security find --vendor oracle --product jdk --cvss-gt 7 --json
agent-do security find --product cpython --published-after 2026-10-01 --json

# Broad keyword discovery when product identity is not known.
agent-do security find --query java --cvss-min 7 --json

# GitHub-reviewed package advisories, including advisories without a CVE.
agent-do security find --ecosystem pypi --package litellm --json
agent-do security find --ecosystem composer --cvss-min 7 --json

# A particular CVE, or records revised since a date.
agent-do security find --cve CVE-2021-44228 --json
agent-do security find --updated-after 2026-10-01 --known-exploited --json
```

Source selection defaults to NVD for vendor/product/keyword queries and GitHub
for ecosystem/package queries; `--source nvd|github` selects explicitly. Package
discovery requires an ecosystem. `python` and `pypi` normalize to GitHub's `pip`;
`php` and `packagist` normalize to `composer`. Product identity remains separate:
the Python interpreter is a product, while LiteLLM is a package. Java JDK
distributions have distinct CPE identities. `--query java` is a text search,
not proof that every result affects every Java runtime.

Discovery covers records from the selected source, not an exhaustive global
catalog. GitHub discovery includes reviewed, nonwithdrawn advisories. NVD rejected
records are omitted. NVD CPE configuration ranges are preserved without turning
their bounds into inferred fixed versions. Consequently `--fix-available` is
most useful for package advisory sources that explicitly publish fixes.

`--limit` defaults to 100 **source records examined before local presentation
filters**. Pagination continues until the source is exhausted or this limit is
reached. Output reports examined counts, available totals, and truncation;
increase the limit to broaden the assessed window. A restrictive score filter
does not mean the rest of the catalog was searched. GitHub supplies no total
record count for this endpoint. Page sizes respect each provider's API limits.

## Scan source dependencies

```bash
agent-do security scan --path . --json
agent-do security scan --path ../service --cvss-min 7 --include-unscored --json
agent-do security scan --repo https://github.com/owner/repo --ref main --json
agent-do security scan --repo owner/repo --cve CVE-2021-44228 --json
agent-do security scan --repos-file ~/team-repos.txt --cvss-min 7 --include-unscored --json
```

Keep one GitHub URL or `owner/repo` per line in `team-repos.txt`. See
[repository-list scanning](REPOSITORY_LIST_SCANNING.md) for JSON refs,
per-repository coverage and saved batch reports.

Local scans include uncommitted dependency files and record Git HEAD/dirty state
when available. GitHub scans resolve a ref to an immutable commit and fetch
dependency files from that commit. A content fingerprint identifies the actual
dependency snapshot. GitHub acquisition rejects truncated trees. Symlinks and
nonregular dependency files are not followed; coverage reports exclusions.

File-only scans of both target types copy recognized manifests and lockfiles into an isolated
temporary directory. Repository-provided scanner configuration is not copied,
so it cannot hide findings. OSV-Scanner v2 runs with an empty global config and
`--all-packages`; its version, raw JSON evidence, output hash, package inventory,
and normalized findings are retained. The temporary source copy is removed.

Recognized inputs include npm/yarn/pnpm/bun, Composer, pinned requirements and
common Python lockfiles, Maven POMs and Gradle locks, Cargo, Go modules, Ruby,
NuGet, Dart, and Elixir inventories. Actual extraction depends on the installed
OSV-Scanner version. A recognized file with no returned package inventory is a
coverage gap. This deliberately favors visible uncertainty over an empty report.

Unpinned requirements, manifest-only projects, and POM-only transitive inventory
are marked unresolved. Packages with available version evidence may still yield
findings. File-only scans do not resolve these projects by installing or building them.
Nested projects are considered, excluding `.git`, `node_modules`, `.venv`, `venv`,
`vendor`, `target`, `dist`, `build`, `__pycache__`, and `.agent-do` directories.

A dependency version match does not establish exploitability. Runtime, OS,
container-image, deployed-artifact, and reachability assessments are outside
this MVP's source-dependency scope. For example, a Composer lockfile does not
establish the installed PHP runtime version. A fixed GitHub branch does not
establish that production has been updated.

### Dependabot provider integration

```bash
agent-do security scan --repo owner/repo --dependabot --json
```

This optional adapter invokes the existing `agent-do gh alerts` provider proposed
in [PR #51](https://github.com/ovachiever/agent-do/pull/51). If that provider is not
installed, the report explicitly marks it unavailable. Its raw alert census is
attached under `dependabot`, separately scoped to GitHub's default-branch alert
inventory. It is not merged into commit-specific findings, because equivalence
to the scanned commit is not established. Disabled alerts and access errors
remain coverage gaps; neither is counted as zero.

## Filters and saved reports

Local Maven/Gradle projects can opt in to build resolution with
`scan --path DIR --resolve maven|gradle`. See
[JVM dependency resolution](JVM_DEPENDENCY_RESOLUTION.md) for wrapper selection,
profiles/settings, configurations, dependency paths, and build-execution scope.

```bash
agent-do security report --latest --cvss-min 7 --include-unscored --json
agent-do security report --list --json
agent-do security report --latest-complete --severity critical,high --json
agent-do security report --file /path/to/report.json --severity critical,high
agent-do security scan --path . --kev --json
agent-do security report --latest --known-exploited --json
```

Shared filters include CVE aliases, ecosystem/package, inclusive `--cvss-min`,
exclusive `--cvss-gt`, comma-separated `--severity`, `--fix-available`, and dates.
Score filtering uses the maximum available base score, preserving each score's
version, vector, and source. Severity follows that score when available; otherwise
it uses the advisory's category or `unknown`. Aliases are merged transitively;
different installed versions remain separate findings. Evidence paths from
multiple occurrences are retained. A published fix is not a tested upgrade plan.

`--fix-available` keeps findings **with** a published fix; it does not remove
them as already resolved. If all 17 findings have fixes, all 17 remain shown.

Dates accept ISO dates/timestamps; a missing timezone means UTC.
`--published-after` is inclusive, `--published-before` is exclusive, and
`--updated-after` is inclusive. NVD publication and modification API windows
must be positive and at most 120 days. When only a publication end is supplied,
the start is 120 days earlier; when only a start is supplied, the end is request
time. Without date filters, no 120-day publication window is imposed. The report
records the request URL.
For modification queries, the upper boundary is request time. Use explicit
publication bounds to make historical searches reproducible. GitHub results
also undergo local date filtering so API-inclusive upper bounds cannot leak in.

`--kev` enriches all results with CISA's catalog; `--known-exploited` also
enriches, then filters. Catalog failures leave exploitation status unknown and
make the assessment incomplete. Saved reports without enrichment cannot later
answer an exploitation filter; repeat the assessment with `--kev`.

Every `find`/`scan` saves **unfiltered** JSON under
`$AGENT_DO_HOME/security/reports/`, defaulting to `~/.agent-do/security/reports/`.
Reports use schema version 1 and unique filenames; a later failed scan never
overwrites earlier evidence. `report` reads saved evidence without network
requests or modifying it. It reports total, shown, excluded, and unscored counts.

`report --latest` includes failed/incomplete assessments and explicitly flags
them; it never silently replaces a recent failure with older findings. Use
`report --list` to see timestamps, targets, status, counts, coverage gaps and
paths for all reports, then `report --file PATH` to choose one. Alternatively,
`report --latest-complete` explicitly selects the newest complete assessment
across **all projects and commands**, which may be older or for a different
project. Always check the target and timestamp. These four selectors are mutually
exclusive. Listing accepts `--json` but not finding filters.

Execution exit codes:

- `0`: assessment completed within its declared scope, including completed
  assessments with vulnerability findings.
- `1`: incomplete assessment, including truncated discovery, stale data,
  unresolved inventory, source/scanner failures, or missing scanner prerequisites.
- `2`: invalid command input or unreadable/unsupported saved report.

No matching findings means no known matches in the successfully assessed
inventory and source window. Review coverage before interpreting that result.

Unscored CVSS values alone do **not** cause exit 1. If a scan resolves dependencies
and returns findings but exits incomplete, inspect non-`ok` entries in the JSON
`coverage` array. Scanner stderr warnings, unassessed inventory and unavailable
providers can still cause incomplete coverage. `--include-unscored` changes score
filtering, not assessment completeness.

The scanner's `advisory_data_freshness` field records that upstream publication
time is unknown on every scan; that field alone does not trigger a warning.
The scanner runs with `--verbosity=warn`, using OSV's native log-level filtering
to suppress its informational output, including info messages containing words
like "error". Other libraries may still write to stderr. Remaining output has
**unclassified severity and coverage impact**; it is not automatically known to
be warn-level or higher. It conservatively keeps coverage incomplete. Warning
coverage includes a reason, line count and stderr hash.
The report records `scanner.verbosity`. This behavior follows OSV-Scanner's
[verbosity option](https://github.com/google/osv-scanner/blob/v2.7.0/docs/usage.md#set-verbosity-level)
and [JSON-mode logging](https://github.com/google/osv-scanner/blob/v2.7.0/internal/cmdlogger/handler.go).

Earlier saved reports keep their original assessment status. If a new scan still
exits incomplete, inspect the actual diagnostic rather than treating every
warning as benign. Opt in to local capture:

```bash
agent-do security scan --path ~/workspace/map-managed-bff --resolve maven \
  --include-unscored --scanner-diagnostics ~/private-security-diagnostics --json
```

Raw scanner stderr is saved only when `--scanner-diagnostics DIR` is supplied.
Files have mode 0600, with unique names so subsequent scans cannot overwrite
earlier logs. A newly created destination directory has mode 0700. The plain
output prints its path; JSON records it under `scanner.diagnostics.stderr_file`
(under each repository record for batch scans). This captures the scan invocation,
including nonzero failures, not the version probe or Maven/Gradle build logs.
The JSON report never embeds the raw contents. Files may contain private paths,
URLs or credentials, so inspect locally and share only redacted relevant lines.
Capture does not change assessment status or silently accept unknown warnings.

OSV's [exit handling](https://github.com/google/osv-scanner/blob/v2.7.0/cmd/osv-scanner/internal/cmd/run.go)
can return 1 for findings before checking its logged-error flag. A valid result
document and exit 1 therefore do not by themselves prove all lookups succeeded.
The remaining warning reported in laptop testing is still under investigation;
`--latest-complete` will not select that run while its coverage remains unclassified.

## Network, cache, and data disclosure

Advisory APIs receive search filters. OSV-Scanner sends package identities and
versions to OSV; it may contact ecosystem metadata services as part of its
supported extraction. GitHub acquisition reads the selected repository through
`gh`. File-only scans do not run local target scripts or package-manager install
commands. Explicit `--resolve` scans run trusted local Maven/Gradle build code,
which can contact configured repositories and write project files and caches;
see the [resolution guide](JVM_DEPENDENCY_RESOLUTION.md).

HTTP JSON responses are cached privately for one hour by default. Credentials
are not saved in the cache; cache identities use credential hashes. `--refresh`
bypasses fresh entries. Stale fallback requires `--allow-stale`, is explicitly
marked, and exits incomplete. Receipts record source URL and original fetch time.
Upstream database publication time is not inferred from request time.

Operator controls include `--timeout`, `--scan-timeout`, `--retries`, `--cache-ttl`,
`--max-bytes`, and discovery `--limit`. Oversized data is an explicit failure.
HTTP rate-limit/server errors are retried with backoff; a Retry-After longer than
the HTTP timeout is surfaced for a later retry. Endpoint redirects are refused
to avoid forwarding credentials. Credentials and response error bodies are not
printed. Temporary/private reports can contain repository and package identities.

## Follow-up scope

Local repository lists and sequential batch scans are available through
`scan --repos-file`; see [repository-list scanning](REPOSITORY_LIST_SCANNING.md).
Compatible-inventory change reports, recurring scheduling and notifications
remain future work. Publication date and first
detection must be distinct, and failed/partial scans must never resolve prior
findings. Image/SBOM and deployment mapping follow that work. Remediation PRs
come afterward, with isolated lockfile updates and tests. The optional unrelated
advisory digest remains separate from repository remediation tasks.

## Validation

```bash
python3 tests/test_security.py
python3 tests/test_security_resolution.py
python3 tests/test_security_targets.py
python3 tests/test_security_repositories.py
python3 tests/test_security_reports.py
./agent-do harness contracts validate
./agent-do harness contracts drift --tool security
./agent-do harness bounds drift --tool security
bin/gen-tools-doc --check
./test.sh
```

The security suite is deterministic and offline. It exercises documented source
shapes and executable scanner doubles, not live database/scanner compatibility.
Verify a real installed scanner and advisory APIs in a network-enabled checkout
before relying on production results.

API/scanner references: [NVD CVE API](https://nvd.nist.gov/developers/vulnerabilities),
[GitHub global advisories](https://docs.github.com/en/rest/security-advisories/global-advisories),
[OSV output](https://google.github.io/osv-scanner/output/),
[OSV formats](https://google.github.io/osv-scanner/supported-languages-and-lockfiles/),
and [CISA KEV](https://www.cisa.gov/known-exploited-vulnerabilities-catalog).
