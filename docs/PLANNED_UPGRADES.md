# Planned security upgrades: milestone 5

Status: **planned, not implemented**. Current commands discover, assess and monitor
vulnerabilities. This feature would turn supported findings into reviewable
dependency updates and draft pull requests. This document does not authorize
changes to any scanned application, merge, or deployment.

Maven/Gradle resolution was added as milestone 2 after the original four-stage
plan. Milestone 5 is now remediation. Milestone 4 is accepted for its tested scope;
live Kubernetes collection and a complete remote Trivy image scan remain deferred.
Those deferred collectors do not block remediation of confirmed source findings.

## Intended behavior

- Identify explicitly published patched versions and the declaration that controls
  the affected dependency. Preserve advisory URLs, resolved versions, dependency
  paths and source assessment IDs.
- Recommend direct dependency, parent, BOM or platform updates. For example,
  identify which Spring Boot parent/BOM update supplies a patched transitive
  Tomcat, rather than blindly pinning Tomcat in every application.
- Apply supported updates in an isolated local checkout or GitHub branch.
- Run the relevant build/tests and rescan the same dependency scope to verify the
  result. Preserve remaining findings, new findings and incomplete coverage.
- Open a draft PR with the changes, addressed CVEs, compatibility considerations
  and exact validation results. Never merge or deploy automatically.

An explicit apply invocation authorizes its selected, reviewable plan. Planning
alone changes no target files. Publishing requires an explicit PR invocation;
existing scan/monitor commands must never begin updating repositories implicitly.

## First implementation: Maven and Spring Boot

Start with the projects already exercised by this plugin. Support numeric direct
versions, version properties and parent/imported-BOM declarations where ownership
can be established from the effective dependency graph. Group CVEs addressed by
the same controlling declaration into one update.

Prefer the smallest supported compatible upgrade within the current release line.
Show major-version changes separately with their compatibility implications; do
not label a version compatible solely because its number is greater. Consult
published package/platform release metadata and resolve the proposed dependency
graph before recommending a parent/BOM version as a fix.

Leave ambiguous property ownership, conflicting BOMs, unsupported expressions,
private metadata failures and uncertain findings for manual review. Never invent
a fixed version from an NVD range boundary. Runtime/image upgrades need verified
vendor patch information; a Temurin candidate is not sufficient for automatic edits.

## Proposed workflow

The following are design stages, not commands available in the current CLI.
They should remain within the existing `security` command family.

| Stage | Inputs and behavior | Saved result |
| --- | --- | --- |
| Plan | Read a saved assessment and matching repository revision; inspect controlling declarations and published fixes. Any build resolution requires explicit build authorization. | Versioned JSON plan plus human-readable proposed changes; no target writes. |
| Apply | Validate a selected plan, create an isolated branch/worktree, edit supported declarations and regenerate inventories with native tooling. | Minimal diff and apply receipt, including base revision and changed-file hashes. |
| Verify | Resolve with the same profiles/settings/configurations, run configured checks and rescan. | Before/after assessments, validation commands and outcomes; unresolved uncertainty stays visible. |
| Draft PR | Publish the reviewed branch and create or update its matching draft PR. | PR URL, branch/revision, plan ID and validation receipt. No merge or deployment. |

The plan should record repository/ref/commit, source assessment ID/time, manifest
hashes, ecosystem, package/version, CVE aliases, declaration ownership, proposed
versions, fix-source evidence, grouped changes, compatibility notes and required
validation. Include a schema version and stable plan fingerprint.

## Repository and execution rules

- Reject a stale plan when its base revision or relevant manifest contents changed;
  regenerate it instead of applying to a different project state.
- Preserve the user's uncommitted work. Use a dedicated worktree/branch and never
  reset, overwrite or force-push their branch. GitHub links require authenticated
  access and a concrete selected ref; do not assume the deployed revision is main.
- Keep build execution explicit, following existing `--allow-builds` behavior.
  Package-manager install hooks and repository tests are project code, too.
  Do not execute newly acquired remote project code during read-only planning.
- Use normal Maven settings and credential mechanisms; never include credentials,
  settings contents or raw potentially sensitive build logs in reports or PRs.
- Reuse the current findings, report and comparison models. Keep update planning,
  ecosystem editors, verification and GitHub publication as separate adapters.
- Make retries idempotent: reuse the matching branch/draft PR when its plan/base
  still matches; never create one PR per CVE when one parent update addresses them.

## Verification and failure handling

A successful edit or passing build is not proof that a vulnerability was fixed.
Compare resolved before/after package versions and advisory matches under the
same scope, then report exactly which findings are no longer detected. If a scan
times out, dependencies cannot resolve or coverage changes, mark verification
incomplete. Do not call the finding resolved or claim the deployment was repaired.

Failed validation must retain the original assessment, proposed diff and failure
summary for review. Do not publish a PR labeled as a verified fix. A deliberately
published unverified draft must say what failed and which findings remain.

## Delivery sequence and acceptance

1. **Planner:** generate evidence-backed Maven/Spring Boot recommendations without
   edits. Test direct/property/parent/BOM ownership, grouped transitive fixes,
   withdrawn or missing fixes, candidates, stale reports and private metadata failure.
2. **Maven editor:** apply only supported declarations in an isolated worktree.
   Preserve XML structure/comments and unrelated changes; reject ambiguous edits.
3. **Verification:** run authorized resolution/tests/rescan. Test partial failure,
   unchanged vulnerability, new findings and successful compatible remediation.
4. **Draft PR adapter:** test the complete plan/apply/verify/publish path with an
   explicitly authorized disposable repository. Verify retry deduplication and
   that no merge/deploy operation exists in the workflow.
5. **Additional editors:** add Gradle, then JavaScript lockfile workflows, then
   Python lockfile workflows, each with its own acceptance tests. Existing scanner
   support does not imply an ecosystem already has a safe updater. Use native
   package managers to regenerate locks rather than editing transitive entries.

Container base-image/digest and other runtime upgrades are later adapters within
this feature, once vendor fixes and declaration ownership are verifiable. Automatic
cluster changes, OS patch installation, speculative framework migrations and
universal ecosystem support are outside the first delivery.

Keep acceptance focused: deterministic fixtures for planner/editor failure cases,
the existing security regressions, and one disposable Maven project with a
confirmed update. Do not rerun unrelated live portfolio/cluster tests for every
documentation change or updater fix.
