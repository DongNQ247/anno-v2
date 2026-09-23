---
name: anno-align
description: Clarify or revise an Anno project's object classes and labeling rules, then compile its anno-class skill. Use before first annotation, when project guidance changes, or when an observed case exposes a material ambiguity. Does not label images or approve a dataset.
---

# Align project labeling rules

Produce `.anno/skills/anno-class/SKILL.md` as an actionable, project-specific decision guide. It must explain what counts as an instance, which class to use, and where its box belongs, using rules grounded in project sources and the user's decisions.

## Establish the current agreement

Work from the data project root. Read `label.md`, `dataset/data.yaml`, and any existing `.anno/skills/anno-class/SKILL.md`. Respect the requested dataset/subset and decisions already made in the conversation; do not interview the user again about settled rules.

Run `anno doctor`. On failure, read `error.details.errors` and distinguish setup faults from missing business rules. Do not invent class names, replace configuration, or reset project files to make readiness pass. `class_compiled: false` is expected before alignment. `ready: true` checks setup; it does not establish that the labeling policy is complete.

Use these sources for their respective purposes:

- `dataset/data.yaml`: exact class IDs and names. Do not renumber, add or merge classes as a side effect of alignment.
- `label.md` and explicit user decisions: labeling policy. Preserve a more recent explicit decision and record its source; if it conflicts with the current class mapping, identify the mismatch before labeling.
- Existing `anno-class`: previously compiled decisions to preserve or revise, not an authority above the user's instructions.
- Example images/labels: evidence of intended practice. An example can reveal a conflict, but does not silently override written rules.

## Resolve only ambiguities that change labels

Inspect available examples with an image-viewing tool. A file path or a successful render is not visual evidence. Sample contrasting cases when available: clear positives, lookalike negatives, class boundaries, occlusion, truncation at the frame, and small or blurred objects. Do not claim that unseen examples were inspected.

The dataset CLI accepts images only under `dataset/images/`. To use it with supplied `examples/`, make a separate temporary sample project containing copies of those examples and the same class mapping. Keep these copies out of the production dataset. Raw examples may also be viewed directly when no CLI overlay is needed.

Compare the rules and examples against these decisions; ask only about unresolved decisions that affect the actual task:

| Decision | What must be clear |
| --- | --- |
| Class boundary | Observable features separating similar classes; what to do when those features are hidden. |
| Instance boundary | One box per object, group, component or other explicitly defined unit. |
| Inclusion and negatives | Objects to label, lookalikes to exclude, treatment of reflections/screens if relevant. |
| Box extent | Visible extent versus inferred full extent; treatment of disconnected visible parts and image-edge truncation. |
| Visibility and size | Whether occlusion, small size or blur excludes an otherwise valid instance; any thresholds must come from the policy. |
| Ambiguous cases | What can be decided from evidence and what needs human resolution. |

Give the user the concrete disputed case and the alternatives that would change its label. Continue compiling settled sections while awaiting a material answer. Do not invent universal visibility percentages, minimum object sizes, or a default class for uncertainty. Geometry audit thresholds are warning thresholds, not the project's object-inclusion policy.

## Compile the project skill

Update only the project `anno-class` skill unless the user also requested source-policy edits. Preserve unrelated, still-valid project rules. Use this structure, omitting sections with no applicable content:

```markdown
---
name: anno-class
description: Apply this project's agreed object classes and box rules when labeling or reviewing its Anno dataset.
---

# Project labeling rules

## Scope and sources
Project/task, relevant data subset, source paths and policy revision/date.
Record the substance of explicit decisions used to resolve source conflicts.

## Class decisions
For each exact ID/name: include, exclude, observable distinctions from
neighboring classes, and policy-backed examples or counterexamples.

## Instance and box rules
Instance unit, extent convention, occlusion/truncation handling and any
policy-backed size or quality exclusions. State relevant exceptions.

## Uncertainty and unresolved cases
What evidence is needed to decide; which cases must wait for clarification.

## Review checklist
A short checklist derived from this project's actual rules.
```

Use decision rules, not generic descriptions such as “label accurately.” For example, distinguish a class by the agreed visible features instead of simply repeating its name. Include only examples or thresholds supported by the sources. Keep uncertainty explicit rather than making the generated file appear complete.

The scaffold contains the marker ``generated from `label.md` ``; the current doctor uses it to identify an uncompiled skill. Keep the original marker sentence while material policy questions remain. Remove it only when the applicable rules are settled and the generated skill is usable. Retain YAML `name` and `description` in the completed skill. Do not rely on doctor's marker check as a semantic policy validator.

## Finish and hand off

Cross-check every compiled class against `data.yaml`, and each substantive rule against its source. Run `anno doctor` again. Report the skill path, decisions clarified, any unresolved cases, and whether labeling can proceed for the requested scope.

For annotation, hand off to the installed sibling `anno-workflow` skill; for a review request, use `anno-review`. Alignment itself does not change labels, mark issues, approve images or authorize either downstream activity beyond the user's request. Never read or edit `.anno/manifest.json` directly; use the CLI for review state.
