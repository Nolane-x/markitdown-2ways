# MarkItDown 2Ways Phase D — DOCX Native Round-Trip Design

## 1. Status and scope

Phase D extends the existing MarkItDown 2Ways Core IR, Markdown identity bridge, and generic OOXML preservation substrate with a high-fidelity DOCX reader and minimal WordprocessingML patch writer.

This phase is intentionally not a general-purpose Word editor. Its first production boundary is:

- DOCX body paragraphs and runs: readable and patchable text.
- Hyperlink text: readable and patchable while preserving the existing relationship target and wrapper.
- Headers and footers: readable and patchable text.
- Pictures: readable with resource identity and alt text; alt text patchable without replacing image bytes.
- Tables: readable as semantic `TablePayload`, read-only in v1.
- Fields, content controls, comments, footnotes/endnotes, drawings beyond pictures, equations, tracked revisions, numbering definitions, styles, section properties, and other unknown native structures: preserved by package authority and not mutated unless explicitly supported.

Unsupported edits fail closed. Patch mode never silently rebuilds the package.

## 2. Architectural choice

Phase D uses the approved hybrid preservation architecture:

1. The original DOCX ZIP/OPC package is the preservation authority.
2. `python-docx` may be used as a semantic assist and as a reopen/readback oracle, but never as the patch serializer.
3. `lxml` operates on only the XML parts that must change.
4. The shared `twoways.ooxml` package performs safe package snapshotting, member limits, duplicate/traversal checks, and sparse archive rewriting.
5. `DocumentIR` remains the canonical semantic representation.
6. Identity Markdown remains the AI/human edit projection.
7. Typed `EditOperation` objects remain the only accepted mutation requests.
8. Verification compares package members, semantic readback, and unrelated native subtrees before a fidelity tier can be claimed.

The writer always starts from the original source bytes and replaces only explicitly touched XML members.

## 3. Non-goals

Phase D v1 does not:

- recreate a DOCX from arbitrary Markdown in patch mode;
- add/delete paragraphs or table rows/cells;
- change hyperlink URLs;
- change list numbering definitions;
- change paragraph styles, section layout, margins, columns, headers/footers assignments, page breaks, or theme data;
- edit field codes or calculated results;
- accept/reject tracked changes;
- mutate comments, footnotes, endnotes, bookmarks, equations, SmartArt, charts, OLE objects, embedded files, or custom XML;
- replace image blobs or relationship targets;
- serialize the source through `python-docx.save()` as part of patch mode.

These structures may be read as semantic or opaque native evidence where useful, but remain preserved and read-only.

## 4. Package and part model

A DOCX source is an OPC package. Phase D recognizes the following relevant part classes:

- `/word/document.xml` — main document body.
- `/word/headerN.xml` — header stories.
- `/word/footerN.xml` — footer stories.
- `/word/_rels/document.xml.rels` and per-part `.rels` — relationship data, read-only in v1.
- `/word/media/*` — embedded image resources, read-only in v1.
- `/word/styles.xml`, `/word/numbering.xml`, `/word/settings.xml`, `/word/theme/*`, `/word/fontTable.xml`, `/word/webSettings.xml` — preserved package members, not mutation targets in v1.

Other parts are preserved unchanged by the sparse package writer.

The reader discovers header/footer part URIs from relationships rather than guessing sequential names.

## 5. IR mapping

### 5.1 Document source

`DocumentIR.source` is populated as:

- `format="docx"`
- `mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document"`
- `sha256=<source package sha256>`
- `size_bytes=<source byte length>`

The source SHA is an authority lock and precondition. It is not part of logical node IDs.

### 5.2 Canvases

DOCX is flow-oriented rather than slide-oriented. Phase D maps Word stories to canvases:

- one `Canvas(kind="document-body")` for `/word/document.xml`;
- one `Canvas(kind="header")` for each header part;
- one `Canvas(kind="footer")` for each footer part.

Canvas `native_locator.part_uri` binds the canvas to its exact OOXML part. Header/footer canvas metadata includes relationship id and header/footer role when available.

### 5.3 Paragraph nodes

Each supported Word paragraph becomes one `Node(kind="text")` with a `TextPayload` containing one IR `Paragraph` and its ordered `TextRun` values.

Paragraph semantic roles may include:

- `paragraph`
- `heading`
- `header`
- `footer`

Heading role/name may be inferred from resolved paragraph style metadata, but the patcher does not rewrite styles in v1.

Paragraph metadata can preserve inert evidence such as:

- paragraph style id;
- numbering id/level;
- section/story role;
- whether the paragraph contains fields, bookmarks, revisions, or unsupported inline constructs;
- hyperlink ranges and relationship ids.

If unsupported inline constructs make text mutation unsafe, the node is emitted readable but with edit capability `read-only` and a diagnostic explaining why.

### 5.4 Run mapping

Each visible `w:t` contribution maps to an IR `TextRun`. A run locator records enough deterministic structural evidence to find the native text node without relying on textual content.

Run style extraction is direct-format evidence only in v1, including where available:

- bold/italic;
- underline;
- font name;
- size;
- color;
- superscript/subscript;
- language.

The patch writer must not reconstruct run properties. Existing `w:rPr`, hyperlink wrappers, bookmarks, proofing markers, and other sibling XML remain untouched.

### 5.5 Hyperlinks

Hyperlink text remains part of the enclosing paragraph text payload. The reader records, as inert metadata, the hyperlink wrapper range and relationship id or anchor.

Text replacement is allowed only when the character-level diff can be assigned without crossing native hyperlink-context boundaries. Each existing `w:t` belongs either to ordinary paragraph context or to one specific hyperlink context (`r:id` or anchor). The patcher may modify text within one or more contexts independently, but it must not move characters across those boundaries or reconstruct a hyperlink wrapper. The URL/anchor itself is never changed in v1.

A requested edit that requires moving text into or out of a hyperlink, creating/deleting/splitting/joining a hyperlink wrapper, or retargeting a relationship is rejected as unsupported.

### 5.6 Tables

A Word table becomes `Node(kind="table")` with `TablePayload` containing row/column dimensions and cell semantic text.

Table XML is read-only in Phase D v1. Paragraphs inside cells are not separately exposed as patchable nodes in v1, preventing ambiguous edits around merged cells, grid spans, nested tables, and vertical merges.

### 5.7 Pictures

Supported inline/anchored pictures become `Node(kind="image")` with:

- resource id derived deterministically from the embedded media member digest;
- relationship id to the media part;
- alt text from `wp:docPr@descr` when present;
- native locator bound to exact part and `wp:docPr@id` plus structural path.

`set_alt_text` changes only `wp:docPr@descr`. It never changes `a:blip`, media bytes, crop/effects, dimensions, relationship ids, or drawing position.

## 6. Native identity and stable IDs

DOCX has weaker universal object identity than PPTX shapes, so Phase D uses layered locators.

### 6.1 Paragraph identity

Preferred identity evidence:

1. `part_uri + w14:paraId` when `w14:paraId` exists and is unique within the part;
2. otherwise `part_uri + canonical structural paragraph path`.

The structural path is safe because v1 does not support paragraph insertion, deletion, or reorder.

Paragraph node IDs are deterministic hashes of:

`part_uri \0 paragraph-identity \0 node-kind`

where `node-kind` is the constant semantic kind (for example `text`), **not the paragraph content**. The source package SHA and semantic text are both excluded, so editing text does not change the logical node id.

### 6.2 Picture identity

Picture identity uses:

`part_uri + wp:docPr@id + structural drawing path`

`docPr@name` is supporting evidence only and is not sufficient by itself for mutation.

### 6.3 Strict resolution

Patch mode requires the designated `part_uri` and a unique native identity. Name-only or text-content-only lookup is rejected.

If preferred and fallback evidence disagree, resolution fails with `AmbiguousNativeLocatorError`; the writer never picks one candidate heuristically.

## 7. Text mutation algorithm

### 7.1 Preconditions

Before any mutation the writer verifies:

1. the supplied source package SHA matches `DocumentIR.source.sha256`;
2. the edit target exists in the document;
3. `expected_semantic_digest`, if present, matches the current IR node;
4. `expected_native_locator_digest`, if present, matches the current locator;
5. `expected_old_value`, if present, matches current semantic text;
6. the native paragraph resolves uniquely in the designated part;
7. the paragraph native subtree still matches the structural assumptions recorded at read time.

A failed check raises a typed fail-closed error before output bytes are written.

### 7.2 Supported text replacement

`replace_text` operates on the semantic text of one paragraph/story node.

The patcher obtains the ordered existing visible `w:t` nodes and groups them by native text context: ordinary paragraph text or one exact hyperlink wrapper. It computes a deterministic character-level diff between old and new semantic text, proves that every changed span can be mapped without crossing context boundaries, and redistributes each accepted changed span only over the existing `w:t` elements of its original context without deleting/recreating their enclosing `w:r` elements.

For ordinary replacement/insertion/deletion within a paragraph:

- existing run order remains unchanged;
- existing `w:rPr` remains byte-equivalent semantically and structurally;
- hyperlink wrapper structure and relationship ids remain unchanged;
- no new relationship is created;
- no paragraph is created/deleted;
- XML whitespace preservation (`xml:space="preserve"`) is set or removed only when required by WordprocessingML text semantics.

### 7.3 Unsafe text structures

The patch is rejected when the edit would require changing unsupported native structure, including:

- a paragraph whose visible text depends on field-code/result boundaries that cannot be preserved safely;
- tracked revision wrappers where mutation would alter revision semantics;
- unsupported content control boundaries;
- text represented by non-`w:t` constructs that cannot preserve equivalent meaning;
- a requested edit requiring a new paragraph, line-break element, tab element, hyperlink wrapper, or relationship.

Readable nodes may therefore be explicitly read-only.

## 8. Header and footer mutation

Headers and footers reuse the exact paragraph reader/locator/text patcher used for `/word/document.xml`, differing only by `part_uri` and story metadata.

A header edit must touch only its `word/headerN.xml` part unless an explicitly supported future operation requires more. The same applies to footer parts.

Section property references in `word/document.xml` remain untouched.

## 9. Picture alt-text mutation

For `set_alt_text`:

1. resolve the exact drawing in the designated XML part;
2. verify `wp:docPr@id` and locator evidence;
3. set only `descr` to the new value;
4. leave `id`, `name`, `title`, extent, transforms, `a:blip`, relationship id, and media part untouched.

If one locator matches multiple `wp:docPr` nodes, patching fails closed.

## 10. Package preservation

Patch mode uses the shared sparse OOXML writer.

### No-op invariant

If there are no edits, output bytes must equal source bytes exactly.

### Edited-package invariant

For each output with edits:

- every ZIP member not listed as touched must have identical uncompressed bytes to the source;
- relationship parts must remain byte-identical in Phase D v1;
- media members must remain byte-identical;
- styles/numbering/settings/theme members must remain byte-identical;
- only XML parts containing successfully applied targets may be replaced.

ZIP container metadata may differ for touched members as permitted by the shared writer, but untouched member payloads must not.

## 11. Native-subtree verification

A touched XML part can contain unrelated paragraphs, tables, drawings, bookmarks, fields, and other native structures. Package-member equality alone is therefore insufficient.

Post-write verification snapshots canonical native subtrees before mutation. After writing, every unrelated supported native object in each touched part is re-resolved and compared.

Verification excludes:

- the exact target paragraph/drawing subtree;
- ancestor containers whose serialized bytes necessarily change solely because the target descendant changed.

It still verifies siblings and unrelated descendants.

Any unexpected unrelated-native change raises `RoundTripVerificationError` and fidelity fails.

## 12. Semantic readback verification

After patching, the output is reopened and reread with the Phase D reader.

For every successfully edited operation:

- logical node id must remain stable;
- the target semantic value must equal the requested new value;
- required resource/relationship identity must still resolve;
- unrelated semantic nodes must retain their previous semantic digests.

For picture alt text, the output node must preserve the same resource id and relationship evidence while exposing the new alt text.

## 13. Fidelity evidence

A successful compatible patch produces a `WriterResult(format="docx", mode="patch")` and a `FidelityReport` containing evidence codes such as:

- `docx.source_digest`
- `docx.package.untouched_members`
- `docx.relationships.unchanged`
- `docx.native.unrelated_subtrees`
- `docx.target.semantic_readback`
- `docx.target.node_identity`
- `docx.picture.resource_identity`

No-op writes may claim `exact-preserve` only when output bytes equal input bytes.

Edited writes may claim `high` only when every required preservation/readback check passes. Failure of a required check prevents a high-fidelity claim.

## 14. Public API

Phase D adds an optional package:

```python
from markitdown.twoways.formats.docx import (
    DocxIRReader,
    DocxPatchOptions,
    DocxPatchWriter,
    DocxReadOptions,
    patch_docx,
    read_docx_ir,
)
```

Proposed signatures:

```python
def read_docx_ir(
    file_stream: BinaryIO,
    stream_info: Any | None = None,
    *,
    options: DocxReadOptions | None = None,
) -> DocumentIR: ...


def patch_docx(
    source: bytes | BinaryIO,
    document: DocumentIR,
    edits: Sequence[EditOperation],
    output: BinaryIO | None = None,
    *,
    options: DocxPatchOptions | None = None,
) -> tuple[bytes, WriterResult] | WriterResult: ...
```

Importing `markitdown.twoways` must not eagerly import `docx`, `mammoth`, or `lxml`.

## 15. Dependency policy

The existing MarkItDown `[docx]` optional feature already uses `mammoth` and `lxml`. Phase D adds `python-docx` to this optional group so fixtures/readback and semantic assistance use an explicit direct dependency rather than an undeclared transitive dependency.

Core `markitdown.twoways` remains free of format-specific imports.

No Node.js, LibreOffice, cloud service, or network access is required.

## 16. Proposed module boundaries

```text
markitdown/twoways/formats/docx/
  __init__.py       lazy public exports
  model.py          DocxReadOptions / DocxPatchOptions
  locators.py       paragraph/drawing native identity and strict resolution
  text.py           WordprocessingML text extraction and run-preserving mutation
  resources.py      relationship/media/resource mapping
  stories.py        body/header/footer story discovery
  blocks.py         paragraph/table/picture -> IR builders
  reader.py         DOCX -> DocumentIR orchestration
  patch.py          edit precondition helpers and narrow native mutations
  verify.py         package/native/semantic readback checks
  writer.py         sparse-package patch orchestration
```

Shared ZIP/XML safety remains in `markitdown/twoways/ooxml/`; DOCX code must not duplicate package-defense logic.

## 17. Error model

Phase D reuses existing typed 2Ways errors wherever possible:

- `MissingOptionalDependencyError`
- `OOXMLPackageError`
- `AmbiguousNativeLocatorError`
- `PatchPreconditionError`
- `UnsupportedEditError`
- `RoundTripVerificationError`

Errors include stable `details["reason"]` values for testability and future CLI reporting.

Representative reason codes:

- `source_digest_mismatch`
- `part_mismatch`
- `paragraph_not_found`
- `ambiguous_paragraph`
- `drawing_not_found`
- `unsupported_inline_structure`
- `hyperlink_structure_change`
- `paragraph_structure_change`
- `unexpected_native_change`
- `semantic_readback_mismatch`

## 18. Security requirements

Phase D inherits shared OOXML package limits and adds Word-specific checks:

- no ZIP traversal;
- no duplicate ZIP member names;
- reject encrypted packages outside supported scope;
- per-member and total uncompressed-size limits;
- XML parsing with DTD/entity/network resolution disabled;
- external hyperlink/image relationships are inert metadata only and are never fetched;
- no URI dereference during reading or verification;
- no macro execution; `.docm` is outside the Phase D v1 accepted source formats;
- no embedded OLE/package execution.

## 19. Test strategy

Tests use real in-memory DOCX files generated with `python-docx` plus targeted raw-OOXML fixture augmentation when python-docx cannot create the required structure.

Required TDD coverage includes:

1. body paragraph/run extraction and deterministic node ids;
2. style/run evidence extraction;
3. hyperlink text extraction while preserving relationship metadata;
4. header/footer discovery and patching;
5. table semantic read-only extraction;
6. image resource mapping and alt text;
7. strict paragraph/drawing locator resolution and ambiguity rejection;
8. stale source/semantic/native/old-value preconditions;
9. run-preserving paragraph text mutation;
10. hyperlink-wrapper preservation under text edits;
11. unsupported paragraph-structure mutations fail closed;
12. picture alt-text-only mutation;
13. no-op output byte identity;
14. untouched ZIP member content identity;
15. unrelated-native subtree verification inside touched parts;
16. semantic reread and stable node identity;
17. Identity Markdown -> typed edit -> DOCX end-to-end path;
18. root import remains lightweight without optional DOCX dependencies;
19. package/XML adversarial security regression inherited from shared OOXML tests.

## 20. Vertical-slice acceptance scenario

The first vertical slice is accepted only when a real DOCX containing:

- a body paragraph with at least two differently formatted runs;
- an external hyperlink;
- a header and footer;
- a table;
- a picture with alt text;

can complete these flows:

### Body text

`DOCX -> DocumentIR -> Identity Markdown -> edit one phrase -> typed replace_text -> patch_docx -> DOCX`

Only `/word/document.xml` may change. Existing run properties and hyperlink relationship bytes must remain unchanged. Reopen/readback must expose the new text and stable node id.

### Header/footer text

Editing a header touches only the exact header XML part. Editing a footer touches only the exact footer XML part.

### Picture alt text

Changing picture alt text touches only the containing XML part and keeps the media member and relationship part identical.

### No-op

No edits produce byte-identical source/output archives.

## 21. Phase D v1 completion criteria

Phase D v1 is locally complete when all of the following are true:

1. body/header/footer paragraph reading works on real DOCX fixtures;
2. tables and pictures are represented semantically;
3. stable native paragraph/drawing locators are deterministic;
4. compatible text replacement preserves existing run/hyperlink wrappers;
5. picture alt-text-only patch works;
6. no-op output is byte-identical;
7. untouched package-member payloads remain identical after edits;
8. unrelated native subtrees in touched XML parts are verified;
9. post-write semantic reread and node-id stability pass;
10. Identity Markdown end-to-end patch succeeds;
11. unsupported mutations fail closed;
12. root package import remains optional-dependency-light;
13. Phase A+B+C+D isolated tests pass under normal execution and multiple `PYTHONHASHSEED` values;
14. Python 3.10 grammar and compile checks pass.

Repository-wide upstream compatibility and the multi-version GitHub Actions matrix remain separate integration gates and must not be claimed without actual evidence.

## 22. Future extensions after v1

Future DOCX phases may add, each behind its own design/verification boundary:

- table-cell editing;
- list/numbering-aware edits;
- hyperlink target mutation with relationship patching;
- footnotes/endnotes/comments;
- tracked-change-aware editing;
- content controls;
- image replacement;
- styles and section/layout mutation;
- full rebuild mode from semantic IR/Markdown.

None of these are implicit in Phase D v1.
