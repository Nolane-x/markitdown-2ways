# Phase G Office Deep Style + Geometry Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deepen MarkItDown 2Ways Office editing with verified run-level text styling for conservative DOCX/PPTX text structures and verified PPTX shape geometry mutation, without weakening existing source-preservation guarantees.

**Architecture:** Reuse the existing `set_text_style` and `move_resize` edit vocabulary. Readers advertise capabilities only for native structures with authoritative locators and a bounded mutation model; writers preflight complete edit payloads, patch only the target OOXML subtree, and verifiers compare both semantic/style/geometry readback and untouched native subtrees. Existing `replace_text`, alt-text, table-cell, XLSX and no-op paths must remain unchanged.

**Tech Stack:** Python 3.10–3.13, `lxml`, `python-docx`, `python-pptx`, existing `DocumentIR`/capability kernel/OOXML package preservation layer, pytest, pre-commit.

**Spec:** `docs/superpowers/specs/2026-09-11-markitdown-2ways-full-parity-program-design.md`

## Global Constraints

- No silent corruption: unsupported or ambiguous style/geometry mutations fail closed before output is written.
- Preserve untouched package members byte-for-byte and untouched native subtrees canonically.
- Unknown/unadvertised capabilities remain read-only.
- No paragraph insertion/removal, slide insertion/removal, theme/master mutation, SmartArt, macros, OLE or external-workbook mutation in this tranche.
- `set_text_style` changes only explicitly supplied direct-style fields on one existing run; it must not synthesize inherited/theme semantics.
- Supported style fields are `bold`, `italic`, `underline`, `font_size_pt`, `font_family`, and `color` when the native format can represent the value locally.
- PPTX `move_resize` is limited to non-group slide/notes shapes with an authoritative transform and positive width/height; rotation is preserved unchanged in this tranche.
- No group-child coordinate rewriting in the first geometry tranche.
- Full Python 3.10–3.13 package CI, OCR 3.10–3.13, pre-commit, exact-head verification and synthetic-merge-tree verification are required before merge/release.

---

## File Structure

### Shared edit validation
- Create `packages/markitdown/src/markitdown/twoways/ir/style_edits.py` for strict run-style payload validation.
- Create `packages/markitdown/src/markitdown/twoways/ir/geometry_edits.py` for strict bounded move/resize validation.
- Test with `packages/markitdown/tests/twoways/test_style_edits.py` and `test_geometry_edits.py`.

### DOCX style mutation
- Modify `_text_extract.py` and `structures.py` to classify safe style targets and advertise `set_text_style` through `twoways.capabilities.v1`.
- Create `_style_patch.py` to patch one authoritative run locally.
- Modify `_writer_apply.py`, `_verify_native.py`, and `verify.py` for preflight, mutation and preservation/readback verification.
- Add `test_docx_style_patch.py`.

### PPTX style + geometry mutation
- Modify `text.py` and `shapes.py` to classify/advertise safe targets.
- Create `style.py` and `geometry.py` for local DrawingML mutation.
- Modify `writer.py` and `verify.py` for preflight and verification.
- Add `test_pptx_style_patch.py` and `test_pptx_geometry_patch.py`.

### Documentation
- Modify `TWOWAYS.md` with the v0.4.0 capability boundary and typed-edit examples.

---

### Task 1: Strict shared style edit validation

**Files:**
- Create: `packages/markitdown/src/markitdown/twoways/ir/style_edits.py`
- Test: `packages/markitdown/tests/twoways/test_style_edits.py`

**Interfaces:**
- Produces `SUPPORTED_TEXT_STYLE_FIELDS: frozenset[str]`.
- Produces `validate_text_style_update(payload: TextPayload, raw: object) -> tuple[int, dict[str, object], dict[str, object]]` returning `(run_index, old_direct_style, new_direct_style)`.

- [ ] Write RED tests for boolean/out-of-range run indices, unknown fields, invalid colors/font sizes, stale `old_style`, and valid sparse updates.
- [ ] Run `pytest packages/markitdown/tests/twoways/test_style_edits.py -q` and confirm RED because the module is absent.
- [ ] Implement exact-type validation, finite positive font sizes, `#RRGGBB` colors, non-empty font families, booleans for bold/italic, and canonical underline validation.
- [ ] Run focused tests GREEN.
- [ ] Commit `feat: validate text style edits`.

### Task 2: DOCX direct run-style patching

**Files:**
- Create: `packages/markitdown/src/markitdown/twoways/formats/docx/_style_patch.py`
- Modify: `_text_extract.py`, `structures.py`, `_writer_apply.py`
- Test: `packages/markitdown/tests/twoways/test_docx_style_patch.py`

**Interfaces:**
- Produces `patch_docx_run_style(paragraph_element, *, run_index: int, old_style: Mapping[str, object], new_style: Mapping[str, object]) -> None`.
- Unsupported reason: `docx.text.ambiguous_run_layout`.

- [ ] Write RED tests proving a single simple run can change bold/italic/underline/font size/family/color while sibling run XML/text remains identical.
- [ ] Add fail-closed tests for duplicate `w:rPr`, unsupported native children, stale old style and non-advertised structures.
- [ ] Implement local `w:rPr` mutation preserving unrelated properties and ordering; create `w:rPr` only for otherwise simple unambiguous runs.
- [ ] Advertise `set_text_style` using `twoways.capabilities.v1` while retaining legacy metadata during v0.x.
- [ ] Wire `_writer_apply._apply_edit` through shared validation and authoritative paragraph/run resolution.
- [ ] Run focused DOCX style/text/table suites GREEN.
- [ ] Commit `feat: add safe docx run styling`.

### Task 3: DOCX style verification

**Files:**
- Modify: `_verify_native.py`, `verify.py`
- Test: extend `test_docx_style_patch.py`

- [ ] Write a RED round-trip test where style changes but text is identical; current verifier must not treat `set_text_style` as semantic-text replacement.
- [ ] Add style readback by target run index and compare exact expected direct-style map.
- [ ] Normalize only supported edited `w:rPr` fields when comparing the target native subtree; all other XML remains required-identical.
- [ ] Run DOCX verifier/reopen/unrelated-subtree tests GREEN.
- [ ] Commit `test: verify docx style preservation`.

### Task 4: Strict shared geometry edit validation

**Files:**
- Create: `packages/markitdown/src/markitdown/twoways/ir/geometry_edits.py`
- Test: `packages/markitdown/tests/twoways/test_geometry_edits.py`

**Interfaces:**
- Produces `validate_move_resize(current: Geometry | None, raw: object) -> Geometry`.
- Payload fields: `x`, `y`, `width`, `height`; values finite numeric, width/height strictly positive; rotation changes rejected.

- [ ] Write RED tests for bools, NaN/inf, non-positive dimensions, missing geometry, unsupported rotation and valid partial updates.
- [ ] Implement exact validation preserving unspecified coordinates, unit and rotation.
- [ ] Run focused tests GREEN.
- [ ] Commit `feat: validate geometry edits`.

### Task 5: PPTX direct run-style patching

**Files:**
- Create: `packages/markitdown/src/markitdown/twoways/formats/pptx/style.py`
- Modify: `text.py`, `shapes.py`, `writer.py`
- Test: `packages/markitdown/tests/twoways/test_pptx_style_patch.py`

**Interfaces:**
- Produces `patch_text_run_style(shape_element, *, run_index: int, old_style: Mapping[str, object], new_style: Mapping[str, object]) -> None`.
- Unsupported reason: `pptx.text.ambiguous_run_layout`.

- [ ] Write RED tests for simple text boxes/title shapes with multiple runs.
- [ ] Add fail-closed tests for fields/breaks, duplicate/malformed run properties, stale old style and unsupported values.
- [ ] Implement direct DrawingML `a:rPr` patching preserving unrelated attributes/children and text.
- [ ] Add capability metadata only for safe run layouts.
- [ ] Wire writer application with shared payload validation.
- [ ] Run focused PPTX style/text/table suites GREEN.
- [ ] Commit `feat: add safe pptx run styling`.

### Task 6: PPTX non-group move/resize

**Files:**
- Create: `packages/markitdown/src/markitdown/twoways/formats/pptx/geometry.py`
- Modify: `shapes.py`, `writer.py`
- Test: `packages/markitdown/tests/twoways/test_pptx_geometry_patch.py`

**Interfaces:**
- Produces `patch_shape_geometry(shape_element, *, current: Geometry, target: Geometry) -> None`.
- Writable only for non-group shapes with exactly one authoritative transform containing exactly one offset and extent.
- Unsupported reasons: `pptx.geometry.ambiguous_transform`, `pptx.geometry.group_coordinate_space`.

- [ ] Write RED test moving/resizing a simple textbox/picture while preserving text/resource/style/rotation.
- [ ] Write fail-closed tests for groups, missing/duplicate transforms, non-positive extents and rotation attempts.
- [ ] Implement native transform patch changing only `x`, `y`, `cx`, `cy`.
- [ ] Advertise `move_resize` only on safe nodes and wire writer validation/application.
- [ ] Run geometry + existing PPTX round-trip suites GREEN.
- [ ] Commit `feat: add safe pptx move resize`.

### Task 7: PPTX style/geometry verification

**Files:**
- Modify: `packages/markitdown/src/markitdown/twoways/formats/pptx/verify.py`
- Test: extend style/geometry tests.

- [ ] Write RED verifier tests for each operation.
- [ ] Dispatch expected readback by edit type instead of forcing style/geometry edits through `node_semantic_text`.
- [ ] Compare target `TextRun.style.direct` or `Geometry` exactly after re-read.
- [ ] Normalize only edited `a:rPr` fields or transform coordinates for target-subtree checks.
- [ ] Run full PPTX verifier/reopen/native-preservation suites GREEN.
- [ ] Commit `test: verify pptx style geometry preservation`.

### Task 8: Capability migration and docs

**Files:**
- Modify: DOCX/PPTX reader metadata and `TWOWAYS.md`
- Test: capability/public-import/serialization suites.

- [ ] Add RED capability-report tests for safe vs unsafe Office fixtures.
- [ ] Encode deterministic `twoways.capabilities.v1` declarations without changing `DocumentIR` schema version.
- [ ] Document typed-edit payloads, fidelity boundary and exclusions.
- [ ] Run capability/public-import/serialization tests GREEN.
- [ ] Commit `docs: document office deep editing`.

### Task 9: Final hardening and release gate

- [ ] Run focused all-2Ways tests and fix only evidence-backed failures.
- [ ] Run full package suite on Python 3.10, 3.11, 3.12 and 3.13.
- [ ] Run OCR matrix 3.10–3.13 and pre-commit.
- [ ] Review changed-file diff for scope leaks, temporary workflows and unrelated rewrites.
- [ ] Verify exact PR head and GitHub synthetic merge commit/tree.
- [ ] Merge with expected-head lock only after all gates are green.
- [ ] Verify actual merge tree equals tested synthetic tree before tagging/releasing v0.4.0.
