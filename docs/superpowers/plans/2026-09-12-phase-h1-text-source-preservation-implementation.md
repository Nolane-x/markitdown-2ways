# Phase H1 Text Source Preservation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add deterministic, source-preserving two-way support for native plain-text and Markdown files while retaining exact source encoding, BOM and unambiguous newline convention.

**Architecture:** Introduce a focused `twoways.formats.text` adapter built around one authoritative text node. Reader-side representation helpers prove reversible decoding and classify newline/BOM metadata; the writer reuses existing `replace_text`, capability and semantic-precondition contracts, performs full preflight, encodes back into the original representation, then re-reads and verifies the candidate before writing it.

**Tech Stack:** Python 3.10–3.13, standard-library codecs/hashlib/io, existing `charset-normalizer`, `DocumentIR`, capability kernel, Markdown projection/import, pytest, pre-commit.

**Spec:** `docs/superpowers/specs/2026-09-12-markitdown-2ways-phase-h1-text-source-preservation-design.md`

## Global Constraints

- Keep the existing one-way `MarkItDown` API and CLI unchanged.
- No silent transcoding or newline selection.
- No production code before a focused failing test demonstrates the missing behavior.
- Source bytes must match `DocumentIR.source.sha256` and `size_bytes` before mutation.
- Unknown/unadvertised capabilities remain read-only.
- Zero-edit and semantic no-op writes are byte-identical.
- No CSV/JSON/XML/HTML mutation in H1.
- Full Python 3.10–3.13 package CI, OCR CI and pre-commit must be green before merge.

---

## File Structure

### Text representation
- Create `packages/markitdown/src/markitdown/twoways/formats/text/model.py` for immutable representation metadata and BOM/newline enums.
- Create `packages/markitdown/src/markitdown/twoways/formats/text/codec.py` for strict reversible decoding, encoding and newline normalization.

### Reader and writer
- Create `packages/markitdown/src/markitdown/twoways/formats/text/reader.py` to construct deterministic `DocumentIR` and capability metadata.
- Create `packages/markitdown/src/markitdown/twoways/formats/text/writer.py` for source verification, edit preflight, exact representation writeback and re-read verification.
- Create `packages/markitdown/src/markitdown/twoways/formats/text/__init__.py` for lazy public imports.

### Tests
- Create `packages/markitdown/tests/twoways/test_text_codec.py`.
- Create `packages/markitdown/tests/twoways/test_text_reader.py`.
- Create `packages/markitdown/tests/twoways/test_text_writer.py`.
- Create `packages/markitdown/tests/twoways/test_text_public_imports.py`.

### Documentation
- Modify `TWOWAYS.md` only after implementation verification to document H1’s bounded capability.

---

### Task 1: Define reversible text representation with RED tests

**Files:**
- Create: `packages/markitdown/tests/twoways/test_text_codec.py`
- Create after RED: `packages/markitdown/src/markitdown/twoways/formats/text/model.py`
- Create after RED: `packages/markitdown/src/markitdown/twoways/formats/text/codec.py`

**Interfaces:**
- Produces `TextRepresentation(encoding: str, bom: str, newline: str, byte_roundtrip: bool)`.
- Produces `decode_text_source(source: bytes, *, encoding: str | None = None) -> tuple[str, TextRepresentation]`.
- Produces `encode_text_source(text: str, representation: TextRepresentation) -> bytes`.
- Produces `normalize_newlines(text: str, newline: str) -> str`.

- [ ] Write tests for UTF-8, UTF-8 BOM, UTF-16 LE/BE BOM, explicit reversible legacy encoding, CR/LF/CRLF/mixed classification, exact byte round-trip, unencodable output, and `newline=none` refusing introduced line breaks.
- [ ] Run `pytest packages/markitdown/tests/twoways/test_text_codec.py -q` and confirm RED because `markitdown.twoways.formats.text` is absent.
- [ ] Implement only the representation/codec behavior required by the tests. BOM bytes are not exposed as decoded text. Fallback charset detection is accepted as writable only after exact strict re-encoding proves equality.
- [ ] Re-run the focused test and require GREEN.
- [ ] Commit `feat: add reversible text source codec`.

### Task 2: Build deterministic text IR and capabilities

**Files:**
- Create: `packages/markitdown/tests/twoways/test_text_reader.py`
- Create after RED: `packages/markitdown/src/markitdown/twoways/formats/text/reader.py`

**Interfaces:**
- Produces `read_text_ir(source, *, filename=None, mimetype=None, encoding=None) -> DocumentIR`.
- Produces `TextIRReader.read(...) -> DocumentIR`.
- Root node locator is `NativeLocator(backend="text", part_uri="/", object_id="document-body")`.
- Root metadata keys are `text.encoding`, `text.bom`, `text.newline`, `text.byte_roundtrip`, `text.format`.

- [ ] Write RED tests for deterministic canonical digest, source SHA/size, exact text payload, filename-driven `text` vs `markdown`, locator identity and writable `replace_text` capability.
- [ ] Add RED read-only tests for mixed newlines and non-roundtrippable representation; assert stable reason codes.
- [ ] Run focused reader tests and confirm RED for the missing reader.
- [ ] Implement one text canvas and one authoritative text node with deterministic IDs seeded by source SHA-256. Encode capabilities through `encode_capabilities`; never infer writability in the writer from node existence.
- [ ] Validate documents with the existing IR validator in tests and require GREEN.
- [ ] Commit `feat: read text sources into document ir`.

### Task 3: Define writer preflight and source identity

**Files:**
- Create: `packages/markitdown/tests/twoways/test_text_writer.py`
- Create after RED: `packages/markitdown/src/markitdown/twoways/formats/text/writer.py`

**Interfaces:**
- Produces `patch_text(document, source, destination, *, edits=()) -> None`.
- Produces `TextPatchWriter.write(document, source, destination, *, edits=()) -> None`.

- [ ] Write RED tests proving zero edits copy source bytes exactly and source hash/size mismatch raises `SourcePackageMismatchError` without writing destination bytes.
- [ ] Add RED tests for unsupported edit type, wrong target, duplicate target replacement, unknown payload keys, non-string `text`, and missing writable capability.
- [ ] Run focused writer tests and confirm RED.
- [ ] Implement complete edit-set preflight before candidate bytes are produced. Source identity must be checked first; capability state must be exactly `WRITABLE` for `replace_text`.
- [ ] Re-run focused tests GREEN.
- [ ] Commit `feat: preflight text source patches`.

### Task 4: Add transactional replace-text writeback

**Files:**
- Extend: `packages/markitdown/tests/twoways/test_text_writer.py`
- Modify after RED: `packages/markitdown/src/markitdown/twoways/formats/text/writer.py`

**Interfaces:**
- Reuses `validate_edit_preconditions(document, node, edit, format_label="text")`.
- Replacement payload remains `{"text": str}`.

- [ ] Write RED tests for LF, CRLF and CR writeback, UTF-8 BOM preservation, UTF-16 BOM preservation, and semantic no-op byte identity.
- [ ] Add RED stale-precondition tests for expected semantic digest, native-locator digest and old value.
- [ ] Add RED test proving edited characters not encodable in the preserved codec fail before destination bytes are emitted.
- [ ] Implement newline normalization and strict re-encoding only after full preflight. For `newline=none`, reject replacement containing any newline. Return original bytes for semantic no-op.
- [ ] Re-run focused writer tests GREEN.
- [ ] Commit `feat: patch text while preserving source representation`.

### Task 5: Re-read verification and Markdown-native coverage

**Files:**
- Extend: `packages/markitdown/tests/twoways/test_text_writer.py`
- Extend: `packages/markitdown/tests/twoways/test_text_reader.py`
- Modify after RED: `packages/markitdown/src/markitdown/twoways/formats/text/writer.py`

- [ ] Write RED test that monkeypatches/isolates candidate verification so representation drift is rejected with `RoundTripVerificationError` rather than emitted.
- [ ] Add native `.md` tests showing the same text adapter preserves exact source representation and advertises `replace_text`; do not introduce a second Markdown parser.
- [ ] Implement candidate re-read verification: semantic text, source format classification, encoding, BOM and newline representation must match the authorized target contract.
- [ ] Re-run codec/reader/writer suites GREEN.
- [ ] Commit `test: verify text source round trips`.

### Task 6: Public imports and existing identity-Markdown integration

**Files:**
- Create: `packages/markitdown/tests/twoways/test_text_public_imports.py`
- Create after RED: `packages/markitdown/src/markitdown/twoways/formats/text/__init__.py`
- Modify only if required by current public patterns: `packages/markitdown/src/markitdown/twoways/formats/__init__.py`

- [ ] Write RED import tests for `TextIRReader`, `TextPatchWriter`, `read_text_ir`, `patch_text`.
- [ ] Add a regression test projecting a native Markdown text document through existing identity Markdown and importing one lossless text edit; assert emitted operation is existing `replace_text`.
- [ ] Run tests and confirm RED only for missing public adapter surface or integration gap.
- [ ] Add lazy public imports following the XLSX adapter pattern. Change generic Markdown code only if the focused regression proves an actual integration gap.
- [ ] Run focused public-import + Markdown round-trip tests GREEN.
- [ ] Commit `feat: expose text round trip adapter`.

### Task 7: Documentation and regression verification

**Files:**
- Modify: `TWOWAYS.md`

- [ ] Document H1 support, supported representation guarantees, stable read-only reasons and the distinction between native Markdown source and identity Markdown projection.
- [ ] Run all `packages/markitdown/tests/twoways` tests.
- [ ] Run the full package suite with the project’s Hatch command locally when available; otherwise require GitHub Actions Python 3.10–3.13 matrix on the exact PR head.
- [ ] Run pre-commit on all files locally when available; otherwise require the repository pre-commit workflow on the exact PR head.
- [ ] Confirm OCR workflow remains green because the sibling package is installed against this checkout.
- [ ] Review diff for accidental one-way converter/API changes; there must be none unless a failing regression required one.
- [ ] Commit `docs: document source preserving text round trips`.

## Completion Gate

H1 is mergeable only when the exact PR head has green package tests for Python 3.10, 3.11, 3.12 and 3.13, green OCR matrix, green pre-commit, no unresolved review blockers, and the final diff remains limited to the H1 adapter/tests/docs. Do not advertise CSV/JSON/XML/HTML as writable until their own preservation tranches exist.
