# Phase F0/F1 Capability Kernel + XLSX Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the first independently releasable post-v0.2.0 tranche: a typed cross-format capability kernel plus source-locked, preservation-verified XLSX scalar-cell round trips.

**Architecture:** Preserve the existing `DocumentIR -> typed edit -> format writer -> verifier` architecture. Add a typed capability contract at the IR boundary, migrate already-proven DOCX/PPTX capabilities without changing their writer semantics, and implement XLSX as a new OOXML format adapter that patches only authoritative worksheet XML carriers in the original package. Production XLSX writing never uses `openpyxl.save()`.

**Tech Stack:** Python 3.10-3.13, dataclasses, `lxml`/secure OOXML XML helpers, `zipfile` through existing OOXML package utilities, `openpyxl` only for independent validation tests, pytest/hatch, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-09-11-markitdown-2ways-full-format-parity-design.md`

## Global Constraints

- [ ] Work only on `nolane/phase-f-format-parity-foundation`, based on `main@fa897976a92aea707ba12a9b2294fdce5f067615`.
- [ ] Preserve all v0.2.0 DOCX/PPTX behavior unless a failing regression proves a bug.
- [ ] Do not add UI, service, workflow, agent, persistence, or cloud-platform features.
- [ ] Every writable capability begins with a test-only RED commit and is followed by the smallest GREEN implementation.
- [ ] Never emit partially mutated XLSX bytes after failed preflight or verification.
- [ ] Keep formulas, merged-cell mutation, styles, rich text, structural row/column/sheet edits, charts, and shared-formula mutations read-only in this release unless a later explicit test tranche proves them.
- [ ] Do not claim absolute bug-freedom; record exact verification evidence instead.

---

## Task 1: Typed capability model and coverage report

**Files:**
- Create: `packages/markitdown/src/markitdown/twoways/ir/capabilities.py`
- Modify: `packages/markitdown/src/markitdown/twoways/ir/nodes.py`
- Modify: `packages/markitdown/src/markitdown/twoways/ir/__init__.py`
- Modify: `packages/markitdown/src/markitdown/twoways/__init__.py`
- Modify: `packages/markitdown/src/markitdown/twoways/ir/_validation.py`
- Test: `packages/markitdown/tests/twoways/test_capabilities.py`
- Test: `packages/markitdown/tests/twoways/test_public_imports.py`

- [ ] **1.1 RED:** Add tests importing `EditCapability`, `CapabilityCoverage`, and `capability_coverage` from the public `markitdown.twoways` namespace.
- [ ] **1.2 RED:** Test `EditCapability(operation="replace_text")` normalization/immutability, invalid empty operation, invalid fidelity, immutable copied constraints, and deterministic tuple storage on `Node`.
- [ ] **1.3 RED:** Test coverage counts with writable, read-only, derived, and zero-capability nodes. A writable node is one with at least one `lossless` or `verified_rewrite` capability. A derived node has `derived_read_only` and no writable capability. Remaining nodes without writable/derived capability are read-only.
- [ ] **1.4 RED:** Test deterministic operation/reason counts independent of node mapping insertion order.
- [ ] Commit the tests only and verify the PR CI fails specifically because the new public contracts do not yet exist.

Implement in `ir/capabilities.py`:

```python
CAPABILITY_FIDELITIES = frozenset(
    {"lossless", "verified_rewrite", "derived_read_only", "read_only"}
)

@dataclass(frozen=True)
class EditCapability:
    operation: str
    fidelity: str = "lossless"
    constraints: Mapping[str, Any] = field(default_factory=dict)
    reason_code: str | None = None

    def __post_init__(self) -> None:
        if not self.operation.strip():
            raise ValueError("operation must be non-empty")
        if self.fidelity not in CAPABILITY_FIDELITIES:
            raise ValueError(f"unsupported capability fidelity: {self.fidelity}")
        object.__setattr__(self, "constraints", dict(self.constraints))

@dataclass(frozen=True)
class CapabilityCoverage:
    total_nodes: int
    writable_nodes: int
    read_only_nodes: int
    derived_nodes: int
    operations: Mapping[str, int] = field(default_factory=dict)
    reason_codes: Mapping[str, int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "operations", dict(self.operations))
        object.__setattr__(self, "reason_codes", dict(self.reason_codes))
```

- [ ] **1.5 GREEN:** Add `capabilities: tuple[EditCapability, ...] = ()` to `Node`; canonicalize to tuple in `Node.__post_init__`.
- [ ] **1.6 GREEN:** Implement `capability_coverage(document)` as a pure deterministic function. Count each operation at most once per node even if duplicate equivalent capability entries somehow exist in input; validation will reject duplicates at the public boundary.
- [ ] **1.7 GREEN:** Extend validation to reject duplicate `(operation, fidelity, reason_code)` capability descriptors on one node and reject a capability whose `operation` is absent from the public edit vocabulary when fidelity is writable.
- [ ] **1.8 GREEN:** Export the new contracts from `ir/__init__.py` and root `twoways/__init__.py`.
- [ ] Run focused tests and full package tests on the exact branch head; commit only after GREEN.

## Task 2: Canonical serialization and schema compatibility for capabilities

**Files:**
- Modify: `packages/markitdown/src/markitdown/twoways/ir/serialization.py` only if generic decoding needs assistance
- Modify: `packages/markitdown/tests/twoways/test_serialization.py`
- Modify: `packages/markitdown/tests/twoways/test_models.py`

- [ ] **2.1 RED:** Add round-trip tests proving a node with typed capabilities produces deterministic canonical JSON and strict-decodes back to an equal `DocumentIR`.
- [ ] **2.2 RED:** Add strict decode test rejecting unknown capability fields and invalid fidelity values.
- [ ] **2.3 RED:** Add canonical order test proving the serialized document is byte-identical regardless of mapping insertion order inside `constraints`.
- [ ] **2.4 GREEN:** Rely on the generic dataclass decoder where sufficient; add only the minimum decoding hook required for `EditCapability`. Do not create a second serialization path.
- [ ] **2.5 GREEN:** Keep schema major at `0`; do not bump to `1.x`. If a schema patch/minor bump is required by existing compatibility tests, make the smallest compatible bump and add explicit tests.
- [ ] Run focused serialization/model tests and full package tests; commit GREEN.

## Task 3: Migrate already-proven DOCX/PPTX capabilities without writer rewrites

**Files:**
- Modify: `packages/markitdown/src/markitdown/twoways/formats/docx/structures.py`
- Modify: `packages/markitdown/src/markitdown/twoways/formats/pptx/shapes.py`
- Test: `packages/markitdown/tests/twoways/test_docx_reader.py`
- Test: `packages/markitdown/tests/twoways/test_pptx_reader.py`
- Test: `packages/markitdown/tests/twoways/test_capabilities.py`

- [ ] **3.1 RED:** Assert compatible DOCX paragraph nodes expose `EditCapability("replace_text", "lossless")`; incompatible paragraphs do not expose a writable replacement capability.
- [ ] **3.2 RED:** Assert compatible DOCX simple tables expose `update_table_cells`; resolved images expose `set_alt_text`.
- [ ] **3.3 RED:** Assert compatible PPTX text/note nodes expose `replace_text`, simple tables expose `update_table_cells`, and pictures expose `set_alt_text` only where the existing writer already supports that operation.
- [ ] **3.4 RED:** Assert charts remain explicitly read-only (either zero writable capability plus a stable reason or a typed `read_only` capability).
- [ ] Commit RED tests and capture CI evidence.
- [ ] **3.5 GREEN:** Add typed capabilities in parallel with existing `docx:*` / `pptx:*` metadata. Do not remove metadata yet and do not make writers trust the new field yet.
- [ ] **3.6 GREEN:** Add stable reason codes only where the reader can explain the compatibility decision without duplicating expensive parsing or inventing reasons.
- [ ] Run DOCX/PPTX reader + round-trip suites and full package tests; commit GREEN.

## Task 4: Spreadsheet IR payload and `set_cell_value` edit contract

**Files:**
- Modify: `packages/markitdown/src/markitdown/twoways/ir/nodes.py`
- Modify: `packages/markitdown/src/markitdown/twoways/ir/edits.py`
- Modify: `packages/markitdown/src/markitdown/twoways/ir/serialization.py`
- Modify: `packages/markitdown/src/markitdown/twoways/ir/_validation.py`
- Create: `packages/markitdown/src/markitdown/twoways/ir/spreadsheet_edits.py`
- Modify: `packages/markitdown/src/markitdown/twoways/ir/__init__.py`
- Modify: `packages/markitdown/src/markitdown/twoways/__init__.py`
- Test: `packages/markitdown/tests/twoways/test_spreadsheet_ir.py`
- Test: `packages/markitdown/tests/twoways/test_spreadsheet_edits.py`

- [ ] **4.1 RED:** Add `SpreadsheetCellPayload` tests for required non-empty uppercase A1 address, JSON-compatible scalar values, finite float requirement, formula/cached value/number format preservation, and canonical serialization.
- [ ] **4.2 RED:** Add `cell` node-kind round-trip decode test.
- [ ] **4.3 RED:** Add `set_cell_value` edit validation tests covering valid `None`/str/bool/int/finite-float and rejecting NaN/infinity, containers, bytes, arbitrary objects, empty payload, unknown fields, bool-as-int confusion where explicit type is used, and no-op edits.
- [ ] **4.4 RED:** Assert operation preconditions carry old semantic value and digests without mutation.
- [ ] Commit RED tests.
- [ ] **4.5 GREEN:** Add `SpreadsheetCellPayload`, `cell` to `INITIAL_NODE_KINDS`, and `_decode_node_payload("cell", ...)`.
- [ ] **4.6 GREEN:** Add `set_cell_value` to `INITIAL_EDIT_TYPES` and implement a focused helper in `spreadsheet_edits.py` that validates payload + stale old value before a writer can mutate.
- [ ] **4.7 GREEN:** Re-export public contracts; run focused + full tests; commit GREEN.

## Task 5: Deterministic minimal XLSX fixtures and package-discovery authority

**Files:**
- Create: `packages/markitdown/tests/twoways/_xlsx_fixtures.py`
- Create: `packages/markitdown/src/markitdown/twoways/formats/xlsx/__init__.py`
- Create: `packages/markitdown/src/markitdown/twoways/formats/xlsx/model.py`
- Create: `packages/markitdown/src/markitdown/twoways/formats/xlsx/package.py`
- Test: `packages/markitdown/tests/twoways/test_xlsx_package.py`

- [ ] **5.1 RED:** Build minimal XLSX bytes in tests with deterministic ZIP members: `[Content_Types].xml`, `_rels/.rels`, `xl/workbook.xml`, `xl/_rels/workbook.xml.rels`, worksheet XML, optional `sharedStrings.xml`, styles, and unrelated sentinel parts.
- [ ] **5.2 RED:** Test authoritative discovery of exactly one workbook main part through the package relationship + content-type contract.
- [ ] **5.3 RED:** Test worksheet relationship mapping from workbook sheet `r:id` to internal worksheet part and deterministic sheet order/name.
- [ ] **5.4 RED:** Reject duplicate/ambiguous workbook relationships, missing worksheet targets, external worksheet targets, malformed relationship namespace, mixed supported spreadsheet namespaces inside one authoritative subtree, and unexpected root type/content-type conflicts.
- [ ] **5.5 RED:** Reuse existing OOXML package limits and assert zip/member/XML limit failures propagate fail-closed.
- [ ] Commit RED tests.
- [ ] **5.6 GREEN:** Implement only XLSX package authority/discovery. Reuse `snapshot_package`, `parse_xml_part`, and existing path/relationship hardening; do not duplicate ZIP safety logic.
- [ ] **5.7 GREEN:** Normalize part names internally to absolute OPC-style names while mapping to ZIP member names only at package I/O boundaries.
- [ ] Run focused package tests and existing OOXML hardening tests; commit GREEN.

## Task 6: XLSX reader — worksheets, typed scalar cells, formulas/read-only diagnostics

**Files:**
- Create: `packages/markitdown/src/markitdown/twoways/formats/xlsx/locators.py`
- Create: `packages/markitdown/src/markitdown/twoways/formats/xlsx/cells.py`
- Create: `packages/markitdown/src/markitdown/twoways/formats/xlsx/reader.py`
- Modify: `packages/markitdown/src/markitdown/twoways/formats/xlsx/__init__.py`
- Test: `packages/markitdown/tests/twoways/test_xlsx_reader.py`
- Test: `packages/markitdown/tests/twoways/test_xlsx_public_imports.py`

- [ ] **6.1 RED:** Read each worksheet as `Canvas(kind="worksheet", name=<sheet name>, index=<order>)` with authoritative part locator metadata.
- [ ] **6.2 RED:** Read inline strings, shared strings, booleans, integers/floats, blanks, and simple formulas into `SpreadsheetCellPayload` without pandas normalization.
- [ ] **6.3 RED:** Preserve A1 addresses exactly semantically and sort cell nodes deterministically by row/column rather than XML incidental ordering.
- [ ] **6.4 RED:** Ensure ordinary supported scalar non-formula non-merged cells advertise `set_cell_value` lossless capability.
- [ ] **6.5 RED:** Formula cells expose `xlsx.cell.formula_read_only`; merged cells expose `xlsx.cell.merged_read_only`; unsupported cell types expose `xlsx.cell.unsupported_type` and no writable capability.
- [ ] **6.6 RED:** Reject duplicate cell addresses in a worksheet, invalid A1 refs, non-finite numeric lexical values, and namespace-mixed cell subtrees.
- [ ] **6.7 RED:** Assert source descriptor contains exact XLSX SHA-256/size/preserved source ref.
- [ ] Commit RED tests and capture exact-head CI failure.
- [ ] **6.8 GREEN:** Implement the reader directly over hardened OOXML XML; `openpyxl` is not the authoritative reader for 2Ways locators.
- [ ] **6.9 GREEN:** Use sharedStrings only for read resolution. Do not mutate or normalize it.
- [ ] **6.10 GREEN:** Export `XlsxIRReader`, read options, and `read_xlsx_ir`; run focused/full tests; commit GREEN.

## Task 7: XLSX scalar-cell patch primitive

**Files:**
- Create: `packages/markitdown/src/markitdown/twoways/formats/xlsx/patch.py`
- Create: `packages/markitdown/src/markitdown/twoways/formats/xlsx/_cell_patch.py`
- Test: `packages/markitdown/tests/twoways/test_xlsx_cell_patch.py`

- [ ] **7.1 RED:** Patch existing numeric cell to int/float and preserve style index/unknown attributes.
- [ ] **7.2 RED:** Patch existing scalar/shared-string cell to inline string locally without editing `sharedStrings.xml`.
- [ ] **7.3 RED:** Patch booleans and clear scalar content while preserving the `<c>` container/style.
- [ ] **7.4 RED:** Reject formula cells, merged cells, unsupported types, stale old native values, ambiguous/missing target cells, duplicate target edits, wrong sheet locator, and namespace mismatch.
- [ ] **7.5 RED:** Verify only the target `<c>` subtree changes; sibling cells, row properties, column definitions, sheet views, merges, conditional formatting, drawings, and other XML descendants remain byte/canonical-preserved according to the chosen native-subtree comparison.
- [ ] Commit RED tests.
- [ ] **7.6 GREEN:** Implement preflight that resolves every requested edit before serializing any worksheet part.
- [ ] **7.7 GREEN:** Use inline string `<is><t>...</t></is>` for written strings; set `xml:space="preserve"` only when required by boundary whitespace.
- [ ] **7.8 GREEN:** Serialize with existing secure XML serializer. Keep replacements sparse and worksheet-local.
- [ ] Run focused tests and commit GREEN.

## Task 8: Source-locked XLSX writer and preservation verifier

**Files:**
- Create: `packages/markitdown/src/markitdown/twoways/formats/xlsx/verify.py`
- Create: `packages/markitdown/src/markitdown/twoways/formats/xlsx/writer.py`
- Modify: `packages/markitdown/src/markitdown/twoways/formats/xlsx/__init__.py`
- Test: `packages/markitdown/tests/twoways/test_xlsx_verifier.py`
- Test: `packages/markitdown/tests/twoways/test_xlsx_roundtrip.py`

- [ ] **8.1 RED:** No-op writer returns byte-identical original XLSX bytes and exact-preserve fidelity evidence.
- [ ] **8.2 RED:** Writer rejects a source whose SHA-256 differs from `DocumentIR.source`.
- [ ] **8.3 RED:** Writer validates all edits before package emission and produces no output bytes on a preflight failure when the supplied output stream begins empty.
- [ ] **8.4 RED:** Successful scalar edit changes only the target worksheet member; all unrelated ZIP member uncompressed digests and member inventory remain identical.
- [ ] **8.5 RED:** Verifier re-reads output through `read_xlsx_ir()` and proves target cell semantics match expected values.
- [ ] **8.6 RED:** Native verifier proves untouched cells/subtrees in each touched worksheet remain equal and refuses unexpected worksheet-wide normalization.
- [ ] **8.7 RED:** Independently open successful output with `openpyxl.load_workbook(..., data_only=False)` in tests and assert the target scalar value while sentinel workbook structures remain available.
- [ ] Commit RED tests.
- [ ] **8.8 GREEN:** Implement `XlsxWriter` with `validate_source_authority`, package snapshot, per-sheet sparse replacements, `write_package`, `inspect_package_preservation`, native-subtree checks, and semantic re-read before copying verified bytes to the caller's output.
- [ ] **8.9 GREEN:** Use an internal `BytesIO` transaction buffer; copy to caller output only after verification passes.
- [ ] **8.10 GREEN:** Emit `WriterResult(format="xlsx", mode="sparse-native-patch", ...)` with concrete fidelity evidence codes for source authority, package inventory, untouched members, untouched worksheet native content, and semantic re-read.
- [ ] Run focused/full tests; commit GREEN.

## Task 9: Identity Markdown boundary decision for XLSX

**Files:**
- Test/Modify only if reversible: `packages/markitdown/src/markitdown/twoways/markdown/*`
- Test: `packages/markitdown/tests/twoways/test_xlsx_markdown_roundtrip.py` only if capability is exposed
- Otherwise document typed-edit-only boundary in `TWOWAYS.md`

- [ ] **9.1 PROBE BY TEST/DESIGN:** Confirm whether existing identity Markdown table syntax can represent XLSX typed scalars, empty-vs-missing cells, formulas, boundary whitespace, booleans, and string-vs-number distinctions without ambiguity.
- [ ] **9.2 DECISION:** If any required distinction is lossy under the current identity syntax, do **not** expose XLSX cell mutation through identity Markdown in v0.3.0. Keep typed `set_cell_value` as the production path and document the reason.
- [ ] **9.3 ONLY IF LOSSLESS:** If a bounded reversible encoding already exists, add RED tests first and implement the smallest importer/projection bridge. Do not change clean Markdown semantics.
- [ ] Record the decision in branch docs and commit.

## Task 10: Hardening matrix for XLSX

**Files:**
- Create/extend: `packages/markitdown/tests/twoways/test_xlsx_hardening.py`
- Extend: `packages/markitdown/tests/twoways/_xlsx_fixtures.py`

- [ ] **10.1 RED/GREEN tranches:** Add adversarial cases for XML comments/non-element nodes, duplicate property containers where uniqueness is required, mixed Transitional/Strict SpreadsheetML namespaces, unexpected foreign elements in authority-sensitive paths, relationship `TargetMode`, unsafe targets, shared-string index bounds, malformed booleans/numbers, oversized XML parts, duplicate ZIP members, and stale locator digests.
- [ ] **10.2 PROPERTY INVARIANTS:** For a matrix of scalar cells, assert read -> no-op write byte identity and read -> edit -> write -> read exact semantic target equality.
- [ ] **10.3 PRESERVATION MATRIX:** Include unrelated workbook, styles, theme, custom property, drawing/media, and second-sheet sentinel members and assert their uncompressed digests remain unchanged.
- [ ] **10.4 DIFFERENTIAL:** Validate generated output with `openpyxl` in addition to the 2Ways reader.
- [ ] Keep each discovered bug as a dedicated regression rather than weakening production gates.

## Task 11: Documentation, PR closure, full CI, and v0.3.0 release gate

**Files:**
- Modify: `TWOWAYS.md`
- Modify: `README.md` only where 2Ways support matrix belongs naturally
- Modify: design/plan status sections if useful; no marketing inflation

- [ ] Document a capability matrix separating one-way conversion, 2Ways read, typed mutation, identity-Markdown mutation, and native writeback.
- [ ] Explicitly document XLSX v0.3.0 boundaries: scalar cell values only for mutation; formulas/merged/rich text/styles/structure read-only until later phases.
- [ ] Document `capability_coverage()` and stable diagnostics.
- [ ] Open/maintain a draft PR from `nolane/phase-f-format-parity-foundation` to `main` early enough that every RED/GREEN lineage has CI evidence.
- [ ] Before readiness, run/check GitHub Actions exact-head matrix: Python 3.10, 3.11, 3.12, 3.13 package tests; OCR tests on all four; pre-commit.
- [ ] Inspect every failed CI job log. Fix root causes with dedicated regressions; never weaken tests merely to turn CI green.
- [ ] Request/perform code review against the master spec and ensure no platform-scope creep.
- [ ] Record exact PR head SHA and CI-tested synthetic merge SHA/tree.
- [ ] Merge only when PR is mergeable and all required jobs are green.
- [ ] Verify actual merge tree equals the tested synthetic merge tree before release.
- [ ] Publish `2ways-v0.3.0` only if all release gates pass, and make the tag target the exact verified merge commit.
- [ ] Clean any temporary publisher workflow/branch changes after independently verifying the release object and tag.
