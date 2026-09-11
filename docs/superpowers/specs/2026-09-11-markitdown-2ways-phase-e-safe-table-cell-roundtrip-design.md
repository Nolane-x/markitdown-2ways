# MarkItDown 2Ways Phase E — Safe Table Cell Round Trip Design

## Status

Approved for implementation on the post-v0.1.0 branch. This phase extends the existing conservative round-trip engine without changing the released `2ways-v0.1.0` tag.

## Goal

Make simple DOCX and PPTX tables editable through the existing `DocumentIR -> identity Markdown -> typed edits -> native document` path while preserving the project’s fail-closed, minimal-patch fidelity model.

## Scope

Phase E enables the already-defined `update_table_cells` edit type for **cell text only**. It does not add or remove rows, columns, tables, cells, merges, relationships, resources, borders, fills, dimensions, styles, formulas, drawings, fields, or any other structural/native feature.

Supported vertical slice:

```text
DOCX/PPTX native table
  -> TablePayload
  -> identity Markdown table
  -> update_table_cells
  -> native cell text patch
  -> semantic + native preservation verification
```

Charts remain read-only. Complex tables remain read-only.

## Edit contract

`update_table_cells` targets exactly one table node. Its payload is:

```python
{
    "cells": [
        {
            "row": 1,
            "column": 1,
            "old_text": "38%",
            "text": "42%",
        }
    ]
}
```

Rules:

- `row` and `column` are non-negative integers and must be within the source table bounds.
- A coordinate may occur at most once in one edit.
- `old_text` and `text` are strings.
- `old_text` must equal both the source `TablePayload` cell value and the native cell value immediately before patching.
- At least one cell must be present.
- A no-op cell update (`old_text == text`) is rejected as invalid edit input rather than silently accepted.
- The edit carries the existing table-level preconditions: semantic digest, native locator digest, and expected old semantic table value.

This gives two independent stale-write defenses: table-level source identity plus per-cell old-value authority.

## Simple-table eligibility

A table is patchable only when all generic and format-specific conditions are proven by the reader.

### Generic eligibility

- `rows > 0` and `columns > 0`.
- Exactly `rows * columns` cells exist.
- Every coordinate in the rectangular grid appears exactly once.
- Every cell has `row_span == 1` and `column_span == 1`.
- Every cell has no child `node_ids`.
- Cell text is identity-Markdown-safe for v1: it contains no `\r`, `\n`, or unescaped `|` character.

### DOCX eligibility

The native `w:tbl` must have exactly the IR row/column shape. Every patchable `w:tc` must:

- contain no nested table;
- contain exactly one direct `w:p` text paragraph (plus optional `w:tcPr`);
- contain no unknown direct child structures;
- have a paragraph accepted by the existing `paragraph_patch_compatible()` logic;
- therefore inherit the existing rules that reject fields, unsupported run carriers, ambiguous hyperlink contexts, duplicate property containers, and foreign namespaces.

The reader records `docx:patch_capabilities=("update_table_cells",)` only when the whole table passes.

### PPTX eligibility

The native table shape must be a single DrawingML table with the IR row/column shape. Every cell must:

- have exactly one paragraph in its text frame;
- contain only run structures already accepted by the existing PPTX text patch machinery;
- contain no line-break or field carrier that would make text redistribution ambiguous.

The reader records `pptx:patch_capabilities=("update_table_cells",)` only when the whole table passes.

## Markdown projection and import

`render_table()` continues to emit ordinary Markdown tables. The editable capability is exposed only if the source node metadata explicitly contains `update_table_cells` in the DOCX or PPTX patch-capability tuple and the `TablePayload` is generically simple.

Identity import parses the exact rectangular Markdown table shape. It must preserve:

- row count;
- column count;
- separator-row structure;
- cell coordinate identity.

Changing table structure, malformed Markdown, pipe-induced ambiguity, or changing a read-only table fails closed.

For an editable table, the importer diffs parsed cell text against the source `TablePayload`. It emits one deterministic `update_table_cells` operation containing only changed cells, ordered by `(row, column)`. Each entry includes `old_text` and `text`.

The operation ID is deterministic over the canonical changed-cell payload.

## DOCX native patching

A dedicated `formats/docx/table.py` owns table compatibility checks, cell resolution, payload validation, and cell text patching.

The writer:

1. validates the target is a `TablePayload` node;
2. validates normal edit preconditions;
3. requires reader-declared `docx:patch_capabilities` to contain `update_table_cells`;
4. resolves the table using the existing strict table locator;
5. re-validates native table shape and patch compatibility at write time;
6. validates every requested coordinate and `old_text` before mutating anything;
7. plans all updates first, then applies them, preventing partial mutation on a later validation failure;
8. delegates each single-paragraph text mutation to the existing DOCX paragraph allocator so run formatting and hyperlink boundaries stay protected.

## PPTX native patching

A dedicated `formats/pptx/table.py` owns table compatibility checks, native cell resolution, payload validation, and patching.

The writer resolves the existing table graphic-frame shape using the strict shape locator, finds exactly one DrawingML table, re-validates shape/compatibility, validates all edits first, then applies each cell update through the existing PPTX text allocator against the cell subtree.

No table shape reconstruction is allowed.

## Verification

### Semantic verification

After reopening the patched file, verification compares the complete table semantic text against the source table plus the requested cell updates. It does not treat `payload["cells"]` as a scalar expected value.

Unedited nodes retain their existing semantic-digest check.

### Native verification

DOCX native verification normalizes only the text carriers of changed table cells when comparing the edited target table. All other XML in the table — table properties, row properties, cell properties, untouched cells, paragraph/run wrappers, drawings, and relationships — must remain canonically identical.

PPTX verification adds equivalent target-table structure checking: only text carrier values in the explicitly changed cells may differ. Existing unrelated-shape subtree verification remains active.

Package inventory, untouched package members, relationship parts, media bytes, reopen oracle, and no-op byte identity remain unchanged.

## Failure behavior

The implementation fails closed with `UnsupportedEditError`, `PatchPreconditionError`, `MarkdownImportError`, or `RoundTripVerificationError` as appropriate for:

- complex/merged/incomplete tables;
- nested DOCX tables;
- multi-paragraph cells;
- field/line-break/unsupported text carriers;
- malformed Markdown tables;
- row/column count changes;
- duplicate/out-of-range update coordinates;
- stale `old_text`;
- stale table semantic/native-locator preconditions;
- native shape drift between read and write;
- unrelated native subtree mutation;
- changed relationships/media/package members.

No best-effort fallback rebuild is permitted.

## Testing requirements

Tests must prove RED before production code and cover at minimum:

- identity projection advertises `update_table_cells` only for proven-simple native DOCX/PPTX tables;
- identity Markdown single-cell and multi-cell diff generation;
- deterministic edit IDs and sorted cell updates;
- structure-change rejection;
- stale and forged update rejection;
- DOCX native single- and multi-cell patches;
- PPTX native single- and multi-cell patches;
- untouched run/cell/table formatting preservation;
- only the owning XML member changes;
- semantic readback of the full updated table;
- complex/merged/multi-paragraph/nested tables remain read-only;
- Unicode and empty-string replacement;
- no-op patch remains byte-identical;
- full Python 3.10–3.13 and OCR CI remains green.

## Non-goals

Phase E does not implement table creation/removal, row/column insertion/deletion, merge/unmerge, style mutation, dimensions, formulas, chart mutation, image/resource replacement, tracked changes, comments, or broad Office automation APIs.

## Release discipline

Work lands through a new PR from `nolane/phase-e-safe-table-cell-roundtrip`. The v0.1.0 tag remains immutable. A maintenance/minor release is considered only after exact-head CI is green and the final merge tree is verified.