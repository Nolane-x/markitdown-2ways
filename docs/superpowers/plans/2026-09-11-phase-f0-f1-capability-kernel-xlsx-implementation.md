# Phase F0/F1 Capability Kernel + XLSX Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a typed capability/diagnostic kernel and a conservative source-preserving XLSX read/edit/write/verify path without weakening the existing DOCX/PPTX safety contracts.

**Architecture:** Keep the existing `DocumentIR` schema version stable by encoding per-node capability declarations in a reserved metadata namespace and exposing typed helpers around that wire form. Add XLSX as a third OOXML format adapter that reuses the existing package/XML safety layer, patches original SpreadsheetML parts directly, and returns output only after semantic and native preservation verification.

**Tech Stack:** Python 3.10–3.13, dataclasses/enums, lxml-safe XML helpers already present in `twoways.ooxml`, `zipfile` via the existing OOXML package layer, pytest, optional openpyxl only for differential tests.

**Spec:** `docs/superpowers/specs/2026-09-11-markitdown-2ways-full-parity-program-design.md`

## Global Constraints

- Do not add editor UI, SaaS, workflow, agent, database or collaboration scope.
- Missing/unknown capabilities default to read-only.
- No writer may mutate output before the full edit set passes preflight.
- Do not use `openpyxl.save()` as the production XLSX mutation path.
- Preserve unrelated OOXML members byte-for-byte whenever the existing package writer contract allows it.
- Formula cells are read-only in the first XLSX tranche.
- Merged-range cells are read-only in the first XLSX tranche.
- Structural sheet/row/column edits are out of scope for v0.3.0 tranche one.
- Python 3.10, 3.11, 3.12 and 3.13 plus pre-commit must be green before merge.
- Exact PR head and the tested synthetic merge tree must be verified before release.

---

## File Structure

### F0 capability kernel

- Create `packages/markitdown/src/markitdown/twoways/capabilities.py`
  - typed capability contracts, metadata parser/encoder and report builder.
- Modify `packages/markitdown/src/markitdown/twoways/__init__.py`
  - stable public exports for capability contracts/helpers.
- Modify `packages/markitdown/src/markitdown/twoways/ir/edits.py`
  - add `update_sheet_cells` to the known edit vocabulary.
- Create `packages/markitdown/src/markitdown/twoways/ir/sheet_edits.py`
  - deterministic spreadsheet cell edit validation independent of OOXML.
- Modify `packages/markitdown/src/markitdown/twoways/ir/__init__.py`
  - export sheet edit helpers only if they are intended public within IR.
- Create `packages/markitdown/tests/twoways/test_capabilities.py`
- Create `packages/markitdown/tests/twoways/test_sheet_edits.py`
- Modify `packages/markitdown/tests/twoways/test_public_imports.py`

### F1 XLSX adapter

- Create `packages/markitdown/src/markitdown/twoways/formats/xlsx/__init__.py`
- Create `packages/markitdown/src/markitdown/twoways/formats/xlsx/model.py`
  - SpreadsheetML namespace/constants and cell-native model helpers.
- Create `packages/markitdown/src/markitdown/twoways/formats/xlsx/package.py`
  - workbook/sheet/relationship discovery on top of shared OOXML package safety.
- Create `packages/markitdown/src/markitdown/twoways/formats/xlsx/cells.py`
  - typed cell extraction, A1 references, shared-string reads and capability decisions.
- Create `packages/markitdown/src/markitdown/twoways/formats/xlsx/reader.py`
  - workbook to `DocumentIR` mapping.
- Create `packages/markitdown/src/markitdown/twoways/formats/xlsx/patch.py`
  - target-cell mutation primitives only.
- Create `packages/markitdown/src/markitdown/twoways/formats/xlsx/verify.py`
  - semantic re-read and native preservation verification.
- Create `packages/markitdown/src/markitdown/twoways/formats/xlsx/writer.py`
  - source lock, preflight, transactional patching, verification and `WriterResult`.
- Modify `packages/markitdown/src/markitdown/twoways/formats/__init__.py`
  - make xlsx adapter package discoverable without polluting root namespace.
- Create `packages/markitdown/tests/twoways/_xlsx_fixtures.py`
- Create `packages/markitdown/tests/twoways/test_xlsx_package.py`
- Create `packages/markitdown/tests/twoways/test_xlsx_reader.py`
- Create `packages/markitdown/tests/twoways/test_xlsx_cell_patch.py`
- Create `packages/markitdown/tests/twoways/test_xlsx_roundtrip.py`
- Create `packages/markitdown/tests/twoways/test_xlsx_hardening.py`
- Create `packages/markitdown/tests/twoways/test_xlsx_public_imports.py`

### Markdown / docs integration

- Modify `packages/markitdown/src/markitdown/twoways/markdown/projection.py`
- Modify `packages/markitdown/src/markitdown/twoways/markdown/_import_edits.py`
  - emit `update_sheet_cells` only for XLSX worksheet tables that are identity-lossless.
- Modify `TWOWAYS.md`
  - capability report API and current XLSX support matrix.

---

### Task 1: Typed capability contracts and strict metadata parsing

**Files:**
- Create: `packages/markitdown/src/markitdown/twoways/capabilities.py`
- Test: `packages/markitdown/tests/twoways/test_capabilities.py`

**Interfaces:**
- Produces: `CapabilityState`, `CapabilityDecision`, `NodeCapabilityProfile`, `CapabilityReasonSummary`, `CapabilityReport`, `capabilities_for_node(node)`, `encode_capabilities(decisions)`, `build_capability_report(document)`.
- Wire key: `twoways.capabilities.v1`.

- [ ] **Step 1: Write failing tests for default read-only behavior and deterministic parsing**

```python
from markitdown.twoways.capabilities import (
    CapabilityState,
    capabilities_for_node,
)
from markitdown.twoways.ir.nodes import Node


def test_missing_capability_metadata_defaults_to_read_only():
    profile = capabilities_for_node(Node(node_id="n1", kind="text"))
    assert profile.node_id == "n1"
    assert profile.decisions == ()
    assert profile.default_state is CapabilityState.READ_ONLY


def test_capability_metadata_is_sorted_by_operation():
    node = Node(
        node_id="n1",
        kind="text",
        metadata={
            "twoways.capabilities.v1": [
                {"operation": "set_text_style", "state": "read-only", "reason_code": "x"},
                {"operation": "replace_text", "state": "writable"},
            ]
        },
    )
    profile = capabilities_for_node(node)
    assert [item.operation for item in profile.decisions] == ["replace_text", "set_text_style"]
```

- [ ] **Step 2: Run focused tests and confirm RED**

Run: `pytest packages/markitdown/tests/twoways/test_capabilities.py -q`

Expected: import/module failure because the capability kernel does not exist.

- [ ] **Step 3: Implement immutable typed contracts and strict parser**

Required rules:

```python
CAPABILITY_METADATA_KEY = "twoways.capabilities.v1"

class CapabilityState(str, Enum):
    WRITABLE = "writable"
    READ_ONLY = "read-only"
    DERIVED = "derived"
```

Reject empty operation names, unknown states, non-string reason codes, duplicate operations and non-mapping constraints. Copy mappings/tuples defensively in `__post_init__`.

- [ ] **Step 4: Add encode/decode round-trip tests**

The encoder must emit operation-sorted plain dictionaries and omit `reason_code` when `None`.

- [ ] **Step 5: Run focused tests GREEN and commit**

Run: `pytest packages/markitdown/tests/twoways/test_capabilities.py -q`

Commit: `feat: add typed capability contracts`

---

### Task 2: Deterministic document capability report

**Files:**
- Modify: `packages/markitdown/src/markitdown/twoways/capabilities.py`
- Test: `packages/markitdown/tests/twoways/test_capabilities.py`

**Interfaces:**
- Consumes: Task 1 typed decisions.
- Produces: `build_capability_report(document: DocumentIR) -> CapabilityReport`.

- [ ] **Step 1: Add RED tests for report counts**

Build a document containing one writable text node, one explicit read-only table node, one derived node and one unspecified node. Assert:

```python
assert report.total_nodes == 4
assert report.writable_nodes == 1
assert report.read_only_nodes == 2
assert report.derived_nodes == 1
assert report.writable_by_operation == {"replace_text": 1}
assert report.reason_counts == {
    "capability.unspecified": 1,
    "docx.table.merged_cells": 1,
    "image.ocr.derived": 1,
}
```

- [ ] **Step 2: Implement deterministic classification**

Classification precedence for a node:

1. any `writable` decision => writable node;
2. otherwise any `derived` decision => derived node;
3. otherwise read-only node.

Unspecified nodes contribute `capability.unspecified`.

- [ ] **Step 3: Verify report mappings/reason summaries are sorted and immutable**

- [ ] **Step 4: Run focused tests GREEN and commit**

Commit: `feat: add capability coverage reports`

---

### Task 3: Stable public capability imports

**Files:**
- Modify: `packages/markitdown/src/markitdown/twoways/__init__.py`
- Modify: `packages/markitdown/tests/twoways/test_public_imports.py`

**Interfaces:**
- Consumes: Task 1/2 symbols.
- Produces: stable `markitdown.twoways` imports.

- [ ] **Step 1: Add RED public-import assertions**

```python
from markitdown.twoways import (
    CapabilityDecision,
    CapabilityReport,
    CapabilityState,
    build_capability_report,
    capabilities_for_node,
)
```

- [ ] **Step 2: Export exactly the typed API and helpers; do not expose internal metadata parser classes**

- [ ] **Step 3: Run public import + capability tests GREEN and commit**

Commit: `feat: expose capability reporting API`

---

### Task 4: Spreadsheet edit vocabulary and validation

**Files:**
- Modify: `packages/markitdown/src/markitdown/twoways/ir/edits.py`
- Create: `packages/markitdown/src/markitdown/twoways/ir/sheet_edits.py`
- Test: `packages/markitdown/tests/twoways/test_sheet_edits.py`

**Interfaces:**
- Produces: `validate_sheet_cell_updates(table: TablePayload, updates: object) -> tuple[dict[str, object], ...]` and `semantic_sheet_values_after_updates(...)`.
- Adds edit type: `update_sheet_cells`.

- [ ] **Step 1: Add RED validation tests**

Test all of:

- empty update list rejected;
- row/column must be integers but not booleans;
- negative and out-of-range coordinates rejected;
- duplicate coordinates rejected;
- `old_value` must match the current typed value stored in cell metadata;
- `value` supports only `str`, `int`, finite `float`, `bool` or `None` in tranche one;
- NaN/Infinity rejected;
- no-op values rejected;
- result sorted by `(row, column)`.

- [ ] **Step 2: Implement pure IR validation without importing XLSX modules**

Cell metadata key used by F1 reader:

```text
cell.metadata["xlsx.typed_value"]
```

- [ ] **Step 3: Add deterministic semantic-result test**

- [ ] **Step 4: Run RED→GREEN and commit**

Commit: `feat: validate spreadsheet cell edits`

---

### Task 5: XLSX fixture builder and package authority discovery

**Files:**
- Create: `packages/markitdown/tests/twoways/_xlsx_fixtures.py`
- Create: `packages/markitdown/src/markitdown/twoways/formats/xlsx/model.py`
- Create: `packages/markitdown/src/markitdown/twoways/formats/xlsx/package.py`
- Create: `packages/markitdown/tests/twoways/test_xlsx_package.py`

**Interfaces:**
- Produces: `XlsxPackageParts`, `discover_xlsx_parts(package)` and namespace/constants helpers.

- [ ] **Step 1: Build minimal in-memory XLSX fixture**

Fixture must contain `[Content_Types].xml`, `_rels/.rels`, `xl/workbook.xml`, `xl/_rels/workbook.xml.rels`, one worksheet and optional `sharedStrings.xml`.

- [ ] **Step 2: Add RED tests for valid workbook discovery**

Assert exact workbook and sheet part names and relationship IDs.

- [ ] **Step 3: Add adversarial RED tests**

Reject:

- duplicate officeDocument authority;
- missing workbook target;
- external worksheet target;
- path traversal target;
- duplicate sheet relationship authority;
- mixed supported SpreadsheetML namespaces in an authoritative subtree;
- wrong content type for workbook/worksheet.

- [ ] **Step 4: Implement discovery only through shared OOXML package validation helpers**

Do not add a second ZIP safety implementation.

- [ ] **Step 5: Run package tests GREEN and commit**

Commit: `feat: discover authoritative xlsx parts`

---

### Task 6: SpreadsheetML cell extraction and capability decisions

**Files:**
- Create: `packages/markitdown/src/markitdown/twoways/formats/xlsx/cells.py`
- Modify: `packages/markitdown/tests/twoways/_xlsx_fixtures.py`
- Create: `packages/markitdown/tests/twoways/test_xlsx_reader.py`

**Interfaces:**
- Produces: A1-reference helpers, typed cell parser and per-cell capability decisions.

- [ ] **Step 1: RED tests for typed extraction**

Cover:

- shared string;
- inline string;
- integer/float;
- boolean;
- blank;
- formula with cached value;
- style ID retention;
- merged-range membership.

- [ ] **Step 2: RED tests for capabilities**

Expected first-tranche behavior:

- plain scalar non-merged cell => `update_sheet_cells:writable`;
- formula cell => `read-only` + `xlsx.cell.formula_requires_explicit_formula_edit`;
- merged cell => `read-only` + `xlsx.cell.merged_range`;
- malformed duplicate cell reference => fail closed.

- [ ] **Step 3: Implement shared-string reads without mutating shared strings**

- [ ] **Step 4: Run GREEN and commit**

Commit: `feat: extract typed xlsx cells`

---

### Task 7: XLSX reader to DocumentIR

**Files:**
- Create: `packages/markitdown/src/markitdown/twoways/formats/xlsx/reader.py`
- Create: `packages/markitdown/src/markitdown/twoways/formats/xlsx/__init__.py`
- Create: `packages/markitdown/tests/twoways/test_xlsx_reader.py`
- Create: `packages/markitdown/tests/twoways/test_xlsx_public_imports.py`

**Interfaces:**
- Produces: `XlsxDocumentReader.read(source: bytes | BinaryIO, *, filename: str | None = None) -> DocumentIR` following the repository’s existing reader protocol shape.

- [ ] **Step 1: RED tests for workbook IR shape**

Assert:

- `source.format == "xlsx"`;
- one worksheet becomes one `Canvas(kind="worksheet")`;
- each worksheet has one table root node representing its used range;
- `TableCell.text` is display projection;
- `TableCell.metadata["xlsx.typed_value"]` retains typed value;
- table/node metadata carries authoritative worksheet part and capability declarations;
- deterministic IDs for identical source bytes.

- [ ] **Step 2: Implement reader with `DocumentIdFactory(seed=source_sha256)`**

- [ ] **Step 3: Validate produced IR through `validate_document()` in tests**

- [ ] **Step 4: Public-import test for XLSX reader/writer package facade only; keep low-level helpers internal**

- [ ] **Step 5: Run GREEN and commit**

Commit: `feat: read xlsx into document ir`

---

### Task 8: Native target-cell patch primitives

**Files:**
- Create: `packages/markitdown/src/markitdown/twoways/formats/xlsx/patch.py`
- Create: `packages/markitdown/tests/twoways/test_xlsx_cell_patch.py`

**Interfaces:**
- Produces: pure worksheet XML target-cell patch function.

- [ ] **Step 1: RED tests for exact target mutation**

Test string, number, boolean and blank changes. For strings, expect a local `inlineStr` representation. Confirm sibling cells and worksheet properties remain unchanged.

- [ ] **Step 2: RED stale/native authority tests**

Reject:

- missing target cell;
- duplicate target reference;
- formula target;
- merged target;
- old native value mismatch;
- namespace mismatch.

- [ ] **Step 3: Implement patching without reparsing/rebuilding unrelated package members**

- [ ] **Step 4: Run GREEN and commit**

Commit: `feat: patch scalar xlsx cells`

---

### Task 9: XLSX native/semantic verifier

**Files:**
- Create: `packages/markitdown/src/markitdown/twoways/formats/xlsx/verify.py`
- Create: `packages/markitdown/tests/twoways/test_xlsx_roundtrip.py`

**Interfaces:**
- Produces: verifier functions returning/feeding `FidelityEvidence`.

- [ ] **Step 1: RED tests for target semantic re-read**

After patching, re-read the worksheet and assert typed values exactly match requested values.

- [ ] **Step 2: RED tests for untouched-member preservation**

Add an unrelated package member and second worksheet; assert byte identity after editing sheet one.

- [ ] **Step 3: RED tests for unauthorized cell mutation detection**

Deliberately alter an unrequested cell and assert verification fails.

- [ ] **Step 4: Implement verifier and run GREEN**

Commit: `feat: verify xlsx native preservation`

---

### Task 10: Transactional XLSX writer

**Files:**
- Create: `packages/markitdown/src/markitdown/twoways/formats/xlsx/writer.py`
- Modify: `packages/markitdown/src/markitdown/twoways/formats/xlsx/__init__.py`
- Create: `packages/markitdown/tests/twoways/test_xlsx_roundtrip.py`

**Interfaces:**
- Produces: `XlsxDocumentWriter` with existing `DocumentWriter` protocol conventions.

- [ ] **Step 1: RED no-op byte-identity test**

Writing a document with no edits must produce exact original bytes.

- [ ] **Step 2: RED end-to-end edit test**

Construct `update_sheet_cells` with semantic/native preconditions and assert output typed value changes while unrelated members remain exact.

- [ ] **Step 3: RED full-preflight test**

Supply two edits where the second is stale; assert the writer raises before returning any output and does not expose a half-mutated result.

- [ ] **Step 4: Implement source digest lock, capability check, edit validation, transactional replacements, verifier and `WriterResult`**

- [ ] **Step 5: Run full XLSX tests GREEN and commit**

Commit: `feat: add transactional xlsx writer`

---

### Task 11: Identity Markdown bridge for lossless XLSX regions

**Files:**
- Modify: `packages/markitdown/src/markitdown/twoways/markdown/projection.py`
- Modify: `packages/markitdown/src/markitdown/twoways/markdown/_import_edits.py`
- Modify/Test: `packages/markitdown/tests/twoways/test_table_markdown_roundtrip.py`
- Create/Test: `packages/markitdown/tests/twoways/test_xlsx_roundtrip.py`

**Interfaces:**
- Consumes: XLSX table-node metadata marker and `update_sheet_cells` validation.
- Produces: identity Markdown edits only for lossless text-cell regions.

- [ ] **Step 1: RED identity projection test**

For an XLSX worksheet containing only plain text cells with no Markdown-lossy whitespace/pipes/newlines, identity projection advertises `update_sheet_cells`.

- [ ] **Step 2: RED importer test**

Changing one identity table cell emits exactly one `update_sheet_cells` operation containing exactly the changed coordinate.

- [ ] **Step 3: RED type-loss tests**

Numeric/boolean/formula cells that cannot be represented unambiguously through the current identity table path must not be advertised as Markdown-writable.

- [ ] **Step 4: Implement narrow bridge without weakening existing DOCX/PPTX table semantics**

- [ ] **Step 5: Run Markdown + XLSX regression tests GREEN and commit**

Commit: `feat: round trip lossless xlsx text cells through markdown`

---

### Task 12: XLSX hardening and differential validation

**Files:**
- Create: `packages/markitdown/tests/twoways/test_xlsx_hardening.py`
- Reuse: `packages/markitdown/tests/test_files/test.xlsx`
- Reuse when practical: `packages/markitdown-ocr/tests/ocr_test_data/xlsx_*.xlsx`

**Interfaces:**
- No new production API unless a real bug requires a narrowly scoped fix.

- [ ] **Step 1: Add malformed workbook/worksheet cases**

Cover duplicate cells, duplicate workbook relationships, shared-string out-of-range indexes, mixed namespaces, oversized XML limits, invalid A1 references, unexpected external targets and stale source package digests.

- [ ] **Step 2: Add independent-open validation**

When openpyxl is installed, load the output workbook in read-only/data-only variants as appropriate. This is differential validation only; it must not be the production writer.

- [ ] **Step 3: Add real fixture smoke tests**

Read existing repository XLSX fixtures and build capability reports without crashing. Mutate only fixtures whose target cell structure satisfies the tranche-one contract.

- [ ] **Step 4: Run focused and complete package suites**

Run:

```bash
pytest packages/markitdown/tests/twoways -q
pytest packages/markitdown/tests -q
```

- [ ] **Step 5: Commit**

Commit: `test: harden xlsx round trip corpus`

---

### Task 13: Documentation and support matrix

**Files:**
- Modify: `TWOWAYS.md`

- [ ] **Step 1: Document capability report API**

Show how a caller asks why a node is writable/read-only/derived.

- [ ] **Step 2: Document XLSX tranche-one support**

State exactly:

- worksheet/cell reading supported;
- scalar non-formula, non-merged cell typed edits supported;
- lossless simple text-cell identity Markdown supported;
- formulas, merged cells, structural edits, charts/drawings/styles remain read-only/preserved in this tranche;
- no-op byte identity and target-only verification are required.

- [ ] **Step 3: Add parity roadmap link to the design spec**

- [ ] **Step 4: Commit**

Commit: `docs: describe capability kernel and xlsx support`

---

### Task 14: Final CI, review and merge gate

**Files:** none unless verification finds a bug.

- [ ] **Step 1: Run/observe pre-commit on exact PR head**
- [ ] **Step 2: Run/observe Python 3.10–3.13 package matrix on exact PR head**
- [ ] **Step 3: Run/observe OCR matrix to ensure XLSX OCR plugin compatibility did not regress**
- [ ] **Step 4: Review PR diff for scope ceiling violations**
- [ ] **Step 5: Verify branch ahead/behind and PR mergeability**
- [ ] **Step 6: Record synthetic merge commit/tree tested by GitHub Actions**
- [ ] **Step 7: Merge only if required checks are green**
- [ ] **Step 8: Verify actual merge tree equals tested synthetic merge tree**
- [ ] **Step 9: Publish `2ways-v0.3.0` only if the merged tree is the verified tree and the documented support matrix matches implemented capabilities**

---

## Program continuation after v0.3.0

The full-parity design is intentionally decomposed. After v0.3.0, create separate design/implementation plans for:

1. Office deep editing (DOCX/PPTX/XLSX formatting/resources/bounded structure);
2. text/structured parity (plain text/Markdown/CSV/JSON/XML/HTML);
3. IPYNB/EPUB/ZIP;
4. native-safe PDF editing;
5. image/audio/MSG/XLS;
6. remote/derived source adapters and Azure bridges.

Each sub-program must independently preserve the scope ceiling and must not reuse “parser support” as proof of safe writeback.
