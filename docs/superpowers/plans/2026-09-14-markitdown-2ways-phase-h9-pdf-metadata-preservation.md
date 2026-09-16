# Phase H9 PDF Metadata Preservation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans task-by-task.

**Goal:** Add conservative incremental PDF metadata editing for existing `/Title`, `/Author`, `/Subject`, `/Keywords` owners.

**Architecture:** strict pypdf authority read -> DocumentIR -> `update_pdf_metadata` -> pypdf incremental writer -> changed-object audit -> pypdf/pdfminer verification -> caller output.

**Tech Stack:** Python 3.10-3.13, pypdf `>=6.18.1,<7`, pdfminer.six, existing 2Ways contracts.

**Spec:** `docs/superpowers/specs/2026-09-14-markitdown-2ways-phase-h9-pdf-metadata-preservation-design.md`

## Global constraints

- Base is exact H8 SHA `9a43768efde296330f8bbea542ffc5e926a2d735`.
- H8 branch remains immutable.
- Writable keys: existing text `/Title`, `/Author`, `/Subject`, `/Keywords` only.
- XMP, encryption, signatures/certification, linearized PDFs are read-only.
- No page/text/image/annotation/form/link/outline/content-stream/general-object mutation.
- Non-empty mutation must keep original source bytes as exact candidate prefix.
- Zero edits must return exact source bytes.
- Caller output stays empty until final verification passes.
- One-way `_pdf_converter.py` must remain unchanged.
- Completion gate: pre-commit + package/OCR Python 3.10-3.13 = exact 9/9 GREEN.

## File map

Create `packages/markitdown/src/markitdown/twoways/formats/pdf/` with `__init__.py`, `limits.py`, `model.py`, `parser.py`, `reader.py`, `routing.py`, `writer.py`, `verification.py`, `writer_adapter.py`.

Tests: `_pdf_fixtures.py`, `test_pdf_native_parser.py`, `test_pdf_native_reader.py`, `test_pdf_native_routing.py`, `test_pdf_native_writer.py`, `test_pdf_native_verification.py`, `test_pdf_native_public_imports.py`, `test_pdf_native_markdown.py`, `test_pdf_native_oneway_regression.py`.

Expected shared edits: `packages/markitdown/pyproject.toml`, `TWOWAYS.md`.

---

### Task 1 — Dependency, fixtures, parser RED

**Files:** modify `pyproject.toml`; create `_pdf_fixtures.py`, `test_pdf_native_parser.py`.

**Produces:** deterministic in-memory PDF fixtures and RED contract for `PdfNativeLimits`, `PdfParseError`, `parse_pdf_source`.

- [ ] Add `pypdf>=6.18.1,<7` to `all` and `pdf` extras.
- [ ] Build one-page fixture with existing four supported metadata fields.
- [ ] Add fixtures/policy cases for XMP, signature evidence, linearization, malformed input, limits.
- [ ] RED assertions bind SHA/size, page count, `/Info` objgen, supported metadata and read-only diagnostics.
- [ ] Run `cd packages/markitdown && hatch test -py=3.12 tests/twoways/test_pdf_native_parser.py -v`; expected import/collection failure because PDF native modules do not exist.
- [ ] Commit `test: define H9 PDF native parser boundary`.

### Task 2 — Strict parser/evidence GREEN

**Files:** create `limits.py`, `model.py`, `parser.py`.

**Produces:** `PdfNativeLimits`, `PdfParseError`, `PdfInfoFieldEvidence`, `PdfSourceSnapshot`, `ParsedPdfSource`, `parse_pdf_source(source, *, limits=None)`.

- [ ] Implement frozen limits: source 512 MiB, 20k pages, suffix 4 MiB, one value 64 KiB chars, total 256 KiB chars.
- [ ] Parse with `PdfReader(BytesIO(source), strict=True)`.
- [ ] Record source hash/size, version, page count, Root, Info objgen, supported values, XMP/encryption/signature/certification/linearized flags.
- [ ] Safely readable but policy-ineligible PDFs return read-only diagnostics; malformed authority raises `PdfParseError`.
- [ ] Run focused parser tests, then full package suite on 3.12.
- [ ] Commit `feat: add strict H9 PDF metadata authority parser`.

### Task 3 — DocumentIR reader RED->GREEN

**Files:** create `test_pdf_native_reader.py`, `reader.py`.

**Produces:** `read_pdf_ir(...) -> DocumentIR`, `PdfIRReader`.

- [ ] RED: one `document` canvas, root `pdf-document`, deterministic `pdf-metadata` children, writable capability only on eligible existing owners.
- [ ] Native locator binds `/Info` objgen + exact key; field metadata includes `pdf.identity_markdown=False`.
- [ ] Read-only policy fixtures expose stable reason codes.
- [ ] Run parser+reader tests on 3.12.
- [ ] Commit `feat: map H9 PDF metadata authority into DocumentIR`.

### Task 4 — Routing/writer RED

**Files:** create `test_pdf_native_routing.py`, `test_pdf_native_writer.py`.

- [ ] RED stale source, forged objgen/key, stale old value, unsupported key, duplicate operation id, duplicate logical target.
- [ ] RED one-field and multi-field `update_pdf_metadata` transactions.
- [ ] RED zero-edit exact bytes, non-empty exact source-prefix, failed transaction leaves output empty.
- [ ] Run focused tests; expected missing `routing`/`writer` modules.
- [ ] Commit `test: freeze H9 PDF metadata transaction contracts`.

### Task 5 — Fresh routing + incremental writer GREEN

**Files:** create `routing.py`, `writer.py`.

**Produces:** `PdfRoutedMetadataEdit`, `resolve_pdf_metadata_edit`, `patch_pdf`.

- [ ] Fresh-parse source and fresh-read IR before routing any edit.
- [ ] Recheck source SHA/size, Info objgen, exact key, capability, semantic/native/old-value preconditions.
- [ ] Reject duplicate op IDs and logical targets before candidate construction.
- [ ] Zero edits write exact source without invoking pypdf writer.
- [ ] Mutation uses `PdfWriter(BytesIO(source), incremental=True, strict=True)` and internal `BytesIO` output.
- [ ] Audit `list_objects_in_increment()`; modified existing indirect objects must be restricted to authorized `/Info` authority.
- [ ] Require candidate prefix equals exact source and suffix <= configured bound.
- [ ] Run routing/writer tests on 3.12.
- [ ] Commit `feat: add transactional incremental PDF metadata writer`.

### Task 6 — Final verifier RED->GREEN

**Files:** create `test_pdf_native_verification.py`, `verification.py`; modify `writer.py`.

**Produces:** `verify_pdf_candidate(...)`.

- [ ] RED unauthorized metadata drift, broken prefix, page-count drift, unexpected changed object, semantic mismatch.
- [ ] Verify exact source prefix, suffix bound, strict re-read, unchanged page count/root authority and policy state.
- [ ] Requested values must match fresh pypdf read; unrequested supported values must remain unchanged.
- [ ] Cross-check comparable Document Info values through pdfminer; disagreement fails closed.
- [ ] Wire verifier before caller output.
- [ ] Run all `test_pdf_native_*.py` on 3.12.
- [ ] Commit `feat: verify H9 PDF incremental metadata candidates`.

### Task 7 — Public facade, Markdown boundary, one-way lock

**Files:** create `__init__.py`, `writer_adapter.py`, public/Markdown/one-way tests.

**Public exports:** `PdfIRReader`, `PdfNativeLimits`, `PdfParseError`, `PdfPatchWriter`, `parse_pdf_source`, `patch_pdf`, `read_pdf_ir`.

- [ ] RED public imports and `PdfPatchWriter` source/target/kwargs behavior.
- [ ] RED identity Markdown is inspection-only; no importer route may emit `update_pdf_metadata`.
- [ ] Lock exact H8 `_pdf_converter.py` blob plus representative one-way behavior.
- [ ] Implement minimal facade/adapter; shared Markdown change only if dedicated RED proves necessary.
- [ ] Run H9 focused suite.
- [ ] Commit `feat: publish H9 PDF metadata adapter boundary`.

### Task 8 — Hardening, docs, exact completion

**Files:** modify `TWOWAYS.md`; add only genuinely missing adversarial tests.

- [ ] Audit coverage for malformed, limits, encryption, XMP, signature/certification, linearized, missing Info, unsupported metadata type, stale/forged routing, conflicts, no-op, prefix, suffix limit, unexpected object, semantic drift and rollback.
- [ ] Add RED only for a real uncovered gap; do not manufacture redundant tests.
- [ ] Update `TWOWAYS.md` H9 capability/fidelity/security matrix and state extracted page text remains derived/read-only.
- [ ] Scope-audit exact H8 SHA to H9 candidate. Expected production changes: `twoways/formats/pdf/*` + `pyproject.toml`, and shared Markdown only if RED-forced.
- [ ] Confirm `_pdf_converter.py` and H1-H8 production remain unchanged.
- [ ] Run focused H9 suite and full 3.12 package suite.
- [ ] Commit closure docs/tests.
- [ ] Require fresh exact-head pre-commit + package 3.10/3.11/3.12/3.13 + OCR 3.10/3.11/3.12/3.13 = 9/9 SUCCESS.
- [ ] Freeze exact completion SHA; after that only PR metadata may change.
- [ ] Leave H9 unmerged unless explicitly authorized.
