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

- [x] Design spec approved, self-reviewed and committed.
- [x] Implementation plan frozen before production work.
- [x] Task 1 deterministic EPUB fixtures and RED contract families established.
- [x] Task 2 safe OCF ZIP snapshot and EPUB semantic parser implemented.
- [x] Task 3 deterministic EPUB `DocumentIR` reader and capabilities implemented and matrix-green.
- [x] Task 4 exact two-edit registry surface plus fresh-H4 XML lowering implemented by RED -> GREEN TDD.
- [x] Task 5 transactional sparse EPUB writer and full candidate verifier implemented; exact-head gate was GREEN at `344f88399075895440a35bb4bfa075cac6203263` (workflow run #327).
- [x] Task 6 public adapter/facade, inspection-only identity Markdown and one-way EPUB regression lock implemented; exact-head 9/9 GREEN at `b119f7f2f5c27caf3fd089e4d68620d4dca5256d` (workflow run #333).
- [x] Task 7 security audit identified unsupported ZIP compression as a real uncovered boundary. RED `37712860bb7a04407e12db8653331bc7cffd1c2f` failed on all four package Python jobs with `DID NOT RAISE EpubParseError`; production guard `440b489b82dee73b68d902e1f34b161d9763d9bd` restricts EPUB entries to Stored/Deflate.
- [x] Task 7 additional package-limit and symbolic-link fail-closed coverage added at `854d74151c9ef07efc16e7ca8b5eff415cd70d11`.
- [x] H6-to-H7 scope audit confirms production changes are confined to `twoways/formats/epub/*` plus exactly two shared edit-registry entries; H4 XML and the one-way EPUB converter remain untouched.
- [x] `TWOWAYS.md` updated for the actual H7 production boundary, fidelity model, security model and roadmap.
- [ ] **External exact-head completion gate:** after this plan-closure commit and all remaining documentation-only commits, freeze the branch and require pre-commit + eight Python matrix jobs GREEN. Record the immutable completion SHA/run in PR #14 rather than adding a post-gate commit that would invalidate the proof.

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
- [x] **Step 2: Encode OCF/package RED tests.**
- [x] **Step 3: Encode reader/capability RED tests.**
- [x] **Step 4: Encode writer/verification RED tests before Task 5 production.**
- [x] **Step 5: Encode identity Markdown and one-way regression tests before Task 6 production.**
- [x] **Step 6: Confirm intended RED signatures before the associated production code.**
- [x] **Step 7: Keep RED contracts separate from production commits.**

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
- [x] **Step 7: Run package/parser tests through the full package matrix.**
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
- [x] **Step 5: Implement acceptance/probe without moving the caller stream.**
- [x] **Step 6: Confirm reader tests and complete package/OCR matrices GREEN.**
- [x] **Step 7: Commit implementation.**

### Task 4: Register H7 edits and lower authorized owners to H4 XML

**Files:**
- Modify: `packages/markitdown/src/markitdown/twoways/ir/edits.py`
- Create: `packages/markitdown/src/markitdown/twoways/formats/epub/lowering.py`

**Interfaces:**
- Register `replace_epub_metadata_text`
- Register `replace_epub_xhtml_text`
- `lower_epub_member_edits(member_bytes: bytes, member_path: str, requested: Sequence[...]) -> tuple[DocumentIR, tuple[EditOperation, ...]]`

- [x] **Step 1: Add Task 4 RED tests before production.**
- [x] **Step 2: Add exactly the two H7 edit types to `INITIAL_EDIT_TYPES`.**
- [x] **Step 3: Build fresh H4 XML IR per touched member.**
- [x] **Step 4: Lower to `replace_xml_text`.**
- [x] **Step 5: Group edits transactionally per member.**
- [x] **Step 6: Run focused and full matrix tests GREEN.**
- [x] **Step 7: Commit.**

### Task 5: Implement transactional sparse EPUB writer and full candidate verifier

**Files:**
- Extend: `packages/markitdown/src/markitdown/twoways/formats/epub/package.py`
- Create: `packages/markitdown/src/markitdown/twoways/formats/epub/verification.py`
- Create: `packages/markitdown/src/markitdown/twoways/formats/epub/writer.py`

- [x] **Step 1: Add writer/verifier RED tests before production.**
- [x] **Step 2: Validate document/source/fresh native authority.**
- [x] **Step 3: Preflight complete edit set before constructing candidates.**
- [x] **Step 4: Patch touched members only into internal buffers using H4 `patch_xml`.**
- [x] **Step 5: Build sparse EPUB candidate while preserving ordered inventory and untouched member content.**
- [x] **Step 6: Re-read and verify complete candidate.**
- [x] **Step 7: Write caller destination only after successful verification.**
- [x] **Step 8: Run writer/preservation/verification tests GREEN and commit.**

### Task 6: Public adapter, projection boundary, and one-way regression lock

**Files:**
- Create: `packages/markitdown/src/markitdown/twoways/formats/epub/writer_adapter.py`
- Create: `packages/markitdown/src/markitdown/twoways/formats/epub/__init__.py`
- Do not modify: `packages/markitdown/src/markitdown/converters/_epub_converter.py`

- [x] **Step 1: Add public/projection/one-way tests and observe clean RED for the missing EPUB facade/adapter.**
- [x] **Step 2: Export the H7 format surface.**
- [x] **Step 3: Add `EpubPatchWriter`.**
- [x] **Step 4: Lock Markdown inspection-only behavior without changing Markdown core.**
- [x] **Step 5: Lock existing one-way EPUB conversion without modifying `_epub_converter.py`.**
- [x] **Step 6: Run exact-head pre-commit/package/OCR 9/9 GREEN at `b119f7f2f5c27caf3fd089e4d68620d4dca5256d`.**

### Task 7: Security hardening, scope audit, and documentation closure

**Files:**
- Modify: `TWOWAYS.md`
- Modify/add H7 tests only where the implementation exposed an uncovered security/preservation boundary
- Reconcile: this implementation plan

- [x] **Step 1: Re-run the full H7 and repository suite throughout hardening.**
- [x] **Step 2: Audit security failure paths.** Added explicit unsupported-compression RED proof plus member-count/per-member/total/XML-size and symbolic-link guards.
- [x] **Step 3: Audit exact H6-to-H7 diff for protected one-way/H4 surfaces.** No H4 XML or one-way EPUB converter production diff; only two shared edit type registrations outside the H7 format package.
- [x] **Step 4: Document H7 capability/fidelity/read-only/security boundaries in `TWOWAYS.md`.**
- [x] **Step 5: Preserve recursive generic ZIP as a separate future tranche rather than expanding H7.**
- [ ] **Step 6: Freeze the final branch head and require exact-head pre-commit + package 3.10-3.13 + OCR 3.10-3.13 = 9/9 GREEN.** This checkbox is intentionally closed externally in PR #14 after CI, because committing a checkbox change afterward would invalidate the exact-head proof.
- [ ] **Step 7: Record immutable H7 completion SHA/run in PR #14 and only then use that SHA as the base for recursive ZIP.** No post-gate source/docs commit is permitted.
