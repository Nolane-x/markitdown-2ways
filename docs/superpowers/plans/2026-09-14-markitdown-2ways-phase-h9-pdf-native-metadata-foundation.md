# Phase H9 PDF Native Metadata Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a bounded PDF 2Ways path that performs source-preserving Info metadata edits through verified append-only classic-xref incremental revisions.

**Architecture:** Parse only the native PDF structures H9 must own: final `startxref`, classic xref chains, trailers, catalog and Info dictionaries. Build deterministic `DocumentIR` metadata from that authority, route one typed `update_pdf_info` operation against a fresh parse, append a replacement/new Info object plus a classic xref/trailer revision, then re-read the candidate before emitting caller bytes. The existing one-way PDF converter remains isolated and unchanged.

**Tech Stack:** Python 3.10-3.13, stdlib `dataclasses`/`hashlib`/`io`/`re`, existing 2Ways IR/capability/writer contracts, existing optional `pdfminer.six` only as an independent test oracle.

**Spec:** `docs/superpowers/specs/2026-09-14-markitdown-2ways-phase-h9-pdf-native-metadata-foundation-design.md`

## Global Constraints

- Base exactly on H8 completion SHA `9a43768efde296330f8bbea542ffc5e926a2d735`.
- Protect `packages/markitdown/src/markitdown/converters/_pdf_converter.py` at blob `ffbcbd990cfc40a577404c453ebe47bf477c4929`.
- No whole-PDF serializer in the production H9 write path.
- Writable sources use classic xref tables only; reject xref streams and `/XRefStm` hybrids.
- Reject encrypted, signed-evidence, linearized and XMP dual-authority sources for mutation.
- H9 writes only `Title`, `Author`, `Subject`, `Keywords`, `Creator`, `Producer` through `update_pdf_info`.
- No metadata deletion; no arbitrary object/stream replacement.
- Every mutation candidate must preserve the complete original PDF as an exact byte prefix.
- Zero edits return exact source bytes without an appended revision.
- Caller output remains empty until final H9 verification succeeds.
- Identity Markdown for PDF is inspection-only.
- No network or subprocess I/O in the H9 core.
- Final completion requires one exact SHA with pre-commit + package 3.10-3.13 + OCR 3.10-3.13 = exact 9/9 GREEN.
- Do not merge H9 automatically.

---

## File Structure

Production files to create:

- `packages/markitdown/src/markitdown/twoways/formats/pdf/limits.py` — frozen parser resource limits.
- `.../pdf/model.py` — parse error and immutable native authority models.
- `.../pdf/lexer.py` — bounded PDF token/value scanner with raw spans.
- `.../pdf/parser.py` — `startxref`, classic xref chain, trailer/catalog/Info authority and eligibility.
- `.../pdf/reader.py` — PDF `DocumentIR` + capability mapping.
- `.../pdf/routing.py` — fresh edit resolution/preflight.
- `.../pdf/writer.py` — append-only incremental revision transaction.
- `.../pdf/verification.py` — complete candidate re-read and preservation proof.
- `.../pdf/writer_adapter.py` — `DocumentWriter` adapter.
- `.../pdf/__init__.py` — stable public facade.

Test files to create:

- `packages/markitdown/tests/twoways/_pdf_fixtures.py`
- `.../test_pdf_native_parser.py`
- `.../test_pdf_reader.py`
- `.../test_pdf_routing.py`
- `.../test_pdf_writer.py`
- `.../test_pdf_verification.py`
- `.../test_pdf_markdown.py`
- `.../test_pdf_public_imports.py`
- `.../test_pdf_oneway_regression.py`
- `.../test_pdf_security.py`

Documentation modified only during closure:

- `TWOWAYS.md`

No H1-H8 production adapter, CLI surface, or one-way PDF converter may be modified.

---

### Task 1: Deterministic PDF fixtures + native parser RED

**Files:**
- Create: `packages/markitdown/tests/twoways/_pdf_fixtures.py`
- Create: `packages/markitdown/tests/twoways/test_pdf_native_parser.py`

**Interfaces:**
- Produces fixture helper `make_classic_pdf(...) -> bytes`.
- Produces fixture helper `append_classic_revision(...) -> bytes` for valid incremental chains.
- Production target introduced later: `parse_pdf_source(source: bytes, *, limits: PdfNativeLimits | None = None) -> ParsedPdfSource`.

- [ ] **Step 1: Build offsets from real emitted bytes**

The fixture builder must calculate object and xref offsets after object serialization. The core pattern is:

```python
def make_classic_pdf(*, info: dict[str, str] | None = None, trailer_extra: bytes = b"") -> bytes:
    out = bytearray(b"%PDF-1.7\n")
    offsets: dict[int, int] = {}

    def emit_object(number: int, body: bytes) -> None:
        offsets[number] = len(out)
        out.extend(f"{number} 0 obj\n".encode("ascii"))
        out.extend(body)
        out.extend(b"\nendobj\n")

    emit_object(1, b"<< /Type /Catalog /Pages 2 0 R >>")
    emit_object(2, b"<< /Type /Pages /Kids [] /Count 0 >>")
    # Optional object 3 is Info.
    ...
    xref_offset = len(out)
    ...
    out.extend(f"startxref\n{xref_offset}\n%%EOF\n".encode("ascii"))
    return bytes(out)
```

- [ ] **Step 2: Write parser tests before production exists**

Cover at minimum:

```python
def test_parse_classic_pdf_resolves_effective_info():
    source = make_classic_pdf(info={"Title": "Alpha", "Author": "Ada"})
    parsed = parse_pdf_source(source)
    assert parsed.startxref > 0
    assert parsed.info is not None
    assert parsed.info.decoded_fields["Title"] == "Alpha"


def test_parse_incremental_chain_uses_newest_info_revision():
    first = make_classic_pdf(info={"Title": "Alpha"})
    source = append_classic_revision(first, info_updates={"Title": "Beta"})
    parsed = parse_pdf_source(source)
    assert parsed.revision_count == 2
    assert parsed.info.decoded_fields["Title"] == "Beta"
```

Also test `/Info` absence, literal and hex strings, newest-free override, real `/Prev` traversal and effective trailer `/Root`/`/ID` carry-forward.

- [ ] **Step 3: Commit test-only RED**

Commit only fixtures/tests. Expected package jobs: collection failure because `markitdown.twoways.formats.pdf` or `pdf.parser` does not exist. OCR jobs must remain unaffected.

- [ ] **Step 4: Capture exact RED CI evidence**

Do not write production until the RED is confirmed to be caused by missing H9 modules, not malformed fixtures or unrelated regressions.

---

### Task 2: Bounded lexer + classic xref/trailer/object authority

**Files:**
- Create: `.../pdf/limits.py`
- Create: `.../pdf/model.py`
- Create: `.../pdf/lexer.py`
- Create: `.../pdf/parser.py`
- Extend: `.../test_pdf_native_parser.py`

**Interfaces:**

`limits.py`:

```python
@dataclass(frozen=True)
class PdfNativeLimits:
    max_file_bytes: int = 512 * 1024 * 1024
    max_incremental_revisions: int = 64
    max_xref_subsections_per_revision: int = 65_536
    max_xref_entries_total: int = 1_000_000
    max_object_number: int = 10_000_000
    max_dictionary_bytes: int = 4 * 1024 * 1024
    max_pdf_string_bytes: int = 1 * 1024 * 1024
    max_lexer_nesting_depth: int = 64
    max_startxref_search_bytes: int = 1 * 1024 * 1024
```

`model.py` minimum contracts:

```python
class PdfParseError(ValueError):
    def __init__(self, message: str, *, reason: str, details: Mapping[str, object] | None = None): ...

@dataclass(frozen=True)
class PdfIndirectRef:
    object_number: int
    generation: int

@dataclass(frozen=True)
class PdfRawValue:
    start: int
    end: int
    raw: bytes
    value: object

@dataclass(frozen=True)
class PdfXrefEntry:
    object_number: int
    generation: int
    offset: int
    in_use: bool

@dataclass(frozen=True)
class PdfInfoSnapshot:
    ref: PdfIndirectRef
    raw_dictionary: bytes
    decoded_fields: Mapping[str, str]
    raw_values: Mapping[str, bytes]

@dataclass(frozen=True)
class ParsedPdfSource:
    source_sha256: str
    source_size: int
    startxref: int
    revision_count: int
    effective_size: int
    root_ref: PdfIndirectRef
    document_id_raw: bytes | None
    info: PdfInfoSnapshot | None
    trailer_values_raw: Mapping[str, bytes]
    xmp_present: bool
    encrypted: bool
    signed_evidence: bool
    linearized: bool
    writable: bool
    read_only_reason: str | None
```

`lexer.py` must expose bounded top-level dictionary parsing with raw spans, e.g.:

```python
def parse_pdf_dictionary(data: bytes, start: int, *, limits: PdfNativeLimits) -> PdfDictionarySnapshot: ...
def decode_pdf_text_string(raw: bytes, *, limits: PdfNativeLimits) -> str: ...
def encode_pdf_text_string(value: str) -> bytes: ...  # UTF-16BE hex with FEFF
```

`parser.py`:

```python
def parse_pdf_source(source: bytes, *, limits: PdfNativeLimits | None = None) -> ParsedPdfSource: ...
```

- [ ] **Step 1: Make lexer RED explicit**

Add focused tests for balanced literal strings, escapes, hex strings, comments, arrays, nested dictionaries, indirect references and malformed nesting.

- [ ] **Step 2: Implement lexer without stream decoding**

The lexer must stop at exact structural boundaries and reject catalog/Info authority that contains unexpected `stream` semantics. Preserve raw key/value spans.

- [ ] **Step 3: Implement final `startxref` discovery**

Search only the last `max_startxref_search_bytes`, require bounded trailing whitespace after final `%%EOF`, parse the decimal offset and verify it is in range.

- [ ] **Step 4: Implement classic xref revision parser**

Parse subsection headers and fixed entries, allowing PDF line endings `\n`, `\r\n` or `\r`. Reject duplicate/overlapping object numbers in one revision and enforce limits.

- [ ] **Step 5: Walk `/Prev` chain newest -> oldest**

Cycle-check offsets and stop after `max_incremental_revisions`. Build newest-first object authority; a newer free entry overrides an older in-use entry.

- [ ] **Step 6: Resolve effective trailer/catalog/Info**

Require an effective indirect `/Root`. Reject `/Encrypt`, `/XRefStm`, xref streams and unsupported object authority. Inspect catalog `/Metadata` and conservative signature markers. Record read-only reason instead of advertising write capability for supported-readable but non-writable cases.

- [ ] **Step 7: Implement deterministic PDF text strings**

Decode bounded literal/hex text strings. New writes use:

```python
def encode_pdf_text_string(value: str) -> bytes:
    payload = b"\xfe\xff" + value.encode("utf-16-be")
    return b"<" + payload.hex().upper().encode("ascii") + b">"
```

Reject embedded NUL and invalid Unicode inputs before write routing.

- [ ] **Step 8: Run focused GREEN and full exact-head gate**

All Task 1/2 tests must pass. Then require fresh pre-commit + package 3.10-3.13 + OCR 3.10-3.13 before declaring Task 2 exact-green.

---

### Task 3: PDF `DocumentIR` reader + capability boundary

**Files:**
- Create: `.../pdf/reader.py`
- Create: `.../test_pdf_reader.py`

**Interfaces:**

```python
def read_pdf_ir(
    source: BinaryIO,
    *,
    filename: str | None = None,
    mimetype: str | None = None,
    limits: PdfNativeLimits | None = None,
) -> DocumentIR: ...

class PdfIRReader(DocumentIRReader): ...
```

Use a deterministic root node and metadata node:

```python
Node(
    node_id=...,
    kind="group",
    semantic_role="pdf-document",
    ...,
)

Node(
    node_id=...,
    kind="unknown_native",
    semantic_role="pdf-info",
    parent_id=root_id,
    payload={"fields": dict(parsed.info.decoded_fields) if parsed.info else {}},
    metadata={
        "pdf.startxref": parsed.startxref,
        "pdf.info_present": parsed.info is not None,
        "pdf.xref_kind": "classic",
        "pdf.identity_markdown": False,
        CAPABILITY_METADATA_KEY: encode_capabilities((decision,)),
        ...,
    },
)
```

`update_pdf_info` is writable only when `parsed.writable` is true; otherwise expose the exact stable `parsed.read_only_reason`.

- [ ] **Step 1: Write reader RED tests**

Test deterministic IDs, source SHA/size, one document canvas, root/info hierarchy, existing/absent Info payload, native locator binding, capability writable/read-only reasons and `pdf.identity_markdown=False`.

- [ ] **Step 2: Implement minimal reader**

Follow existing `SourceDescriptor`, `Canvas`, `Node`, `NativeLocator`, `Provenance`, `CAPABILITY_METADATA_KEY`, `validate_document` patterns. Do not import one-way PDF conversion code.

- [ ] **Step 3: Verify forged/non-writable structures remain represented but non-writable**

Encrypted/XMP/signed/linearized classic PDFs that are safe enough to inspect should produce deterministic read-only diagnostics rather than silently gaining capability.

- [ ] **Step 4: Run focused and exact-head GREEN**

Require fresh exact CI before Task 4.

---

### Task 4: Fresh routing + transactional incremental writer

**Files:**
- Create: `.../pdf/routing.py`
- Create: `.../pdf/writer.py`
- Create: `.../test_pdf_routing.py`
- Create: `.../test_pdf_writer.py`

**Interfaces:**

`routing.py`:

```python
@dataclass(frozen=True)
class PdfInfoUpdate:
    key: str
    old_value: str | None
    value: str

@dataclass(frozen=True)
class PdfRoutedEdit:
    operation: EditOperation
    updates: tuple[PdfInfoUpdate, ...]
    fresh_info_ref: PdfIndirectRef | None


def resolve_pdf_edit(
    document: DocumentIR,
    parsed: ParsedPdfSource,
    edit: EditOperation,
) -> PdfRoutedEdit: ...
```

`writer.py`:

```python
def patch_pdf(
    document: DocumentIR,
    source_stream: BinaryIO,
    output: BinaryIO,
    *,
    edits: Sequence[EditOperation],
    limits: PdfNativeLimits | None = None,
) -> WriterResult: ...
```

- [ ] **Step 1: Write routing RED tests**

Required failures before output:

- stale source SHA/size;
- unknown target;
- non-`pdf-info` target;
- operation not `update_pdf_info`;
- forged startxref/native locator evidence;
- stale Info ref/raw digest;
- unsupported key;
- duplicate key;
- `old_value` mismatch;
- exact no-op update;
- duplicate `operation_id`;
- multiple edits that target the same PDF Info field.

- [ ] **Step 2: Implement fresh source authority validation**

Read source once, compare descriptor format/SHA/size, parse again with H9 limits and compare the caller node's recorded native evidence against the fresh parse.

- [ ] **Step 3: Implement typed edit normalization**

Normalize payload `updates` to sorted unique `PdfInfoUpdate` values, require six allowed keys, string `value`, exact fresh `old_value`, and common edit preconditions via `validate_edit_preconditions`.

- [ ] **Step 4: Write append-only writer RED tests**

Success tests must assert:

```python
candidate.startswith(source)
assert candidate[: len(source)] == source
```

Cover existing-field replacement, adding a field to existing Info, creating Info when absent, multi-field transaction and zero-edit exact identity.

- [ ] **Step 5: Implement existing Info revision**

Patch only requested raw value spans inside a copy of `PdfInfoSnapshot.raw_dictionary`; insert absent keys immediately before the matching top-level `>>`. Append the same object number/generation as a new revision.

- [ ] **Step 6: Implement absent Info creation**

Allocate object number `parsed.effective_size` only after proving it is not effective/in-use. Emit generation 0 and sorted requested keys.

- [ ] **Step 7: Append classic xref + trailer**

Compute absolute appended offsets from `len(source)` plus the appended separator/object bytes. Emit object 0 free entry and the authored Info entry as classic xref subsections. Carry safe effective trailer raw values, own `/Size`, `/Root`, `/Info`, `/Prev`, preserve `/ID`, then emit `startxref` and `%%EOF`.

- [ ] **Step 8: Keep output empty until candidate is complete**

Build into `BytesIO`/bytes only. Do not call `output.write()` yet; Task 5 verification must run first.

- [ ] **Step 9: Run focused GREEN and exact-head gate**

Task 4 is not complete on focused tests alone.

---

### Task 5: Candidate verification + rollback proof

**Files:**
- Create: `.../pdf/verification.py`
- Create: `.../test_pdf_verification.py`
- Modify: `.../pdf/writer.py`
- Extend: `.../test_pdf_writer.py`

**Interfaces:**

```python
def verify_pdf_candidate(
    original: ParsedPdfSource,
    source: bytes,
    candidate: bytes,
    *,
    requested: Sequence[PdfRoutedEdit],
    limits: PdfNativeLimits | None = None,
) -> ParsedPdfSource: ...
```

- [ ] **Step 1: Write verifier RED tests**

Reject:

- candidate whose source prefix differs by one byte;
- candidate `/Prev` not equal original `startxref`;
- changed effective `/Root`;
- changed raw `/ID`;
- requested field semantic mismatch;
- unrequested existing Info raw-token drift;
- malformed new xref/trailer;
- unauthorized extra Info field mutation.

- [ ] **Step 2: Implement strict re-read verification**

Call `parse_pdf_source(candidate)` and compare native invariants. Reconstruct the set of requested keys across routed edits and require every other pre-existing Info raw token to match exactly.

- [ ] **Step 3: Integrate verifier before destination write**

`patch_pdf` flow becomes:

```python
candidate = _build_incremental_candidate(...)
verified = verify_pdf_candidate(...)
output.write(candidate)
return WriterResult(...)
```

Any exception before `output.write` leaves output empty.

- [ ] **Step 4: Add rollback test**

Force verifier failure through a test seam or a directly tested invalid candidate path; assert `output.getvalue() == b""`.

- [ ] **Step 5: Emit fidelity evidence**

Zero edits: `exact-preserve`.

Mutation: `high`, with evidence keys:

- `pdf.source_prefix_exact`
- `pdf.incremental_revision`
- `pdf.classic_xref_chain`
- `pdf.root_reference_preserved`
- `pdf.document_id_preserved` when present
- `pdf.unrequested_info_raw_tokens_preserved`
- `pdf.requested_info_semantics`
- `pdf.candidate_reread`

- [ ] **Step 6: Exact-head GREEN gate**

Require 9/9 before public surface work.

---

### Task 6: Public facade + writer adapter + Markdown boundary + one-way regression

**Files:**
- Create: `.../pdf/__init__.py`
- Create: `.../pdf/writer_adapter.py`
- Create: `.../test_pdf_public_imports.py`
- Create: `.../test_pdf_markdown.py`
- Create: `.../test_pdf_oneway_regression.py`
- Modify shared Markdown projection only if a dedicated RED proves the H8 guard is insufficient.

**Interfaces:**

Public imports:

```python
from markitdown.twoways.formats.pdf import (
    PdfIRReader,
    PdfNativeLimits,
    PdfParseError,
    PdfPatchWriter,
    parse_pdf_source,
    patch_pdf,
    read_pdf_ir,
)
```

Writer adapter mirrors existing package adapters:

```python
class PdfPatchWriter(DocumentWriter):
    def accepts(self, document: DocumentIR, target: TargetInfo, **kwargs: Any) -> bool:
        del kwargs
        source_format = document.source.format if document.source is not None else None
        extension = (target.extension or "").lower()
        return source_format == "pdf" and (
            target.format.lower() == "pdf" or extension == ".pdf"
        )

    def write(self, document, output, target, **kwargs):
        del target
        source_stream = kwargs.pop("source_stream", None)
        edits = kwargs.pop("edits", None)
        limits = kwargs.pop("limits", None)
        if source_stream is None or edits is None:
            raise TypeError("PdfPatchWriter.write requires source_stream= and edits=")
        if kwargs:
            raise TypeError(f"unexpected PDF writer options: {sorted(kwargs)}")
        return patch_pdf(document, source_stream, output, edits=tuple(edits), limits=limits)
```

- [ ] **Step 1: RED public imports and adapter tests**

Test accepts/rejects target formats, required kwargs and stable facade symbols.

- [ ] **Step 2: RED identity-Markdown inspection-only test**

Project a PDF IR in identity mode, mutate visible metadata text, import it, and assert the importer emits no PDF metadata edit. If existing generic guard already passes, do not modify shared Markdown code.

- [ ] **Step 3: Lock one-way converter blob and behavior**

Assert `_pdf_converter.py` Git blob remains `ffbcbd990cfc40a577404c453ebe47bf477c4929` through a source-tree lock test or equivalent repository fixture used by prior one-way regression tests. Add a representative current one-way PDF conversion regression without importing H9 production into the converter.

- [ ] **Step 4: Independent pdfminer oracle**

For a synthetic PDF with simple extractable page text, patch only Info metadata, reopen both source/candidate through `pdfminer.six`, and assert extracted page text is identical while candidate metadata reflects requested values where the oracle exposes them.

- [ ] **Step 5: Exact-head GREEN gate**

Require pre-commit and full package/OCR matrices.

---

### Task 7: Security hardening + docs + final exact-head closure

**Files:**
- Create: `.../test_pdf_security.py`
- Modify only if RED proves a gap: H9 `pdf/*` production files.
- Modify: `TWOWAYS.md`

**Interfaces:**
- No new public operation.
- Security tests exercise frozen spec reasons and output-empty failure semantics.

- [ ] **Step 1: Audit before adding tests**

Check whether existing Task 1-6 tests already cover every frozen adversarial item. Add only missing cases; do not duplicate tests for checklist optics.

- [ ] **Step 2: Add missing adversarial RED tests**

Frozen checklist:

- malformed/missing `startxref`;
- out-of-bounds `startxref`;
- xref stream;
- `/XRefStm` hybrid;
- malformed subsections;
- duplicate/overlapping entries;
- wrong object number/generation at xref offset;
- newest-free override;
- `/Prev` cycle;
- revision limit;
- xref-entry limit;
- dictionary/string/nesting limits;
- encryption;
- linearization;
- signature evidence;
- XMP dual authority;
- malformed/stream-backed Info;
- ambiguous Info text encoding;
- stale source;
- stale Info identity/digest;
- stale old value;
- duplicate/conflicting fields;
- unsupported keys;
- no-op update;
- rollback on inner/preflight failure;
- rollback on final verification failure;
- exact source-prefix preservation on success.

- [ ] **Step 3: Implement only gaps proven by RED**

Do not broaden H9 capability to make an adversarial test pass. Fail closed instead.

- [ ] **Step 4: Update `TWOWAYS.md`**

Document:

- H9 PDF native metadata boundary;
- append-only incremental revision model;
- classic-xref-only limitation;
- writable fields and `update_pdf_info`;
- signed/encrypted/linearized/XMP/xref-stream read-only boundaries;
- zero-edit `exact-preserve`, mutation `high`;
- identity Markdown inspection-only;
- protected one-way converter;
- H10 annotations/forms/links and later content-stream work.

Add PDF H9 to the capability matrix.

- [ ] **Step 5: Exact H8 -> H9 scope audit**

Base:

`9a43768efde296330f8bbea542ffc5e926a2d735`

Allowed production delta:

- `packages/markitdown/src/markitdown/twoways/formats/pdf/*`
- shared Markdown projection only if dedicated H9 RED forced the smallest necessary guard
- `TWOWAYS.md`
- H9 spec/plan/tests

Forbidden delta:

- `_pdf_converter.py`
- H1-H8 production adapters
- CLI
- unrelated dependencies/packaging unless a dedicated H9 RED proves necessity

- [ ] **Step 6: Verify protected one-way PDF blob**

It must still equal:

`ffbcbd990cfc40a577404c453ebe47bf477c4929`

- [ ] **Step 7: Run final exact-head 9/9**

Require fresh success for:

1. pre-commit
2. package 3.10
3. package 3.11
4. package 3.12
5. package 3.13
6. OCR 3.10
7. OCR 3.11
8. OCR 3.12
9. OCR 3.13

- [ ] **Step 8: Freeze the exact H9 completion SHA**

After this SHA, do not add source/test/doc commits. Update PR title/body and mark Ready for review without changing the branch SHA. Do not merge automatically.
