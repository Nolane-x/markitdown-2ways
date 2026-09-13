# MarkItDown 2Ways Phase H7 EPUB Package Preservation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox task state and strict test-first sequencing.

**Goal:** Implement conservative source-preserving two-way editing for EPUB 3 publications, allowing selected OPF metadata text and ordinary XHTML body text replacement while preserving OCF/package structure, untouched member content, and existing one-way behavior.

**Architecture:** H7 owns EPUB OCF/package-graph authority and sparse ZIP orchestration. Existing H4 XML remains the lexical mutation authority inside OPF/XHTML members. Every mutation follows source authority -> fresh EPUB evidence -> edit preflight -> H4 lowering -> internal sparse ZIP candidate -> full H7 re-read verification -> caller output. Zero-edit output is byte-identical to the source.

**Tech Stack:** Python stdlib `zipfile`, `hashlib`, `posixpath`, `urllib.parse`; existing `markitdown.twoways.formats.xml` H4 reader/writer; existing DocumentIR/capability/edit/fidelity contracts; pytest; GitHub Actions Python 3.10-3.13 package/OCR matrices.

**Spec:** `docs/superpowers/specs/2026-09-13-markitdown-2ways-phase-h7-epub-package-preservation-design.md`

## Global Constraints

- H7 starts from exact-green H6 `f8930911e643fdaef718f1f0cb701e2b8c8b9bcf`.
- Do not modify `packages/markitdown/src/markitdown/converters/_epub_converter.py`.
- Do not modify the one-way converter registry or one-way CLI behavior.
- Do not weaken H4 XML parsing/writing/security contracts for EPUB coverage.
- No EPUB serializer, DOM save path, network access, external entity resolution, JavaScript execution, media decoding, subprocesses, or remote writeback.
- Writable publication version is EPUB 3.x only. Earlier package versions are inspection-only/read-only.
- Navigation-document text is read-only in H7 tranche one.
- No member insertion/deletion/rename/reorder, no manifest/spine/container structural mutation, no identifier-linkage mutation, no CSS/SVG/MathML/media/link mutation, and no arbitrary whole-member replacement.
- Exactly two H7 edit types are registered: `replace_epub_metadata_text` and `replace_epub_xhtml_text`.
- Production code must not be added before the corresponding tests have been committed and observed RED for the intended missing H7 behavior.
- Caller output remains empty on any mutation/preflight/lowering/package/verification failure.
- Before H7 completion, exact final head must pass pre-commit + package tests Python 3.10/3.11/3.12/3.13 + OCR tests Python 3.10/3.11/3.12/3.13 = 9/9 GREEN.

## Execution Status

- [x] Design spec approved and committed.
- [x] Implementation plan frozen.
- [x] Task 1 package/parser RED contracts established for the implemented tranche.
- [x] Task 2 safe OCF ZIP snapshot and EPUB semantic parser implemented; full package tests were GREEN on head `859a59849a8dea5d5832f66101b05c9e4c5d2eb2`; subsequent pre-commit-only formatting failure was corrected without semantic changes.
- [x] Task 3 reader RED contract committed at `2bee2e2b5b3da9abb8630ce09b19f36077a2c1fd`; missing `formats/epub/reader.py` was confirmed at that exact RED head.
- [x] Task 3 minimal GREEN reader implementation committed at `be86eca8773435d54d3e45b68ab133c1403df1c0`.
- [ ] Task 3 exact CI GREEN confirmation is pending GitHub runner availability; run #303 is queued.
- [ ] Tasks 4-7 remain gated behind Task 3 GREEN confirmation.

---

### Task 1: Freeze RED contracts and deterministic EPUB fixtures

**Files:**
- Create: `packages/markitdown/tests/twoways/_epub_fixtures.py`
- Create: `packages/markitdown/tests/twoways/test_epub_package.py`
- Create: `packages/markitdown/tests/twoways/test_epub_parser.py`
- Create: `packages/markitdown/tests/twoways/test_epub_reader.py`
- Create: `packages/markitdown/tests/twoways/test_epub_writer.py`
- Create: `packages/markitdown/tests/twoways/test_epub_verification.py`
- Create: `packages/markitdown/tests/twoways/test_epub_public_imports.py`
- Create: `packages/markitdown/tests/twoways/test_epub_markdown.py`
- Create: `packages/markitdown/tests/twoways/test_epub_oneway_regression.py`

- [x] **Step 1: Add in-memory EPUB fixture builder.** Build deterministic EPUB 3 ZIPs with `mimetype` first/stored/no-extra, `META-INF/container.xml`, `OEBPS/content.opf`, one normal XHTML spine document, one navigation document, stylesheet and image payload. Allow controlled malformed variants without introducing disk fixtures.
- [x] **Step 2: Encode OCF/package RED tests for the implemented parser/package tranche.**
- [x] **Step 3: Encode reader/capability RED tests for Task 3.**
- [ ] **Step 4: Encode writer/verification RED tests before Task 5 production.**
- [ ] **Step 5: Encode identity Markdown and one-way regression RED tests before Task 6 production.**
- [x] **Step 6: Confirm RED for missing H7 reader behavior at the exact Task 3 RED head.**
- [x] **Step 7: Commit RED contracts separately from production.**

### Task 2: Implement safe OCF ZIP snapshot and EPUB semantic parser

**Files:**
- Create: `packages/markitdown/src/markitdown/twoways/formats/epub/limits.py`
- Create: `packages/markitdown/src/markitdown/twoways/formats/epub/model.py`
- Create: `packages/markitdown/src/markitdown/twoways/formats/epub/package.py`
- Create: `packages/markitdown/src/markitdown/twoways/formats/epub/parser.py`

**Interfaces:**
- `EpubPackageLimits`
- `EpubPackageEntry`, `EpubPackageSnapshot`
- `EpubRootfileEvidence`, `EpubManifestItemEvidence`, `EpubSpineItemEvidence`, `EpubMetadataOwnerEvidence`, `EpubXhtmlTextEvidence`, `ParsedEpubSource`
- `EpubParseError`
- `snapshot_epub_package(source: bytes, *, limits: EpubPackageLimits | None = None) -> EpubPackageSnapshot`
- `parse_epub_source(source: bytes, *, limits: EpubPackageLimits | None = None) -> ParsedEpubSource`

- [x] **Step 1: Implement `EpubPackageLimits`.**
- [x] **Step 2: Implement ZIP snapshot fail-closed validation.**
- [x] **Step 3: Enforce OCF `mimetype`.**
- [x] **Step 4: Parse `container.xml` through strict XML authority.**
- [x] **Step 5: Parse OPF package graph through H4 XML evidence.**
- [x] **Step 6: Extract selected metadata text owners and XHTML text owners.**
- [x] **Step 7: Run package/parser tests through full package matrix; semantic tests GREEN before formatting-only cleanup.**
- [x] **Step 8: Commit implementation.**

### Task 3: Build deterministic EPUB DocumentIR and capabilities

**Files:**
- Create: `packages/markitdown/src/markitdown/twoways/formats/epub/reader.py`

**Interfaces:**
- `read_epub_ir(source: BinaryIO, *, filename: str | None = None, mimetype: str | None = None, limits: EpubPackageLimits | None = None) -> DocumentIR`
- `EpubIRReader(DocumentIRReader)`

- [x] **Step 1: Map deterministic publication structure.**
- [x] **Step 2: Add selected metadata text nodes.**
- [x] **Step 3: Add XHTML text nodes.**
- [x] **Step 4: Represent read-only publications.**
- [x] **Step 5: Implement acceptance/probe.**
- [ ] **Step 6: Confirm reader tests GREEN on exact current head.**
- [x] **Step 7: Commit implementation.**

### Task 4: Register H7 edits and lower authorized owners to H4 XML

**Files:**
- Modify: `packages/markitdown/src/markitdown/twoways/ir/edits.py`
- Create: `packages/markitdown/src/markitdown/twoways/formats/epub/lowering.py`

**Interfaces:**
- Register `replace_epub_metadata_text`
- Register `replace_epub_xhtml_text`
- `lower_epub_member_edits(member_bytes: bytes, member_path: str, requested: Sequence[...]) -> tuple[DocumentIR, tuple[EditOperation, ...]]`

- [ ] **Step 1: Add Task 4 RED tests before production.**
- [ ] **Step 2: Add exactly the two H7 edit types to `INITIAL_EDIT_TYPES`.**
- [ ] **Step 3: Build fresh H4 XML IR per touched member.**
- [ ] **Step 4: Lower to `replace_xml_text`.**
- [ ] **Step 5: Group all edits for the same member into one H4 transaction.**
- [ ] **Step 6: Run focused lowering tests GREEN.**
- [ ] **Step 7: Commit.**

### Task 5: Implement transactional sparse EPUB writer and full candidate verifier

**Files:**
- Extend: `packages/markitdown/src/markitdown/twoways/formats/epub/package.py`
- Create: `packages/markitdown/src/markitdown/twoways/formats/epub/verification.py`
- Create: `packages/markitdown/src/markitdown/twoways/formats/epub/writer.py`

- [ ] **Step 1: Add writer/verifier RED tests before production.**
- [ ] **Step 2: Validate document/source/fresh native authority.**
- [ ] **Step 3: Preflight complete edit set before constructing candidates.**
- [ ] **Step 4: Patch touched members only into internal buffers using H4 `patch_xml`.**
- [ ] **Step 5: Build sparse EPUB candidate.**
- [ ] **Step 6: Re-read and verify complete candidate.**
- [ ] **Step 7: Write caller destination only after successful verification.**
- [ ] **Step 8: Run writer/preservation/verification tests GREEN and commit.**

### Task 6: Public adapter, projection boundary, and one-way regression lock

**Files:**
- Create: `packages/markitdown/src/markitdown/twoways/formats/epub/writer_adapter.py`
- Create: `packages/markitdown/src/markitdown/twoways/formats/epub/__init__.py`
- Modify only if required by existing projection dispatch: the smallest existing Markdown projection surface needed to mark EPUB identity blocks inspection-only
- Do not modify: `packages/markitdown/src/markitdown/converters/_epub_converter.py`

- [ ] **Step 1: Add public/projection/one-way RED tests before production.**
- [ ] **Step 2: Export the H7 format surface.**
- [ ] **Step 3: Add `EpubPatchWriter`.**
- [ ] **Step 4: Lock Markdown inspection-only behavior.**
- [ ] **Step 5: Lock existing one-way EPUB conversion.**
- [ ] **Step 6: Run public/import/Markdown/one-way tests GREEN and commit.**

### Task 7: Security hardening, scope audit, and documentation closure

**Files:**
- Modify: `TWOWAYS.md`
- Modify/add H7 tests only where the implementation exposed an uncovered security/preservation boundary

- [ ] **Step 1: Re-run full H7 focused suite.**
- [ ] **Step 2: Audit security failure paths.**
- [ ] **Step 3: Audit exact H6-to-H7 diff for protected one-way/H4 surfaces.**
- [ ] **Step 4: Document H7 capability/fidelity/read-only boundaries.**
- [ ] **Step 5: Run full package tests locally/CI as available.**
- [ ] **Step 6: Require exact final-head 9/9 CI GREEN before H7 completion.**
- [ ] **Step 7: Only then mark H7 complete and branch recursive ZIP from that exact SHA.**
