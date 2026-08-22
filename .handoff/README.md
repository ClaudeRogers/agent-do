# agent-do handoffs

This directory is generated workflow state. `.manna/` owns status, tracks,
claims, and blockers. Each actionable Manna item owns exactly one Markdown
work order here, and the two are content-bound.

Rules:

- Create work through `agent-do manna create`; do not hand-build parallel
  prompt roots such as `.handoffs/`, `.dev/session-prompts/`, or
  `<campaign>/handoff-prompts/`.
- The Manna item `prompt` field points to a board-wide fixed-width name,
  `.handoff/<NN...>[b<MM...>]-mn-xxxxxx-<slug>.md`, after synchronization.
  Width is at least two digits and expands when the active plan exceeds 99.
- Frontmatter identifies the item, track, source, base commit, scope, inputs,
  and SHA-256 binding for the complete document.
- Edit a work order, then run `agent-do manna handoff seal mn-xxxxxx` before
  claiming it. A claim fails closed on any unsealed change.
- Board state stays in Manna. The handoff contains scope, authority,
  deliverables, and verification, never a second backlog.
- Priority lives in `.manna/handoff-order.yaml`. Run `agent-do manna sync`
  after board changes; never hand-maintain numbered filenames or this index.
- A bare numbered filename is safe to launch. `bMM...` means the item is held
  until that numbered priority closes. The full dependency truth remains
  `blocked_by`.
- Completed pairs return to unnumbered sealed history on sync, so no numbered
  filename advertises work that is already done.
- Commit `.manna/workflow.yaml`, `.manna/handoff-order.yaml`,
  `.manna/issues.jsonl`, and `.handoff/`.

## Generated index

| Priority | Manna ID | Status | Full blocker list | Handoff |
| ---: | --- | --- | --- | --- |
| 01 | `mn-90b694` | open | none | `.handoff/01-mn-90b694-moon-trunk-a-gh-issue-verbs-create-assign-label-list-close-comme.md` |
| 02 | `mn-807f18` | open | none | `.handoff/02-mn-807f18-moon-trunk-b-manna-floor-claim-policy-gh-issue-metadata-sync-git.md` |
| 03 | `mn-c3145f` | open | none | `.handoff/03-mn-c3145f-moon-trunk-c-agent-do-attest-stamp-verify-doctor.md` |
| 04 | `mn-404dd7` | blocked | `mn-90b694`, `mn-807f18`, `mn-c3145f` | `.handoff/04b03-mn-404dd7-moon-trunk-d-policy-engine-init-show-check-install-org-scoping.md` |
| 05 | `mn-f1604f` | blocked | `mn-404dd7` | `.handoff/05b04-mn-f1604f-moon-trunk-e-ambient-hooks-board-injection-auto-claim-floor-nudg.md` |
| 06 | `mn-613088` | blocked | `mn-807f18`, `mn-404dd7` | `.handoff/06b04-mn-613088-moon-trunk-f-policy-board-render-notify-rules-claim-conflict-unb.md` |
| 07 | `mn-54cec0` | blocked | `mn-404dd7`, `mn-f1604f` | `.handoff/07b05-mn-54cec0-moon-trunk-g-vid-adoption-pass-newco-portable-spec-policy-yaml-1.md` |
| 08 | `mn-a45739` | open | none | `.handoff/08-mn-a45739-companion-agent-do-dictate-the-chair-s-ears-wispr-class-streamin.md` |
| 09 | `mn-b17dc6` | open | none | `.handoff/09-mn-b17dc6-companion-p1-security-voice-speak-replace-eval-d-shell-string-wi.md` |
| 10 | `mn-ec44be` | open | none | `.handoff/10-mn-ec44be-charter-law-5-organ-parked-eval-redraw-fresh-context-agreement-c.md` |
| 11 | `mn-2ac590` | open | none | `.handoff/11-mn-2ac590-charter-law-2-nudge-sessionend-warns-when-substantial-work-dies-u.md` |
| 12 | `mn-e0d107` | open | none | `.handoff/12-mn-e0d107-harness-context-redesign-unify-context-zpc-ledger-the-memory-hem.md` |
| 13 | `mn-c2dc8b` | open | none | `.handoff/13-mn-c2dc8b-harness-undocumented-verbs-promote-help-only-verbs-into-registry.md` |
| 14 | `mn-96415d` | open | none | `.handoff/14-mn-96415d-harness-doc-reference-scan-scope-archive-noise-and-cross-board-r.md` |
| 15 | `mn-194972` | open | none | `.handoff/15-mn-194972-harness-family-re-org-audit-sweep-the-96-bundled-tools-for-famil.md` |
| 16 | `mn-9dbb48` | open | none | `.handoff/16-mn-9dbb48-harness-media-family-surface-agent-do-media-with-makemkv-handbra.md` |
| 17 | `mn-b8359d` | open | none | `.handoff/17-mn-b8359d-install-sh-warn-when-an-installed-wrapper-has-no-settings-regist.md` |
| 18 | `mn-010cd0` | open | none | `.handoff/18-mn-010cd0-zpc-write-nudge-misreads-a-bound-worktree.md` |
| 19 | `mn-6be265` | open | none | `.handoff/19-mn-6be265-zpc-security-a-tracked-zpc-store-injects-a-repo-s-own-text-as-pr.md` |
| 20 | `mn-b7cb18` | open | none | `.handoff/20-mn-b7cb18-quantities-the-authority-does-not-know-the-model-it-runs-on-clau.md` |
| 21 | `mn-a8337a` | open | none | `.handoff/21-mn-a8337a-suggest-project-walks-the-whole-tree-to-answer-one-yes-no.md` |
| 22 | `mn-43932b` | open | none | `.handoff/22-mn-43932b-brief-contract-v2-verb-labels-scope-state-sentence-adopted-panel.md` |
| 23 | `mn-f12284` | open | none | `.handoff/23-mn-f12284-harness-zpc-write-nudge-attributes-shared-checkout-drift-to-a-re.md` |
| 24 | `mn-9668e9` | open | none | `.handoff/24-mn-9668e9-ci-triage-anchor-the-429-transient-hint-changelog-notes-the-gate.md` |
| 25 | `mn-3086f2` | open | none | `.handoff/25-mn-3086f2-docs-estate-wide-refresh-to-as-is-state-readme-integration-archi.md` |
| 26 | `mn-8b4a1c` | open | none | `.handoff/26-mn-8b4a1c-tests-suite-can-hang-forever-on-the-bootstrap-gui-dialog-pin-age.md` |
| 27 | `mn-ee7d1e` | open | none | `.handoff/27-mn-ee7d1e-tests-record-ages-fails-in-a-worktree-when-the-primary-zpc-store.md` |
| 28 | `mn-2521d5` | in_progress | none | `.handoff/28-mn-2521d5-dpt-fix-false-positive-generators-and-honesty-defects.md` |
| 29 | `mn-d2d67b` | open | none | `.handoff/29-mn-d2d67b-manna-done-handoffs-retire-to-handoff-archive-root-is-the-live-p.md` |
| 30 | `mn-040aae` | blocked | `mn-d2d67b` | `.handoff/30b29-mn-040aae-manna-estate-wide-handoff-debris-cleanup-pre-structure-work-orde.md` |
| 31 | `mn-386f70` | open | none | `.handoff/31-mn-386f70-harness-agent-substack-draft-publish-essays-through-substack-s-e.md` |
