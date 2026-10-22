# Milestone 4 completion scope

Milestone 4 adds runtime and deployment evidence to dependency scans. Maven/Gradle
resolution was added as milestone 2 after the original four-stage plan; remediation
is now milestone 5. This document makes the remaining milestone 4 work explicit.

Acceptance criteria:

- NVD matching evaluates each configuration branch independently. Unsupported
  unrelated product syntax cannot create a Java candidate. Relevant unsupported
  predicates and missing environment prerequisites remain uncertain.
- Observed Eclipse Temurin versions use Adoptium's published vulnerability
  disclosure report (VDR), not Oracle CPE substitution. Preserve vendor report
  provenance, exact version evidence and limitations; never invent fix versions.
- Explicit image and filesystem collection uses installed maintained scanners,
  without executing image code. Retain immutable image identity, JVM release-file
  metadata, OS vendor advisory results and coverage failures separately.
- Explicit Kubernetes collection requires context and namespace. Inspect pod
  image IDs read-only and scan those immutable images. Never persist pod specs,
  environment variables, registry credentials or helper raw diagnostics by default.
- Monitoring retains findings through collector/advisory failures and scope
  changes. Collection execution requires an explicit per-run opt-in.
- Every parameter has examples, helper requirements and scope limitations.
  Automated fixtures cover matching, collectors, vendor data and lifecycle errors;
  real-host acceptance must distinguish live results from test doubles.

Completion does not mean universal vendor coverage, Azure control-plane auditing,
runtime exploitability analysis, or automatic repairs. Imported evidence is not
independent proof of deployment state. Milestone 5 owns remediation/update PRs.

## Host acceptance after v12

The user's v12 run passed 205 automated tests and demonstrated an authenticated,
digest-verified live Adoptium VDR download, observed Temurin JVM release metadata,
and rootfs monitor new/ongoing/unverified retention. Syft also acquired a registry
image and retained its immutable repository digest.

That run exposed a real compatibility bug: Syft 1.55.0 rejects `/dev/null` as a
configuration filename. Collectors now use a private temporary `empty.yaml` for
Syft and Trivy, including Trivy's version probe. Regression tests cover extension,
permissions, cleanup on all exits and an extension-sensitive helper subprocess.
Rerun the v12 rootfs command with the installed Syft binary directly, removing the
wrapper override. Expected advisory uncertainty is distinct from collector failure.

Positive live Kubernetes collection remains deferred because the cluster was
unreachable. A complete remote Trivy image scan remains unaccepted after the
reported Docker Hub transport failure. The macOS JDK-directory scan demonstrated
JVM inventory and Trivy DB metadata; it did not establish positive Linux OS package
or backport matching. Do not report these deferred paths as passed.

The host-specific cron PATH is expected and documented. `--fix-available` is also
already documented in the CLI reference: it keeps findings with published fixes,
so all 17 remain when all 17 have fixes.
