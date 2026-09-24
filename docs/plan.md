# Anno 2.0 implementation and acceptance

Updated 2026-09-23. Sources: [developer specification](220926/dev-read.md), [user guide](220926/user-read.md), [normative contract](220926/implementation-contract.md), and [CLI contract](../TOOL_CONTRACT.md).

## Phase 1 — Runtime and project foundation

Implemented: package/entrypoint; non-destructive init with four skill roles and packaged schemas; strict YAML class mapping, JSON config and manifest validation; centralized request/readiness guards; canonical path containment, symlink rejection and duplicate label-path detection. Runtime dependencies are installed only in repository `.venv`.

Verified: editable installation; init preservation; doctor success/error schema; invalid configuration, YAML, classes and missing resources. Missing model is not an error; uncompiled anno-class is an explicit alignment warning.

## Phase 2 — Labeling, rendering and review

Implemented: exact hierarchical cell math with ranges/lists, global endpoint comparisons and outward pixel rounding; labeled coarse/subgrids; native select preserving the selected coordinate level; margin-aware visual/inspect with bbox outlines; class names/indexes in overview; explicit negative labels; content-bound verify tokens for add/update; stable label/review queues with findings; pixel geometry audit; merged visual findings; explicit approval with stale-audit checks and archived issue history.

Verified: geometry boundaries, malformed/missing inputs, no-clamp behavior, repeat audit preservation, lifecycle and approval gates, queue order/exhaustion, verification binding, render artifact pixels/dimensions and absence of label/state mutations. Synthetic grid output was also visually inspected; label sizing now adapts to available cell space and fails explicitly when coordinates cannot fit.

## Phase 3 — Integrity and concurrent writers

Implemented: POSIX advisory project locks, fsync/atomic replace, label+manifest replay journal, `anno repair`, and fail-closed behavior while recovery is pending. No automatic fallback to empty labels or replacement of corrupt state.

Verified: concurrent issue writers preserve all findings; two concurrent adds with the same token cannot both write; simulated I/O failure and a real subprocess exit during commit leave a journal that can be replayed. Readers refuse pending transactions. These tests cover cooperating local processes, not external writers or power-loss behavior on every filesystem.

## Phase 4 — Contracts, package and release checks

Implemented: parser-derived command/option inventory; per-command response schemas; packaged schemas accessible without a project; updated developer/user guides and four skill roles; reusable wheel-install smoke script; GitHub Actions acceptance workflow for Python 3.10/3.12/3.13 (added, not yet run remotely). `--help`/`--version` are documented text exceptions. The current package has no A4OD CLI shim.

Verified locally in `.venv` on Linux/Python 3.10:

- `pytest -q`: **100 passed** (12.82 seconds in the final regression run).
- `ruff check src tests tools` and `ruff format --check src tests tools`: passed.
- Editable install and `anno --version`: passed (`2.0.0`).
- `python -m build --no-isolation`: wheel and sdist built successfully, including all skills/schema/contract resources.
- `python tools/package_smoke.py`: installed the wheel under `.venv`, asserted imports came from that install, then ran the actual entrypoint outside the checkout through init, doctor, every packaged schema, grid, verify, bbox add, audit, overview, inspect, approval and queue exhaustion. Passed.
- `python -m pip check`: no broken requirements.

Synthetic test and package evidence does not certify real-world annotation accuracy, production throughput or other operating systems. The CI matrix has been configured but has not run on the remote service in this session.

## Phase 5 — Agent skill decision guides

Rewrote `anno-align`, `anno-workflow`, `anno-review` and the generated `anno-class` template. All four now have YAML name/description frontmatter and bounded responsibilities. The instructions cover source precedence, material policy ambiguities, actual artifact viewing, progressive grid decisions, partial-image resume, stale verification, uncertain write outcomes, read-only versus state-writing review, legitimate geometry warnings, approval evidence and queue-loop avoidance. They preserve user scope and do not turn ordinary review into permission to edit labels.

Verified with the skill-creator structural validator for the three source skills and all four installed skills. A temporary project confirmed init copies the exact source content, doctor distinguishes the uncompiled scaffold from a compiled sample, and repeated init preserves the project's compiled policy. Structural checks and this installation exercise do not establish real Agent annotation quality; independent visual-task evaluation remains future validation.

## Phase 6 — User-facing CLI presentation

Implemented: explicit `--format text` at every command level, readable nested results and complete error details, stderr for text errors, and contextual next-step hints. JSON remains the default with unchanged response envelopes and exit codes. All commands now have help descriptions, argument guidance and examples. Review progress identifies flagged/modified activity separately from approval. Parser-derived contracts, README and user/normative guides document the presentation extension in [TOOL_CONTRACT.md](../TOOL_CONTRACT.md).

Verified locally: **114 tests passed**, including format placement/override, JSON compatibility, argument/readiness errors, truthful review progress, shell-quoted queue hints, artifact paths, all command help, bbox output, and a subprocess audit failure preserving both input diagnostics and manifest bytes. Ruff lint and formatting checks passed. These checks cover CLI presentation and existing synthetic regression cases; no real-dataset usability study or new package release was performed.

## Phase 7 — Local grid and select readability (2026-09-24)

Implemented per local-render feedback: default auto scale targeting 28 px per subcell, integer overrides 1–4, crop/render metadata, detailed sizing failures, and a hard limit of 8 parent cells for subgrids. Select uses the same scale calculation before margin. Original image coordinates and the global thumbnail behavior are preserved. Parser-generated capabilities and both schema copies are updated; semantics and the edge-inspection workflow are documented in [TOOL_CONTRACT.md](../TOOL_CONTRACT.md) and the user guide.

Verified: 137 tests passed; Ruff lint/format, dependency check, wheel/sdist build and isolated installed-wheel smoke passed. Synthetic 720x1280 acceptance images produce G4 grid 270x480 and select 378x672 at scale 3. Tests cover explicit/default scales, invalid values, original geometry, broad-region rejection, the 8/9-parent threshold and required scale 5 failures. The named feedback images 1.jpg/5.jpg are absent here; real-object edge readability is not verified. Existing testrepo lacks its project lock, so CLI verification used clean temporary projects without migrating testrepo.

## Explicit limits and deferred work

- `infer` remains unavailable as required by the normative gate: no accepted runtime/model/class-mapping/no-overwrite contract yet.
- Tested locally on Linux, Python 3.10. Windows, network filesystems, large-dataset throughput and memory use are not certified.
- Audit pair comparisons remain O(boxes²) per image; manifest writes cover the project state. Benchmark real dataset sizes before setting production throughput targets.
- Queue commands do not claim or reserve images. Multiple agents need work assignment even though writes are serialized safely.
- Render rejects subpixel cells, labels that cannot fit, and excessive cell enumeration; coordinate math itself has no fixed hierarchy-depth limit.
- CLI safeguards do not measure visual annotation quality or prove that an Agent actually inspected an image. Approval remains an explicit caller assertion after audit.
- Existing projects need backup and deliberate resource migration. Init preserves existing config/skills/schema files; it adds missing files only. Old approvals without fingerprints require fresh audit/review.
