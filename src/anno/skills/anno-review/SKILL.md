---
name: anno-review
description: Audit an Anno dataset and visually assess existing labels against project rules. Use for quality review, investigating geometry warnings, or rechecking modified images before explicit approval. Supports read-only assessment and, when requested, recorded findings or verified repairs.
---

# Review evidence before approval

Separate geometry warnings, visual findings, label repairs and approval. The goal is a defensible verdict for the requested images, with unresolved findings preserved.

## Establish scope and permitted writes

Read `.anno/skills/anno-class/SKILL.md` and relevant `label.md` rules; use sibling `anno-align` if material policy is unresolved. Run `anno doctor` and address readiness errors before proceeding. Doctor does not prove annotation quality.

Honor the user's requested mode:

| Request | Work within scope |
| --- | --- |
| Read-only assessment/report | Use status/next, bbox list and renderers. Do not run audit, mark, repair or bbox mutations: audit itself writes the manifest. Artifacts are the only writes unless the user also prohibited those. |
| Record review findings | Run audit as appropriate, inspect images and mark supported issues. Keep labels unchanged. Approval is appropriate only when requested as part of completing review and the full checklist passes. |
| Review and fix / end-to-end annotation | Repair confirmed problems through sibling `anno-workflow`, then re-audit and visually recheck before approval. |

Explicit target paths take precedence over global queues. `review audit` scans the entire project and has no image/subset option. If project-wide audit is outside the requested write scope, use visual assessment and report that fresh audited approval remains unavailable; do not imply that an image-scoped audit exists.

## Establish geometry evidence

When audit is in scope, run `anno review audit` using the project's agreed configuration. Examine `effective_config`; disabled checks or explicit overrides qualify any claim that geometry was checked. Do not disable checks or loosen thresholds to force approval.

If audit returns `AUDIT_INPUT_ERROR`, read each entry in `error.details.failures`. The failed run commits no new audit state, even for otherwise valid images. Missing labels, invalid class IDs, malformed labels and unreadable images are input problems, not evidence of clean negatives. Do not approve from that failed run. Complete/correct source data only within authorized scope, or report the blocker.

For dataset review, use `review next`: flagged precedes modified, then unreviewed. Read all returned findings. For specific images, inspect those images directly. Neither status nor the queue performs a fresh audit or proves that existing approvals remain current after external file changes.

## Inspect the actual images

Run `review overview IMAGE`, then open its `artifact_path` in an image-viewing tool. Use `bbox list` to obtain current indexes/classes. Run `review inspect IMAGE --index N --margin 0.20` for every box before approving; open the crops at native resolution. Increase margin when more context is needed. Render success is not a visual check.

First scan the whole frame for missing instances, then inspect existing boxes. A crop-only review cannot find targets with no box. If you cannot view the artifacts or cannot resolve the evidence, report the affected images and withhold approval.

| Visual issue | Evidence to check |
| --- | --- |
| `missing_object` | A real target satisfying the project inclusion rules has no matching annotation. |
| `class_mismatch` | Visible distinguishing features contradict the assigned class under the agreed policy. |
| `tightness_error` | Identify which edge cuts into the required extent or includes unjustified space. |
| `occlusion_violation` | Cite the project visibility/extent rule that the box violates; do not invent a percentage. |
| `ghost_object` | An annotation covers a non-target, reflection, shadow or background according to project rules. |

For each geometry warning, inspect the implicated objects: high IoU may represent distinct overlapping instances; containment can be legitimate; a tiny or elongated target can be valid. Out-of-bounds coordinates need comparison with the actual frame boundary. Do not use a warning alone as justification to delete or reshape a correct annotation.

## Record actionable findings

When recording is in scope, use the matching supported visual issue and a concrete message:

```bash
anno review mark "dataset/images/001.jpg" --issue tightness_error --box-index 0 --message "Lower edge cuts off the visible rear wheel; extend to the wheel boundary."
```

Include the observed location, violated rule and needed correction or unresolved evidence. Use `--box-index` only for an existing box; a missing object has no box index. Keep uncertain interpretations distinct from confirmed findings. Do not invent issue codes or disguise a geometry warning as a visual defect merely to store it.

Findings of the same type accumulate; record each distinct problem, not repeated paraphrases of the same finding. Historical indexes can shift after deletions. Open findings remain until explicit approval closes all of them; partial repairs do not resolve the rest automatically.

If fixes are requested, use `anno-workflow` for verified bbox mutations. Reopen the final overview/crops after edits and rerun audit. If a correct box still triggers a legitimate geometry warning, leave it flagged and report the policy/configuration conflict: this CLI has no per-issue waiver, and approval will remain blocked. Do not deform a correct label or silently change the audit policy.

## Approve only with complete evidence

Before `review mark IMAGE --verdict approved --notes TEXT`, establish all of the following for the current image:

- The label exists, including an explicit empty label for a visually confirmed negative image.
- A successful audit reflects the latest image, label, class mapping and config, with no open geometry findings.
- The full frame has been checked for missing instances and every existing box for class, extent, visibility and object validity.
- All previous open visual findings have been checked against the current image and actually resolved; no material ambiguity remains.

Use notes to summarize the observed checks and important resolutions. Approval closes every open issue and archives it. `STALE_AUDIT` requires a fresh audit; reopen changed visual evidence as needed. `OPEN_GEOMETRY_ISSUES` requires resolution or a reported blocker, not a repeated approval attempt. Notes alone are not a substitute for inspection.

## Avoid queue loops and report honestly

`review next` is stable and does not claim, skip or advance an image. In read-only or report-only work, maintain a local list of reviewed target paths; if necessary enumerate image filenames within scope and use per-image commands. Do not mutate state just to advance the queue. Do not call `next` repeatedly expecting it to move past an unresolved flagged image.

For a blocked image, retain its findings, record the path/reason in the handoff, and continue independent in-scope images when possible. An identical failed operation without a relevant change is not progress. If a pending transaction blocks CLI reads, report it in read-only mode; when operational recovery is authorized, run `anno repair`, inspect the recovered state and resume. Never edit the journal, manifest or label text directly.

Conclude with reviewed scope, observed defects, any actual repairs/approvals, unreviewed paths and blockers. Distinguish CLI geometry results from your visual judgments. `label next done`, `review status.progress`, successful rendering and passing software tests are not proof of dataset quality. Claim dataset-wide review complete only when all in-scope images were examined and all required approvals are confirmed.
