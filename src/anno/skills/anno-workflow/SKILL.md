---
name: anno-workflow
description: Annotate images or repair YOLO boxes in an Anno project using hierarchical grids and verified CLI mutations. Use for new labeling, correcting flagged images, or resuming an identified annotation task. Requires project class rules; use anno-review for review-only requests.
---

# Annotate and repair with Anno

Complete the requested images using the agreed class policy, visible image evidence, and CLI-validated mutations. Keep a record of the current image and unfinished objects so an interrupted run can resume without losing work.

## Prepare and choose work

Work at the data project root. Run `anno doctor`; resolve reported setup errors before writing labels. If `class_compiled` is false, use the sibling `anno-align` skill. Read `.anno/skills/anno-class/SKILL.md` and the relevant `label.md` rules even when doctor reports ready. If an encountered case exposes a material gap, return to alignment for that case; do not guess a class or exclusion rule.

Use `anno capabilities` or command `--help` when syntax is uncertain. All operational responses are JSON; check both the exit code and `ok`. Quote paths and cell expressions in shell commands. Do not invoke unavailable `infer` or edit label text files.

Respect the user's scope:

- For an explicit image or subset, process only those paths. A project-wide queue can point outside that subset.
- For a dataset-wide task, **MUST** use `anno label next` before selecting the
  first image. Process only the returned `task`, read all returned `issues`,
  and call `anno label next` again after finishing that image before selecting
  another one. Do not enumerate image files directly as a substitute for the
  queue unless the queue is unavailable and the limitation is reported.
- `anno label next` prioritizes flagged images, then missing label files. A
  `done` response means the queue selected no further work; it does not prove
  that every existing label is complete or correct.
- On resume, return to the last unfinished image before using `next`. An existing label file can contain only part of an image's objects; the queue does not track annotation completeness.

Queue selection does not reserve an image. Use an existing assignment scheme when multiple workers are active; do not edit a path owned by another worker. Serialized CLI writes do not make duplicate human/Agent decisions safe.

## Inspect before deciding

Open each returned `artifact_path` with an image-viewing tool. Merely running a renderer or receiving a verification ID does not validate the object's identity, presence, or box quality. If image viewing is unavailable, report that limitation and leave visual decisions unconfirmed.

For a new image, inspect the whole frame with `label grid` or `label overview`. Scan it systematically, including borders, small targets and partially occluded regions. Keep an inventory of candidate instances under the project rules; avoid adding the same object twice as you move between crops.

For a flagged or partially labeled image, begin with `label overview` and `label bbox list`. Read every returned finding, including multiple findings within one issue type. Match each finding to the visible object; historical indexes can shift after deletion. Audit warnings are reasons to inspect, not automatic instructions to remove boxes.

## Refine one candidate

Use the smallest amount of zoom that resolves the decision:

| Tool | Decision it supports |
| --- | --- |
| `label grid IMAGE` | Locate objects on the global A1..H8 grid. |
| `label select IMAGE --cells CELLS --margin 0.20` | Inspect native-resolution boundaries using the current coordinate level. |
| `label grid IMAGE --cells CELLS` | Subdivide each selected parent into a1..h8 when finer localization is useful. |
| `label visual IMAGE --cells CELLS --margin 0.20` | Compare a candidate rectangle against the object on an image without grid lines. |

Coordinates are anchored to the original image. Do not rename a crop's upper-left corner A1. Hierarchy uses `A1-a1`, then `A1-a1-a1`; ranges and comma-separated selections form one enclosing rectangle, not multiple boxes. Create separate annotations for separate instances.

Check all four candidate edges against the agreed visible/full-extent convention. Do not invent hidden boundaries or apply a universal occlusion threshold. If a finer grid cannot fit labels or reaches subpixel resolution, use a coarser grid and native select/visual evidence; report unresolved precision instead of repeatedly issuing the same failing render or switching to direct file edits.

## Verify and write

For each add/update, obtain a fresh token for the exact current image, class and cells. This example illustrates syntax; select the actual class and cells from evidence:

```bash
anno label verify "dataset/images/001.jpg" --class 0 --cells "A1-a1:B2-h8"
anno label bbox add "dataset/images/001.jpg" --class 0 --cells "A1-a1:B2-h8" --verification-id "TOKEN_FROM_VERIFY"
```

For a correction, use `bbox update` with `--index N` and the same candidate arguments/token. Confirm the current index with `bbox list` before index-sensitive edits. Class-only updates still require cells and a matching verification token in this CLI.

A token binds the current label content as well as the image, class mapping, config and candidate. Any successful label mutation invalidates previously obtained tokens for that image; do not pre-verify a batch and reuse those tokens after the first write. Geometric verification is not a visual endorsement.

Use `bbox delete IMAGE --index N` only for a confirmed unwanted annotation. Re-read indexes after deletion. Use `bbox empty IMAGE` only after inspecting the complete image and confirming it has zero target instances under the policy. Missing labels, unreadable images, uncertainty and unfinished work are not negative images.

After changes, render a fresh overview and inspect changed boxes. Check for missing targets, duplicate instances, class errors and boundary errors. Finish the current image's object inventory and all applicable findings before asking the queue for another image; a first edit changes flagged to modified, so the queue can stop returning an image whose repair is still incomplete.

## Recover without duplicating work

| Result or interruption | Next action |
| --- | --- |
| `VERIFICATION_MISMATCH` | Relist current boxes and inspect changed state, then verify the still-intended candidate again. Do not replay the old token. |
| `INVALID_ARGUMENT` or invalid cells/index | Correct the named input using help/current bbox list; retry only after the cause is understood. |
| Missing/corrupt project inputs or malformed labels | Report the affected path and error. Do not fabricate data, reset the project or repair label text outside the CLI. |
| `RECOVERY_REQUIRED` | Run `anno repair` to finish the existing journal, then doctor and bbox list. Reconcile the completed transaction before issuing another mutation. If repair fails, stop further writes and report the error. |
| Lost response, timeout or interrupted mutation | Read current boxes/state first. If a journal is pending, recover it. Do not assume the write failed and blindly add the object again. |

Never read or edit `.anno/manifest.json` directly. Never lower audit thresholds or delete valid objects just to make the dataset pass.

## Complete or hand off

For an end-to-end annotation-and-review request, continue with sibling `anno-review` after the requested labeling is finished. For labeling-only work, report which images were completed or modified and which still need review. Do not expand a limited task into a dataset-wide review.

Report actual processed paths/counts, unresolved cases and the next action. `label next` returning `done: true` means no flagged/missing-label work is selected; it does not prove all existing labels are complete or all images approved. Preserve the exact current path and remaining objects/findings in any interruption handoff.
