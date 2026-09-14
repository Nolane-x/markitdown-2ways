# MarkItDown 2Ways Phase H9 PDF Native Metadata Foundation Design

## Status

Approved implementation design for the first v0.7 PDF tranche.

H9 starts exactly from the frozen H8 completion commit:

`9a43768efde296330f8bbea542ffc5e926a2d735`

The branch is:

`phase-h9-pdf-native-metadata-foundation`

H9 is intentionally narrower than the complete v0.7 PDF program. It builds the native PDF object/xref authority and proves append-only incremental update semantics through bounded Info-dictionary metadata edits. Annotation/form/link mutation belongs to the next PDF tranche. Selected text/image mutation remains later still and must not be implemented until font/content-stream/object-graph ownership can be proved independently.

The existing one-way PDF converter is protected and must remain unchanged:

`packages/markitdown/src/markitdown/converters/_pdf_converter.py`

Frozen H8 blob SHA:

`ffbcbd990cfc40a577404c453ebe47bf477c4929`

## Goal

Add a source-preserving PDF 2Ways path that can:

1. parse a deliberately bounded subset of native PDF cross-reference and trailer structure;
2. represent the effective standard Info dictionary as deterministic `DocumentIR` metadata;
3. expose a single typed metadata operation only when native authority is provable;
4. write mutations as an append-only PDF incremental revision rather than rewriting the original file;
5. preserve the complete original PDF byte-for-byte as the prefix of every mutated candidate;
6. strictly re-read and verify the candidate before returning any destination bytes;
7. fail closed on encrypted, signed, linearized, XMP-conflicted, xref-stream/hybrid, malformed or otherwise unsupported PDF structures.

The central H9 invariant is:

> A metadata edit may append a new authoritative revision, but it must never rewrite or normalize the existing PDF bytes.

## Why H9 starts with metadata

PDF text and images are not ordinary scalar fields. Visible page content may depend on content streams, graphics state, resource inheritance, font encodings, composite fonts, CMaps, text matrices, image XObjects, object streams, incremental revisions and signed-byte ranges. A generic PDF serializer can therefore produce a readable file while silently rewriting unrelated native structure.

The Info dictionary is a much smaller authority surface. It is trailer-addressed, semantically bounded and can be superseded by one incremental object revision. That makes it the correct first place to prove:

- classic xref-chain parsing;
- authoritative indirect-object resolution;
- raw token ownership;
- append-only incremental updates;
- stale-source rejection;
- effective-trailer reconstruction;
- independent candidate verification.

H9 deliberately does not use a whole-PDF save operation from `pypdf`, `PyPDF2`, `pikepdf`, PyMuPDF or another serializer as the production mutation path.

## Scope

### Writable in H9

H9 supports one operation:

`update_pdf_info`

The writable standard Info text fields are:

- `Title`
- `Author`
- `Subject`
- `Keywords`
- `Creator`
- `Producer`

The operation may replace an existing supported field or add a previously absent supported field. Deletion is not writable in H9.

### Read-only metadata in H9

The following standard Info entries may be represented when safely readable but are not writable in H9:

- `CreationDate`
- `ModDate`
- `Trapped`
- unknown/private Info keys

H9 does not automatically modify `ModDate`. An edit must not smuggle unrelated metadata changes into the transaction.

### Explicitly outside H9

H9 does not support:

- page-content text replacement;
- font rewriting, glyph remapping or CMap mutation;
- image replacement;
- annotation mutation;
- link target mutation;
- AcroForm value mutation;
- page insertion/deletion/reordering;
- outline/bookmark mutation;
- attachment mutation;
- XMP metadata mutation;
- encryption/decryption;
- digital-signature preservation or resigning;
- xref-stream or hybrid-reference output;
- linearization preservation;
- object-stream mutation;
- arbitrary indirect-object replacement;
- full-PDF serialization.

No API equivalent to `replace_pdf_object`, `write_pdf_object`, `replace_stream` or arbitrary opaque byte replacement may be introduced.

## Supported native PDF boundary

A PDF is H9-writable only when all of the following are true.

### Header and terminal structure

- The file begins with a valid `%PDF-1.x` or `%PDF-2.0` header in the accepted bounded header window.
- The final active revision ends in a valid `startxref` and `%%EOF` structure.
- The active `startxref` resolves to a classic `xref` table.
- Every `/Prev` revision followed by H9 also resolves to a classic `xref` table.
- Trailing bytes after the final `%%EOF` are limited to accepted PDF whitespace.

### Cross-reference model

- Classic fixed-width in-use/free entries are parsed with explicit line-ending handling.
- Multiple subsections are allowed.
- Duplicate object entries inside one xref section fail closed.
- Overlapping subsections inside one xref section fail closed.
- Out-of-range object offsets fail closed.
- `/Prev` cycles fail closed.
- The newest xref entry for an object number is authoritative across the incremental chain.
- A newest free entry makes the object unavailable even if an older in-use revision exists.
- The active effective `/Size` must be consistent with the object-number space H9 observes.

### Unsupported xref families

H9 fails closed when it encounters:

- an xref stream instead of a classic xref table;
- `/XRefStm` hybrid-reference metadata;
- object references that require type-2 xref-stream entries;
- malformed mixed xref representations.

These may become readable/writable in a later PDF tranche only with dedicated tests and verification.

### Encryption

Any effective trailer `/Encrypt` entry makes the PDF H9 read-only for mutation. H9 does not attempt password handling or encryption-preserving incremental output.

### Linearization

A PDF whose leading object advertises `/Linearized` is read-only in H9. Incremental append can invalidate linearization hints even when general readers still open the file; H9 must not silently downgrade this property.

### Digital signatures

H9 conservatively rejects mutation when signature evidence is present. The guard is intentionally fail-closed and may reject some unusual false positives rather than invalidate a signed document.

At minimum, write eligibility must reject a source containing authoritative or lexical signature evidence such as:

- `/FT /Sig`
- `/Type /Sig`
- `/ByteRange`
- catalog `/Perms` / DocMDP evidence

H9 does not claim to preserve signature validity after modification.

### XMP dual-authority metadata

If the effective catalog contains `/Metadata`, H9 metadata is inspectable but Info mutation is read-only with a stable reason code. H9 does not create an inconsistent state where Info says one value while an XMP metadata stream says another.

A later tranche may add coordinated Info + XMP mutation, but that must be a separate verified contract.

## Native parser architecture

Production H9 code uses a purpose-built bounded parser for the native structures required by the mutation contract. It is not a general PDF rendering engine.

Suggested module split:

- `formats/pdf/limits.py`
- `formats/pdf/model.py`
- `formats/pdf/lexer.py`
- `formats/pdf/xref.py`
- `formats/pdf/objects.py`
- `formats/pdf/parser.py`
- `formats/pdf/reader.py`
- `formats/pdf/routing.py`
- `formats/pdf/writer.py`
- `formats/pdf/verification.py`
- `formats/pdf/writer_adapter.py`
- `formats/pdf/__init__.py`

The exact file split may be reduced if implementation stays clearer with fewer modules, but parsing, IR construction, routing, writing and verification must remain conceptually separable.

## Parser limits

H9 introduces deterministic fail-closed limits. Default values are frozen for the tranche:

- `max_file_bytes = 512 MiB`
- `max_incremental_revisions = 64`
- `max_xref_subsections_per_revision = 65,536`
- `max_xref_entries_total = 1,000,000`
- `max_object_number = 10,000,000`
- `max_dictionary_bytes = 4 MiB`
- `max_pdf_string_bytes = 1 MiB`
- `max_lexer_nesting_depth = 64`
- `max_startxref_search_bytes = 1 MiB`

Exceeding a limit fails closed before mutation and reports a stable machine-readable reason.

## Lexical model

H9 needs exact raw ownership, not only decoded Python values.

The bounded lexer recognizes enough PDF syntax to parse trailer, catalog and Info dictionaries safely:

- whitespace and comments;
- names;
- integers;
- indirect references (`obj gen R`);
- literal strings with balanced parentheses and PDF escape handling;
- hex strings;
- arrays;
- dictionaries;
- booleans and null;
- raw value spans.

The lexer must preserve byte spans for top-level dictionary keys and values.

H9 does not decode arbitrary streams. If the catalog or Info authority needed for H9 resolves to a stream object or requires stream decoding, mutation is read-only/fail-closed.

## Xref-chain authority

The parser starts from the final `startxref` and walks `/Prev` backwards.

For each revision it records:

- xref byte offset;
- ordered subsections;
- object-number/generation/status/offset entries;
- raw trailer dictionary;
- parsed trailer top-level entries;
- `/Prev` reference when present.

The chain is bounded and cycle-checked.

Effective object lookup is newest-first across revisions. Effective trailer keys are also resolved newest-first, with older revisions supplying only keys omitted by newer revisions. `/Prev` itself is revision linkage, not an inherited semantic trailer key.

The parser must retain raw trailer value bytes for fields copied into a new incremental trailer.

## Indirect-object authority

For an in-use classic-xref object, H9 validates that the xref offset resolves to the expected object header:

`<object-number> <generation> obj`

The object number and generation must exactly match the xref entry.

For the H9 catalog and Info objects:

- the object must be uncompressed;
- its top-level value must be one dictionary;
- the dictionary must terminate before the matching `endobj`;
- unexpected `stream` content makes that authority unsupported for H9 mutation;
- malformed token nesting fails closed.

The parser records the complete raw dictionary bytes plus top-level key/value spans.

## PDF string semantics

Existing Info text values may be literal strings or hex strings.

The reader decodes supported strings according to the bounded PDF string rules needed by H9. If an existing writable field cannot be decoded deterministically, that field is read-only rather than guessed.

New or replacement H9 text is serialized deterministically as a UTF-16BE PDF hex string with BOM:

`<FEFF...>`

This avoids dependence on incomplete producer-specific PDFDocEncoding choices for newly written Unicode text.

Embedded NUL and invalid Unicode scalar input are rejected.

## DocumentIR mapping

A writable H9 PDF maps to one document canvas:

- canvas `kind="document"`;
- a read-only structural root node with semantic role `pdf-document`;
- one `pdf-info` metadata node, present even when the source currently has no `/Info` dictionary.

The `pdf-info` node payload contains the decoded supported Info fields that are present.

The node metadata records at minimum:

- `pdf.source_sha256`
- `pdf.source_size`
- `pdf.startxref`
- `pdf.revision_count`
- `pdf.info_object_number` when present
- `pdf.info_generation` when present
- `pdf.info_raw_digest` when present
- `pdf.info_present`
- `pdf.xref_kind = "classic"`
- `pdf.xmp_present`
- `pdf.encrypted`
- `pdf.signed_evidence`
- `pdf.linearized`
- `pdf.identity_markdown = False`

Existing Info fields additionally retain raw token evidence in native metadata owned by the `pdf-info` node.

The native locator for the `pdf-info` node binds the active startxref, effective trailer authority and Info object identity (or explicit absence when creating a new Info object).

## Capability contract

The `pdf-info` node advertises `update_pdf_info` as writable only when the complete H9 native boundary is satisfied.

Stable read-only reasons include at minimum:

- `pdf.xref.unsupported_stream`
- `pdf.xref.hybrid_reference`
- `pdf.trailer.encrypted`
- `pdf.signature.present`
- `pdf.linearized.unsupported`
- `pdf.metadata.xmp_dual_authority`
- `pdf.info.unsupported_object`
- `pdf.info.ambiguous_string_encoding`
- `pdf.source.malformed`
- `pdf.limit.exceeded`

Absent or unknown capability remains read-only under the common capability kernel.

## Typed edit contract

Operation:

`update_pdf_info`

Target:

The document's `pdf-info` node.

Payload shape:

```json
{
  "updates": [
    {
      "key": "Title",
      "old_value": "Original title",
      "value": "New title"
    },
    {
      "key": "Author",
      "old_value": null,
      "value": "Ada"
    }
  ]
}
```

Rules:

- updates must be non-empty;
- keys must be from the six writable H9 fields;
- updates are canonicalized/sorted by key;
- duplicate keys are rejected;
- `old_value` must exactly match the fresh native value, with `null` meaning the field must be absent;
- `value` must be a string and is never interpreted as deletion;
- exact no-op field updates are rejected;
- generic `replace_text` must not target PDF metadata;
- structural or arbitrary-object edit types are rejected.

The outer `EditOperation` still uses the common semantic digest, native-locator digest and expected-precondition discipline.

## Fresh routing and preflight

`patch_pdf` must not trust the caller's stale `DocumentIR` as native authority.

Before producing any candidate bytes it must:

1. read the complete source stream;
2. verify source SHA-256 and size against the document source descriptor;
3. parse the source again with H9 limits;
4. re-resolve the active xref/trailer chain;
5. re-resolve catalog/XMP/encryption/signature/linearization eligibility;
6. re-resolve the effective Info object or its absence;
7. verify the caller target node exists and advertises the operation;
8. verify semantic/native locator preconditions;
9. verify every `old_value` against fresh native metadata;
10. reject duplicate/conflicting/no-op updates;
11. only then construct an internal candidate.

Any failure leaves caller output empty.

## Incremental-update writer

H9 mutation output is append-only.

For every non-zero edit transaction:

`candidate[:len(source)] == source`

must be true exactly.

### Existing Info object

When `/Info` points to a supported indirect dictionary:

- reuse the same object number and generation;
- start from the exact raw dictionary bytes;
- replace only requested existing value-token spans;
- insert newly requested standard keys immediately before the dictionary's closing `>>` using deterministic H9 formatting;
- preserve every unrequested key/value raw token exactly;
- append the replacement indirect object as a new revision object body.

The old Info object bytes in the source prefix are never modified.

### No existing Info object

When the effective trailer has no `/Info` and the rest of the H9 boundary is writable:

- allocate object number equal to the effective `/Size` only after proving that number is not already effective/in-use;
- use generation `0`;
- write a deterministic Info dictionary containing only the requested writable fields in sorted key order;
- increase `/Size` accordingly.

### New xref section

The incremental revision writes classic xref entries only for objects authored by H9. It may include object 0's conventional free entry plus the updated/new Info entry as separate subsections.

Each in-use entry contains the exact absolute byte offset of the appended object and the preserved/new generation number.

### New trailer

The new trailer:

- preserves the effective `/Root` raw reference exactly;
- preserves effective `/ID` raw value exactly when present;
- preserves other safe effective trailer keys as raw values unless H9 explicitly owns them;
- sets `/Info` to the effective updated/new Info indirect reference;
- sets `/Size` to the validated effective object-space size;
- sets `/Prev` to the source's former active xref offset;
- never emits `/Encrypt` or `/XRefStm` because those sources are not writable in H9.

Unknown trailer entries are carried forward only when their raw value was parsed safely and they do not conflict with H9-owned trailer keys.

### Final markers

The writer appends:

- the new xref section;
- the new trailer;
- `startxref` pointing to the new xref byte offset;
- `%%EOF`.

A single line separator may be inserted between the exact source prefix and the first appended object only when required to create a valid token boundary. That separator is part of the appended revision, never a mutation of source bytes.

## Zero-edit behavior

`patch_pdf(..., edits=())` returns the exact source bytes with fidelity tier `exact-preserve`.

It must not append an empty incremental revision.

## Candidate verification

No caller output is written until a complete candidate passes H9 verification.

The verifier must:

1. confirm the original source is an exact byte prefix of the candidate;
2. parse the candidate from its final `startxref` under the same H9 limits;
3. confirm the new active xref is classic and `/Prev` points to the original active xref offset;
4. confirm effective `/Root` is unchanged;
5. confirm effective `/ID` raw value is unchanged when present;
6. confirm the effective `/Info` reference is the expected existing/new object;
7. confirm every requested field equals the requested semantic value;
8. confirm every unrequested pre-existing Info key/value retains its prior semantic value and exact raw value token;
9. confirm unsupported trailer state did not appear;
10. confirm the complete candidate remains H9-parseable.

Independent tests use `pdfminer.six`/existing PDF dependencies as a differential oracle where practical, including reopening the candidate and checking that ordinary page text extraction is unchanged by metadata-only mutation.

The production writer does not depend on a third-party whole-file serializer.

## Fidelity reporting

### Zero edits

Claimed tier:

`exact-preserve`

Evidence includes:

- exact source byte identity.

### Metadata mutation

Claimed tier:

`high`

Required evidence includes:

- `pdf.source_prefix_exact`
- `pdf.incremental_revision`
- `pdf.classic_xref_chain`
- `pdf.root_reference_preserved`
- `pdf.document_id_preserved` when applicable
- `pdf.unrequested_info_raw_tokens_preserved`
- `pdf.requested_info_semantics`
- `pdf.candidate_reread`

H9 does not claim byte identity for the effective Info object because a new revision supersedes it. It does claim exact byte identity for the entire original file prefix.

## Markdown boundary

PDF H9 identity Markdown is inspection-only.

The metadata may be projected visibly, but every PDF-backed projection block must advertise no reversible Markdown edit capability. `import_identity_markdown` must never emit `update_pdf_info` from edited Markdown in H9.

Direct typed `update_pdf_info` is the only writable H9 path.

## One-way PDF protection

The existing one-way converter behavior is not part of the H9 writer and must remain unchanged.

Protected file:

`packages/markitdown/src/markitdown/converters/_pdf_converter.py`

Frozen blob:

`ffbcbd990cfc40a577404c453ebe47bf477c4929`

Dedicated regression tests must lock both the blob and representative current conversion behavior. H9 production code must not be imported into the one-way converter.

## Security and adversarial requirements

Dedicated tests must cover at least:

- malformed/missing final `startxref`;
- `startxref` outside file bounds;
- xref stream rejection;
- `/XRefStm` hybrid rejection;
- malformed xref subsection headers;
- duplicate/overlapping xref entries;
- xref offset resolving to the wrong object number/generation;
- newest free entry overriding older in-use object;
- `/Prev` cycles;
- revision-count limit;
- xref-entry-count limit;
- dictionary/string/nesting limits;
- encrypted trailer rejection;
- linearized source rejection;
- signature evidence rejection;
- XMP catalog metadata dual-authority rejection;
- malformed/stream-backed Info authority rejection;
- ambiguous/unsupported existing Info string encoding;
- stale source SHA/size;
- stale Info object identity/digest;
- stale per-field `old_value`;
- duplicate/conflicting field updates;
- unsupported metadata keys;
- no-op field update rejection;
- transaction rollback with caller output remaining empty;
- candidate verifier rejection before caller output;
- source-prefix exactness after successful mutation.

## Fixtures

H9 tests use synthetic minimal PDFs generated by a deterministic fixture builder rather than hand-maintained opaque binary blobs wherever possible.

The fixture builder must be able to produce:

- classic single-revision PDFs;
- PDFs with/without Info;
- multiple classic incremental revisions;
- free/reused entries;
- configurable trailer keys;
- XMP catalog marker cases;
- encrypted-marker cases;
- signature-marker cases;
- linearized-marker cases;
- malformed xref/startxref cases.

Fixtures must calculate real byte offsets rather than embedding fake offsets that bypass the parser contract.

## Public API

The final H9 facade should expose:

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

`PdfPatchWriter` follows the existing `DocumentWriter` adapter pattern, accepts source format `pdf` and target format `pdf`/`.pdf`, requires `source_stream=` and `edits=`, accepts optional native limits, rejects unrelated kwargs and delegates to `patch_pdf`.

## Implementation sequence

The implementation must use strict RED -> GREEN progression.

### Task 1 — deterministic PDF fixtures and xref/parser RED

Create synthetic classic-xref fixtures and parser tests first. RED must fail because the H9 PDF native package does not exist, not because fixtures are malformed.

### Task 2 — bounded lexer/xref/object authority

Implement only enough native syntax to satisfy trailer/catalog/Info authority. Run focused tests plus exact branch CI.

### Task 3 — `DocumentIR` reader and capability boundary

Add `pdf-document` / `pdf-info` mapping, source/native evidence, read-only diagnostics and inspection-only identity Markdown metadata.

### Task 4 — fresh routing and transactional incremental writer

Add `update_pdf_info` preflight, source authority checks, field old-value checks, append-only Info object revision and classic xref/trailer append.

### Task 5 — candidate verifier and rollback proof

Re-read complete candidates, verify source-prefix identity, effective trailer invariants, requested semantics and untouched Info raw evidence before destination write.

### Task 6 — public facade, writer adapter, one-way regression and differential oracle

Expose stable imports, add `PdfPatchWriter`, lock `_pdf_converter.py`, keep Markdown inspection-only and use `pdfminer.six` only as an independent test oracle where practical.

### Task 7 — adversarial hardening, docs, scope audit and exact completion gate

Add only missing adversarial tests after auditing the frozen checklist. Update `TWOWAYS.md`, verify the H8 -> H9 diff is bounded, and run the complete exact-head gate.

## Completion gate

H9 is complete only when one exact final branch SHA has all of the following fresh and successful:

- pre-commit;
- package tests Python 3.10;
- package tests Python 3.11;
- package tests Python 3.12;
- package tests Python 3.13;
- OCR tests Python 3.10;
- OCR tests Python 3.11;
- OCR tests Python 3.12;
- OCR tests Python 3.13.

That is the same exact 9/9 authority used by H6-H8.

After the exact completion SHA is established, no source/test/doc commit may be added to the H9 branch without invalidating the proof. PR metadata may be updated without changing the branch SHA.

H9 must not be merged automatically.

## H9 -> later PDF tranches

The next PDF tranche may build annotations/forms/links only from the exact H9 completion SHA and must reuse the xref/object/incremental-update authority rather than introducing a serializer shortcut.

Selected text/image mutation comes later and requires dedicated proof for content-stream token ownership, resource inheritance, font encoding/CMap/glyph representability, graphics-state boundaries and object/resource sharing. If that proof is not available, visible extracted text remains derived/read-only rather than being presented as safely writable native PDF content.
