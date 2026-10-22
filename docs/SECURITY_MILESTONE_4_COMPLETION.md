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
