# Phase E Safe Table Cell Round Trip Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enable conservative cell-text-only round trips for proven-simple DOCX and PPTX tables through identity Markdown and the existing `update_table_cells` edit type.

**Architecture:** Reader-owned capability discovery marks only simple native tables editable. Markdown import emits deterministic table-cell diffs with table-level and per-cell stale-write evidence. Format-specific table patch modules validate all updates before mutation and reuse existing text allocators; verifiers prove semantic readback and native preservation.

**Tech Stack:** Python 3.10–3.13, dataclasses, python-docx, python-pptx, lxml, pytest, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-09-11-markitdown-2ways-phase-e-safe-table-cell-roundtrip-design.md`

## Global Constraints

- Keep `2ways-v0.1.0` immutable; all work is on `nolane/phase-e-safe-table-cell-roundtrip`.
- Use existing edit type `update_table_cells`; do not add a new public edit type.
- Cell-text-only mutation; no table structure/style/resource mutation.
- Writer must revalidate native compatibility and all updates before applying any mutation.
- Unsupported/ambiguous native structures fail closed.
- No-op archive behavior remains byte-identical.
- Full Python 3.10–3.13 package tests and OCR matrix must remain green.

---

### Task 1: RED — table capability and Markdown typed-edit contract

**Files:**
- Modify: `packages/markitdown/tests/twoways/test_markdown_projection.py`
- Modify: `packages/markitdown/tests/twoways/test_markdown_importer.py`
- Create: `packages/markitdown/tests/twoways/test_table_markdown_roundtrip.py`

**Interfaces:**
- Consumes: `TablePayload`, `ProjectionBlock.editable_capabilities`, `import_identity_markdown()`.
- Produces expected contract: `update_table_cells` payload entries `{row, column, old_text, text}` sorted by coordinate.

- [ ] **Step 1: Write failing projection tests**

Create a representative table node carrying explicit `docx:patch_capabilities=("update_table_cells",)` and assert its identity block advertises only `update_table_cells`; preserve the existing read-only assertion for a table without source capability.

- [ ] **Step 2: Write failing importer tests**

Use a capable table with two data rows. Change one and then multiple cells in identity Markdown. Assert one deterministic edit is emitted with sorted changed-cell entries and complete table-level preconditions. Assert row/column shape changes, malformed separator rows, duplicate/ambiguous cells, and read-only table edits fail closed.

- [ ] **Step 3: Push RED and run CI**

Expected: new tests fail because `render_table()` returns no edit capability and `generate_identity_edits()` has no table branch.

---

### Task 2: GREEN — generic Markdown table projection/import

**Files:**
- Modify: `packages/markitdown/src/markitdown/twoways/markdown/_render_structured.py`
- Modify: `packages/markitdown/src/markitdown/twoways/markdown/_import_helpers.py`
- Modify: `packages/markitdown/src/markitdown/twoways/markdown/_import_edits.py`
- Test: files from Task 1

**Interfaces:**
- Produces: `table_patch_capable(node, payload) -> bool` or equivalent local helper.
- Produces: `parse_table_block(block_text, block, original_node) -> tuple[tuple[str, ...], ...]` with exact source dimensions.

- [ ] **Step 1: Add minimal capability gate**

`render_table()` advertises `("update_table_cells",)` only when node metadata explicitly grants the capability and `TablePayload` is rectangular, span-free, child-node-free, and Markdown-safe (`\r`, `\n`, `|` absent from cell text).

- [ ] **Step 2: Add strict table parser**

Parse only the renderer’s canonical pipe-table structure. Require exactly `rows + 1` lines (header + separator + remaining rows), exact column count, canonical separator cells of `---`, and no ambiguous extra pipe segments. Unescape engine-marker escaping in cell text.

- [ ] **Step 3: Generate deterministic update edit**

Diff source cells by coordinate. Emit one edit containing changed cells sorted `(row, column)`, each with `old_text` and `text`. Build a deterministic operation id from canonical JSON/string material. Set table-level semantic/native locator/old-value preconditions.

- [ ] **Step 4: Run focused tests GREEN**

Run Markdown projection/import tests and ensure pre-existing formatting-only and read-only protections still pass.

---

### Task 3: RED→GREEN — DOCX simple-table native capability and patching

**Files:**
- Create: `packages/markitdown/src/markitdown/twoways/formats/docx/table.py`
- Modify: `packages/markitdown/src/markitdown/twoways/formats/docx/structures.py`
- Modify: `packages/markitdown/src/markitdown/twoways/formats/docx/_writer_apply.py`
- Modify: `packages/markitdown/src/markitdown/twoways/formats/docx/verify.py`
- Modify: `packages/markitdown/src/markitdown/twoways/formats/docx/_verify_native.py`
- Modify: `packages/markitdown/tests/twoways/test_docx_roundtrip.py`
- Create: `packages/markitdown/tests/twoways/test_docx_table_patch.py`

**Interfaces:**
- Produces: `docx_table_patch_compatible(table_element) -> bool`.
- Produces: `patch_docx_table_cells(table_element, payload, updates) -> None` (name may be shortened but semantics must match spec).

- [ ] **Step 1: RED reader/writer tests**

Assert fixture table exposes `docx:patch_capabilities == ("update_table_cells",)`. Replace existing blanket table rejection with successful cell patch tests. Add stale `old_text`, duplicate/out-of-range coordinate, nested/multi-paragraph/merged-complexity rejection tests.

- [ ] **Step 2: Implement native compatibility**

Validate direct `w:tr`/`w:tc` rectangle, exactly one direct `w:p` per cell, only optional `w:tcPr` plus that paragraph, no nested table, and `paragraph_patch_compatible()` for each paragraph.

- [ ] **Step 3: Mark reader capability**

`build_table_node()` records `("update_table_cells",)` only when compatibility passes; otherwise `()`.

- [ ] **Step 4: Implement preflight + patch**

Validate payload schema and all native/source old values before mutation. Then call existing `patch_paragraph_text()` per changed cell. Reject no-op updates.

- [ ] **Step 5: Extend semantic readback verification**

Construct expected complete table semantic text by applying cell updates to the source `TablePayload`; compare to reopened output node.

- [ ] **Step 6: Extend native target normalization**

For `update_table_cells`, blank only text carriers in explicitly changed cells while retaining every other target-table XML attribute/subtree. Verify unchanged cells and wrappers remain canonically identical.

- [ ] **Step 7: Run focused DOCX suite GREEN**

Run reader, table patch, roundtrip, verifier, locator and Markdown vertical-slice tests.

---

### Task 4: RED→GREEN — PPTX simple-table native capability and patching

**Files:**
- Create: `packages/markitdown/src/markitdown/twoways/formats/pptx/table.py`
- Modify: `packages/markitdown/src/markitdown/twoways/formats/pptx/shapes.py`
- Modify: `packages/markitdown/src/markitdown/twoways/formats/pptx/writer.py`
- Modify: `packages/markitdown/src/markitdown/twoways/formats/pptx/verify.py`
- Modify: `packages/markitdown/tests/twoways/test_pptx_roundtrip.py`
- Create: `packages/markitdown/tests/twoways/test_pptx_table_patch.py`

**Interfaces:**
- Produces: `pptx_table_patch_compatible(table) -> bool`.
- Produces: `patch_pptx_table_cells(shape_element, payload, updates) -> None`.

- [ ] **Step 1: RED capability/patch tests**

Assert fixture table advertises table-cell capability, single/multi-cell patches change only `ppt/slides/slide2.xml`, styles/layout remain intact, and invalid/stale/complex updates fail closed.

- [ ] **Step 2: Implement compatibility**

Require exact rectangle and one paragraph per cell with text runs accepted by existing PPTX text patch logic; reject field/line-break or ambiguous carrier structures.

- [ ] **Step 3: Mark reader capability**

Set `pptx:patch_capabilities=("update_table_cells",)` for proven-simple tables.

- [ ] **Step 4: Implement writer preflight + patch**

Resolve exactly one DrawingML table inside the strict table shape. Validate all coordinates/old values first, then apply each cell using existing `patch_text_shape()` on the cell subtree.

- [ ] **Step 5: Extend PPTX verification**

Compute expected table semantic readback. Add target-table native structure comparison that normalizes only changed cell text values while preserving all other table XML.

- [ ] **Step 6: Run focused PPTX suite GREEN**

Run reader, locator, table patch, roundtrip, verifier and Markdown vertical-slice tests.

---

### Task 5: Cross-format hardening and documentation

**Files:**
- Create/modify focused tests under `packages/markitdown/tests/twoways/`
- Modify: `TWOWAYS.md`

**Interfaces:**
- No new public surface beyond the already-existing `update_table_cells` edit type.

- [ ] **Step 1: Add adversarial cases**

Cover Unicode, empty replacement, special Markdown marker-like text, duplicate coordinates, bool-as-int coordinates rejection, incomplete rectangular payloads, malformed Markdown separators, merged/spanned structures, nested DOCX table, multi-paragraph cell, and stale table preconditions.

- [ ] **Step 2: Update docs only after behavior is green**

Change table capability row to `simple cell text patchable`; document payload shape and fail-closed boundary. Keep charts read-only and non-goals explicit.

- [ ] **Step 3: Run formatting/static checks**

Run repository pre-commit workflow and ensure Black 23.7.0 produces no diff.

---

### Task 6: Exact-head CI and integration closure

**Files:** none unless CI reveals a real defect.

- [ ] **Step 1: Run full GitHub Actions on exact PR head**

Require pre-commit SUCCESS and full `packages/markitdown` tests green for Python 3.10, 3.11, 3.12, 3.13, plus OCR matrix SUCCESS.

- [ ] **Step 2: Inspect failures by root cause**

Any failure gets a new RED regression test before production fix. Do not weaken tests to obtain green.

- [ ] **Step 3: Verify scope diff**

Compare branch against `main`; only Phase E code/tests/docs may change.

- [ ] **Step 4: Finish branch**

Use `superpowers:finishing-a-development-branch`. Merge only after fresh exact-head evidence. Do not overwrite or retag v0.1.0.
