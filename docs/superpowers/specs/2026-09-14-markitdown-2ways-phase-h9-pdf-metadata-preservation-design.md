# MarkItDown 2Ways Phase H9 — PDF Metadata Preservation Design

## Status

Approved architectural direction for the first PDF-native tranche of v0.7. H9 is isolated on `phase-h9-pdf-metadata-preservation` and starts from exact-green H8 completion head `9a43768efde296330f8bbea542ffc5e926a2d735`.

H8 is immutable completion authority. H9 must not add commits to `phase-h8-recursive-zip-preservation` and must not weaken any H1-H8 safety contract.

## Goal

Add the first conservative native-safe PDF write path: source-preserving incremental updates for a narrow subset of the PDF Document Information dictionary.

H9 tranche one is intentionally limited to existing ordinary text metadata fields:

- `/Title`
- `/Author`
- `/Subject`
- `/Keywords`

The operation is `update_pdf_metadata` and is exposed only when the current PDF has one unambiguous writable Document Information authority and no conflicting metadata/signature/security condition.

H9 does **not** edit page content, text-showing operators, fonts, images, annotations, links, forms, outlines, page geometry, XMP, embedded files, encryption, signatures, structure trees, object streams, or arbitrary PDF objects.

## Why metadata first

PDF is a complex object graph with multiple metadata systems and multiple native revision mechanisms. A library being able to save a PDF is not enough to claim source-preserving writeback.

The first H9 tranche therefore establishes the PDF-native transaction model before any content mutation:

```text
source PDF bytes
    -> strict PDF authority read
    -> one writable Document Info owner
    -> typed metadata edit
    -> incremental candidate
    -> changed-object audit
    -> independent semantic re-read
    -> prefix/native preservation proof
    -> caller output
```

This gives later PDF tranches a tested authority/verifier foundation for annotations, forms and links without pretending text/image editing is already safe.

## Library choice

H9 uses `pypdf>=6.18.1,<7` for the production PDF object model and incremental writer.

Reasons:

- `PdfWriter(..., incremental=True)` writes the original document first and appends new/modified content rather than rebuilding the complete file;
- `list_objects_in_increment()` exposes the new/modified indirect objects that will be written, allowing H9 to fail closed if anything outside the authorized metadata object changes;
- strict parsing can be requested;
- the dependency is pure Python and compatible with the project Python 3.10–3.13 matrix.

`pdfminer.six`, already in the PDF optional dependency set, remains an independent semantic oracle for metadata verification where practical.

H9 does not use pikepdf/qpdf as the production writer because its ordinary save path consolidates incremental updates into a non-incremental rewrite. H9 also does not implement a new PDF/xref parser from scratch; duplicating a PDF parser would increase corruption risk without improving the tranche boundary.

## Dependency contract

Update the `pdf` optional dependency group and `all` group to include:

```text
pypdf>=6.18.1,<7
```

The one-way PDF converter remains independent in behavior. Its existing extraction path must not import H9 two-way code or change output semantics.

## PDF safety boundary

### Writable eligibility

A PDF is writable in H9 only when all of the following are true:

- source starts with a valid `%PDF-` header and strict parsing succeeds;
- source is not encrypted;
- source has a resolvable catalog/root;
- source has an existing Document Information dictionary reachable through trailer `/Info`;
- requested fields already exist as text-string metadata owners;
- the selected fields decode without ambiguity;
- no XMP metadata stream is present;
- no digital-signature field, signature dictionary, certification `/Perms`, DocMDP or equivalent signature authority is present;
- the source is not linearized;
- no parser repair/recovery is required;
- no requested change requires creating/deleting metadata keys or changing metadata value type;
- the complete requested edit set is internally consistent.

Everything else remains readable when possible but read-only with a stable reason code.

### Why reject XMP in tranche one

PDF may contain both Document Information and XMP metadata. Updating only one can create two conflicting metadata authorities. H9 therefore rejects native metadata writeback whenever XMP exists. A later dedicated tranche may update both authorities transactionally.

### Why reject signed/certified PDFs

Incremental writing can technically append revisions to signed PDFs, but signature validity and certification permissions are policy-sensitive. H9 does not claim signature-preserving metadata mutation. Any signature/certification evidence makes native writeback read-only.

### Why reject linearized PDFs

Appending a revision can make the original linearization hints stale or misleading. H9 preserves correctness by leaving linearized sources read-only until a dedicated linearization-aware policy exists.

## Evidence model

Add immutable evidence under `markitdown.twoways.formats.pdf`:

- `PdfNativeLimits`
- `PdfSourceSnapshot`
- `PdfInfoFieldEvidence`
- `ParsedPdfSource`
- `PdfParseError`

`PdfSourceSnapshot` records at minimum:

- source SHA-256;
- source byte size;
- PDF header/version;
- page count;
- trailer/root identity evidence;
- `/Info` indirect-object id/generation;
- current supported metadata values;
- whether XMP exists;
- whether encryption exists;
- whether signature/certification evidence exists;
- whether linearization exists;
- parser/authority diagnostics.

Each writable metadata field records:

- PDF key;
- decoded semantic value;
- raw object class/type evidence;
- owning `/Info` object id/generation;
- semantic digest;
- native locator digest.

## Resource limits

`PdfNativeLimits` is immutable and should start conservatively. Initial controls include at least:

- `max_source_bytes`;
- `max_pages`;
- `max_increment_bytes`;
- `max_metadata_value_chars`;
- `max_total_metadata_chars`.

Recommended initial defaults:

- source bytes: 512 MiB;
- pages: 20,000;
- incremental suffix: 4 MiB;
- one metadata value: 64 KiB characters;
- total supported metadata text: 256 KiB characters.

These limits are safety ceilings, not targets. Tests may justify lowering them; implementation must not silently raise them during H9.

## `DocumentIR` mapping

### Root

- `SourceDescriptor(format="pdf")` binds source SHA-256 and size.
- The primary canvas is `Canvas(kind="document")`.
- The root node semantic role is `pdf-document`.
- The root records read-only structural PDF evidence and capability decisions.

### Metadata field nodes

Create deterministic child nodes for supported existing metadata keys.

Each field node has:

- semantic role `pdf-metadata`;
- payload containing the decoded text value;
- metadata `pdf.info_key`;
- metadata `pdf.info_objgen`;
- native locator identifying the `/Info` object plus key;
- writable `update_pdf_metadata` capability only when the whole document passes the H9 writable gate;
- `pdf.identity_markdown = false`.

The field node is the caller-facing target, but H9 treats the complete `/Info` dictionary as the native transactional owner.

## Capability model

### Writable operation

H9 adds one operation:

```text
update_pdf_metadata
```

A metadata field may advertise it as writable only when the document passes every H9 eligibility rule and that key is an existing supported text owner.

### Stable reason codes

Initial reason-code namespace includes at least:

- `pdf.source.malformed`
- `pdf.source.too_large`
- `pdf.source.too_many_pages`
- `pdf.security.encrypted`
- `pdf.security.signature_present`
- `pdf.security.certification_present`
- `pdf.metadata.info_missing`
- `pdf.metadata.xmp_conflict`
- `pdf.metadata.unsupported_value_type`
- `pdf.metadata.key_missing`
- `pdf.metadata.value_too_large`
- `pdf.metadata.total_too_large`
- `pdf.structure.linearized`
- `pdf.structure.authority_ambiguous`
- `pdf.writer.unexpected_increment_object`
- `pdf.writer.increment_too_large`
- `pdf.structure.read_only`

Unknown/absent PDF capabilities default to read-only.

## Edit contract

`update_pdf_metadata` payload:

```json
{
  "field": "Title",
  "value": "Updated title"
}
```

Allowed public field names map exactly to:

- `Title` -> `/Title`
- `Author` -> `/Author`
- `Subject` -> `/Subject`
- `Keywords` -> `/Keywords`

Rules:

- target node must be the matching existing metadata field node;
- value must be a Python `str`;
- empty string is allowed and remains a text string; key deletion is not H9;
- duplicate logical targets are rejected;
- duplicate operation IDs are rejected;
- no-op values are rejected as edits; zero-operation transactions use the explicit zero-edit path;
- semantic/native locator/expected-old-value preconditions are validated;
- value and total metadata limits are checked before writer construction.

## Fresh routing and stale-source protection

For every write:

1. validate `DocumentIR`;
2. read exact source bytes;
3. require source SHA-256/size match;
4. strict-parse source again;
5. require fresh `/Info` object id/generation match recorded authority;
6. require writable eligibility still holds;
7. resolve every requested key against fresh `/Info`;
8. require the same value type and old semantic value/evidence;
9. validate all edit preconditions;
10. only then construct the incremental writer.

No cached parser object from the original read is authoritative for mutation.

## Incremental writer contract

H9 uses a fresh strict source parse and `PdfWriter(source, incremental=True)`.

After applying all requested metadata changes in memory and before writing:

- call `list_objects_in_increment()`;
- require that every modified existing indirect object is exactly the authorized `/Info` object;
- permit only writer-required new bookkeeping objects if empirical RED/GREEN evidence proves they are deterministic and necessary;
- reject any changed page, catalog, content, annotation, AcroForm, outline, metadata-stream or unrelated object;
- reject an increment whose predicted/actual suffix exceeds `max_increment_bytes`.

The complete candidate is written into an internal buffer. Caller output remains empty until final verification passes.

### Zero edits

With zero edit operations, H9 returns the original source bytes byte-for-byte and does not invoke the incremental writer.

### Mutated output

For a successful metadata mutation:

- the candidate must begin with the **exact original source bytes**;
- only an incremental suffix may be appended;
- existing original bytes are never rewritten;
- the suffix must remain within the configured bound;
- requested metadata values must re-read exactly;
- unrequested supported metadata values must remain semantically identical;
- page count and page-object authority must remain unchanged;
- XMP/signature/encryption/linearization state must not be introduced or removed;
- no unauthorized indirect object may be modified in the new increment.

H9 claims high source preservation for mutation, not whole-file byte identity.

## Verification

Final verification occurs before caller output.

### Native checks

Require:

- `candidate.startswith(source)`;
- candidate is longer than source for a non-empty edit set;
- suffix size within limit;
- strict pypdf re-read succeeds;
- source/candidate page count identical;
- root/catalog authority remains semantically equivalent;
- authorized `/Info` authority remains the only modified existing object;
- no unexpected object appears in the increment audit;
- encryption/XMP/signature/certification/linearization policy remains consistent;
- unrequested supported metadata fields retain old values.

### Semantic checks

Require every requested field to equal the requested Unicode value under a fresh pypdf read.

Where `pdfminer.six` can independently decode the Document Information dictionary, require it to agree on requested supported text metadata. Disagreement fails closed.

### Failure behavior

Any parse, preflight, changed-object audit, write, limit or verification failure leaves caller output empty.

## Markdown boundary

Identity Markdown for H9 is inspection-only.

PDF text extracted by the one-way converter, pdfminer or pdfplumber is not authoritative native text and must never become a route to page-content mutation.

Visible PDF metadata may be projected, but every H9-backed block has `editable_capabilities=()` in identity Markdown. Direct typed `update_pdf_metadata` is the only writable path.

## One-way PDF compatibility

Protect:

```text
packages/markitdown/src/markitdown/converters/_pdf_converter.py
```

H9 must add a regression lock for the one-way converter source blob and representative existing behavior. The one-way converter must not import `markitdown.twoways.formats.pdf` and must not change because of H9.

## Public API

Expose from `markitdown.twoways.formats.pdf`:

- `PdfIRReader`
- `PdfNativeLimits`
- `PdfParseError`
- `PdfPatchWriter`
- `parse_pdf_source`
- `read_pdf_ir`
- `patch_pdf`

`PdfPatchWriter` follows existing `DocumentWriter` adapter patterns and requires `source_stream=` plus `edits=`.

## Production module boundary

Expected production code is confined primarily to:

```text
packages/markitdown/src/markitdown/twoways/formats/pdf/
```

plus the minimal optional-dependency declaration and, only if dedicated RED evidence requires it, a narrowly scoped shared Markdown projection guard.

H1-H8 adapters, CLI behavior and one-way PDF conversion remain unchanged.

## Test strategy

H9 must be developed test-first and cover at least:

### Parser/reader

- deterministic metadata IR;
- supported field mapping;
- source SHA/size binding;
- malformed PDF read-only/fail-closed behavior;
- missing `/Info` read-only;
- XMP conflict read-only;
- encryption read-only;
- signature/certification read-only;
- linearized read-only;
- unsupported metadata value type read-only;
- source/page/value limits.

### Writer/routing

- one-field title update;
- multiple metadata fields in one transaction;
- zero-edit byte identity;
- stale source rejection;
- stale old value rejection;
- forged locator rejection;
- duplicate logical target rejection;
- duplicate operation-id rejection;
- unsupported key rejection;
- no-op edit rejection;
- caller output empty on inner/write/verification failure.

### Incremental preservation

- candidate exact source-prefix proof;
- only `/Info` existing object changed;
- suffix size bound;
- unrequested metadata preserved;
- page count preserved;
- page object/content semantics preserved;
- strict re-read succeeds;
- independent pdfminer metadata check agrees;
- unexpected modified object is rejected.

### Public/compatibility

- public imports;
- `PdfPatchWriter` adapter behavior;
- inspection-only identity Markdown;
- one-way `_pdf_converter.py` blob lock;
- representative one-way PDF conversion regression;
- optional dependency installation path.

### Full gate

Exact completion head must pass:

- pre-commit;
- package Python 3.10;
- package Python 3.11;
- package Python 3.12;
- package Python 3.13;
- OCR Python 3.10;
- OCR Python 3.11;
- OCR Python 3.12;
- OCR Python 3.13.

That is the same exact 9/9 completion gate as H6-H8.

## Explicit non-goals for H9

H9 does not support:

- XMP mutation;
- adding/removing metadata keys;
- creation of a new `/Info` dictionary;
- `/Creator`, `/Producer`, creation/modification dates;
- annotations;
- links;
- AcroForm values;
- signatures;
- page insert/delete/reorder;
- text replacement;
- image replacement;
- content stream mutation;
- font/resource mutation;
- outline/bookmark mutation;
- attachment mutation;
- encryption changes;
- PDF repair;
- linearization repair/rewrite;
- generic indirect-object replacement.

## Follow-on PDF tranches

After H9 exact completion, v0.7 should proceed in independent exact-head branches rather than widening H9:

1. annotations and URI/link destinations;
2. AcroForm values under appearance/signature constraints;
3. XMP + Document Information synchronized metadata;
4. selected text operations only after font encoding/content-stream/object-graph proof;
5. selected image/resource replacement only after XObject ownership proof.

Each tranche must preserve the rule that parsing or rendering a PDF does not imply native write capability.

## Completion rule

H9 is complete only when all of these are true on one frozen exact branch head:

- design and implementation plan are committed;
- dedicated RED evidence exists before production behavior;
- reader/capability/writer/verifier/public API are implemented;
- incremental changed-object audit is enforced;
- zero-edit byte identity is proven;
- non-empty mutation preserves exact original bytes as candidate prefix;
- one-way PDF converter remains unchanged;
- H8-to-H9 scope audit is clean;
- exact-head pre-commit + full package/OCR Python 3.10–3.13 matrix is 9/9 GREEN;
- PR metadata records the exact completion SHA;
- no source/test/docs commits are added after the frozen completion SHA.
