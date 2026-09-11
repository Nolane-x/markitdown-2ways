# MarkItDown 2Ways Full Format Parity Design

## Status

Approved architectural direction for the post-v0.2.0 program.

Baseline: `main@fa897976a92aea707ba12a9b2294fdce5f067615` (`2ways-v0.2.0`).

The goal is deliberately large in format coverage but deliberately narrow in product scope: MarkItDown 2Ways remains a document/file round-trip engine, not an application platform.

## Goal

Bring MarkItDown 2Ways to capability parity with the formats and source adapters supported by MarkItDown one-way, while making native mutation substantially stronger for writable formats and refusing unsafe or semantically dishonest writeback.

For a format/source to be considered supported by 2Ways it must have an explicit capability contract, source provenance, deterministic diagnostics, and a fidelity boundary. Native mutation is enabled only where the implementation can prove that the requested mutation is representable and that unrelated native content remains protected.

## Non-goals / scope ceiling

This program MUST NOT add:

- a hosted web application or editor UI;
- accounts, billing, collaboration, cloud storage, project workspaces, or a database;
- a workflow engine, scheduler, generic automation platform, or autonomous-agent framework;
- a plugin marketplace;
- a generic Office replacement;
- network writeback to remote sources such as Wikipedia, YouTube, RSS publishers, or Bing;
- silent conversion from one native file type to another as a substitute for round-trip fidelity.

The library may expose reusable readers, writers, capability reports, diagnostics, validation helpers, and fidelity evidence. Those are part of the round-trip engine and are in scope.

## Existing foundation retained

The program keeps the existing 2Ways architecture:

`source -> format reader -> DocumentIR -> typed edits -> format writer -> verifier -> output`

The existing deterministic DocumentIR, source digests, native locators, canonical serialization, Markdown projections, typed preconditions, OOXML package limits, DOCX/PPTX patchers, and preservation verification remain authoritative. Existing public APIs are evolved conservatively rather than replaced.

Existing `Diagnostic` and fidelity-report structures are reused rather than creating a parallel reporting system.

## Parity definition

One-way MarkItDown currently covers a mixture of native files, structured text, archives, media, webpages/remote sources, and cloud extraction backends. 2Ways parity therefore has three distinct meanings.

### Tier A: native round-trip formats

These have a stable native representation that can, in principle, be patched and returned in the same format.

Target set:

- DOCX
- PPTX
- XLSX
- XLS
- PDF
- HTML
- plain text
- CSV
- JSON
- XML
- IPYNB
- EPUB
- ZIP containers
- images with editable metadata/resources
- audio with editable metadata/resources
- Outlook MSG

For these formats, 2Ways should support native writeback for proven capabilities and fail closed for the rest.

### Tier B: remote/read-derived sources

Target set:

- RSS
- Wikipedia
- YouTube
- Bing SERP

These sources are supported as provenance-bearing IR inputs but MUST NOT pretend to be native-writeable. Edits may be materialized to a local artifact or exported projection, but `writeback_to_source` is false.

### Tier C: alternate extraction backends

Target set:

- Azure Document Intelligence
- Azure Content Understanding

These are readers/extraction backends, not storage formats. They may enrich DocumentIR. Only nodes carrying authoritative native locators may later be sent to a native format writer. Derived analyzer fields remain non-writeable unless a native mapping exists.

## Core rule: no silent corruption

A successful mutation MUST satisfy all of the following gates:

1. source authority: the supplied source matches the source descriptor/digest required by the edit session;
2. semantic precondition: the target semantic state still matches the edit's expectation;
3. native locator precondition: the native target still resolves unambiguously;
4. capability preflight: the node advertises the requested mutation under the current constraints;
5. format preflight: every edit in the transaction is validated before bytes are emitted;
6. mutation: only authorized native carriers are changed;
7. native preservation verification: unrelated native/package content remains unchanged under the format's preservation contract;
8. semantic re-read: the produced file is read again and the target semantics are compared against the expected state;
9. output commit: bytes are returned only after all verification succeeds.

Any failure aborts the transaction. There is no partial-success file.

## Phase F0: Capability Kernel

### Motivation

DOCX and PPTX currently encode mutation compatibility through format-specific metadata such as `pptx:patch_capabilities` and boolean compatibility markers. This does not scale to XLSX and the rest of the parity program.

F0 introduces one typed, format-neutral capability contract while preserving backward compatibility for existing readers/writers during migration.

### Capability model

Add `EditCapability` to the IR layer:

```python
@dataclass(frozen=True)
class EditCapability:
    operation: str
    fidelity: str = "lossless"
    constraints: Mapping[str, Any] = field(default_factory=dict)
    reason_code: str | None = None
```

`operation` must be non-empty and belong to the supported public edit vocabulary when it describes a writable capability.

`fidelity` initially accepts:

- `lossless`: the operation can be applied with the format's native preservation contract;
- `verified_rewrite`: the format requires a bounded rewrite, but semantic and native preservation verification is available;
- `derived_read_only`: content is derived from extraction/OCR/transcription/remote analysis and cannot be written back natively;
- `read_only`: native content is understood but mutation is intentionally unavailable.

A `Node` gains:

```python
capabilities: tuple[EditCapability, ...] = ()
```

Capabilities are deterministic, serializable, and immutable.

### Why a typed field instead of metadata-only

Capabilities are part of the cross-format contract and must survive canonical serialization, strict decode, test fixtures, and downstream tooling without knowing format-specific metadata keys. Format-specific implementation details remain in `constraints` or existing metadata.

### Diagnostics

Readers emit deterministic `Diagnostic` entries for important mutation exclusions. Diagnostic codes are machine-oriented and stable. Examples:

- `pptx.table.merged_cells`
- `docx.table.multiple_paragraphs`
- `xlsx.cell.shared_formula`
- `xlsx.sheet.unsupported_relationship`
- `pdf.text.unrepresentable_font_encoding`
- `image.ocr.derived_read_only`

A reader does not need to emit one warning for every ordinary read-only node; diagnostics are required when they explain why an otherwise expected capability was withheld or when the structure is malformed/ambiguous.

### Capability coverage report

Add a pure reporting API that derives coverage from a `DocumentIR` without mutating it.

```python
@dataclass(frozen=True)
class CapabilityCoverage:
    total_nodes: int
    writable_nodes: int
    read_only_nodes: int
    derived_nodes: int
    operations: Mapping[str, int]
    reason_codes: Mapping[str, int]
```

`capability_coverage(document)` counts capabilities deterministically. A node is writable if it has at least one capability whose fidelity is `lossless` or `verified_rewrite`. Derived-only nodes are counted separately.

The report is diagnostic/measurement infrastructure only; it does not grant permission to writers. Writers still enforce their own native checks.

### Migration strategy

F0 does not remove current DOCX/PPTX metadata. Instead:

1. add typed capabilities;
2. migrate PPTX tables/text/images/notes and DOCX tables/text/images where the existing code already has a proven compatibility decision;
3. keep existing metadata keys through the migration release so current writer logic stays stable;
4. later writers may consume the typed capability field directly once tests prove equivalence.

This avoids coupling the XLSX launch to a risky rewrite of the already-green DOCX/PPTX mutation paths.

## Phase F1: XLSX native round-trip

### Principle

XLSX is an OOXML package, but it is not modeled as a generic Markdown table. Workbooks, worksheets, typed cell values, formulas, styles, relationships, merged ranges, and shared strings have native semantics that must remain explicit.

The first XLSX tranche is intentionally strong for cell values while conservative for structure.

### F1.0 package authority

Reuse the existing hardened OOXML package reader and limits wherever possible. XLSX reader/writer must reject:

- invalid/duplicate ZIP members;
- unsafe package paths;
- XML parts over configured limits;
- invalid root relationships;
- missing workbook part;
- conflicting workbook content types;
- ambiguous worksheet relationships;
- external worksheet relationship targets where internal content is required;
- malformed namespace mixtures that defeat locator authority.

No XML parser may resolve external entities or fetch network resources.

### F1.1 workbook/sheet IR

Each worksheet becomes a `Canvas(kind="worksheet")` with deterministic `canvas_id`, worksheet name, index, and native locator metadata.

Cells become nodes with a new `kind="cell"` and a typed `SpreadsheetCellPayload`:

```python
@dataclass(frozen=True)
class SpreadsheetCellPayload:
    address: str
    value: Any = None
    data_type: str | None = None
    formula: str | None = None
    cached_value: Any = None
    number_format: str | None = None
```

The first tranche does not duplicate the entire workbook object model in DocumentIR. Workbook-level data that must be preserved but is not edited remains in the source package/native payload layer.

`INITIAL_NODE_KINDS` gains `cell`.

The semantic digest for a cell includes address, value/data type, formula, and number-format semantic fields where present.

### F1.2 first writable XLSX capability

F1 initially exposes a new public edit operation:

`set_cell_value`

Payload:

```python
{
    "value": JSON-compatible scalar or None,
    "data_type": optional explicit type token
}
```

A cell advertises `set_cell_value` only when all of these hold:

- it has one authoritative native `<c>` cell element or can be represented by a deterministic insertion into an existing authoritative row;
- it is not part of a merged range whose ownership is ambiguous;
- it is not a shared/array/dynamic formula cell;
- its value representation is supported by the first writer tranche;
- its worksheet relationship and namespace authority are valid;
- mutation does not require rewriting unrelated workbook structures.

Initially supported new values:

- `None` (clear scalar content while preserving the cell container/style where present);
- strings;
- booleans;
- integers;
- finite floats.

Dates/times, rich text, errors, formulas, shared strings creation, and structural edits remain read-only in the first writer tranche unless represented through a proven existing native carrier.

### F1.3 preservation-first cell writer

The writer begins from the original XLSX package bytes and replaces only worksheet XML parts that contain authorized edits.

For each target cell it must:

1. resolve sheet and cell locators from the original source package;
2. re-read the current native value;
3. check the edit semantic/native preconditions;
4. patch only the target `<c>` element/value carrier;
5. preserve the cell style index and unrelated attributes;
6. preserve all non-target cells and worksheet subtrees;
7. preserve all unrelated ZIP members exactly under the existing package-preservation contract;
8. re-read the result with the XLSX IR reader and verify the requested cell value.

No workbook rebuild through `openpyxl.save()` is acceptable as the production writer path because it can normalize unrelated package content.

`openpyxl` may be used as an independent validation reader in tests, not as the fidelity-preserving serializer.

### F1.4 shared strings policy

The initial writer does not mutate the global shared string table. Existing shared-string cells are readable. Setting a string value converts the target cell to OOXML inline-string representation only when this can be done locally without changing other cells and the re-read verifier confirms the value. This prevents refcount/index churn in `sharedStrings.xml`.

If an existing cell uses a shared/complex construct that cannot be safely localized, its write capability is withheld with a reason diagnostic.

### F1.5 formula policy

Formulas are readable in F1. The first `set_cell_value` operation is not advertised for shared/array/dynamic formula cells. A simple formula cell is also read-only for scalar overwrite in the first tranche unless the writer has an explicit tested contract for removing the formula and cached value together.

A later XLSX tranche will add `set_cell_formula` as a separate operation; F1 must not smuggle formula edits through `set_cell_value`.

### F1.6 merged cells

Merged ranges are readable. Only the top-left owner cell may eventually be writable. In the initial tranche, cells participating in merged ranges are conservatively read-only unless tests prove owner-only mutation does not disturb merge semantics.

### F1.7 XLSX diagnostics

At minimum:

- `xlsx.cell.formula_read_only`
- `xlsx.cell.merged_read_only`
- `xlsx.cell.unsupported_type`
- `xlsx.cell.ambiguous_locator`
- `xlsx.sheet.relationship_invalid`
- `xlsx.package.unsupported_workbook`

Diagnostics are stable codes; human messages may improve without breaking callers.

## Phase F2: Office deep editing

After XLSX scalar value mutation is production-green, deepen the three Office formats without changing the product boundary.

### DOCX targets

- run-level text style;
- paragraph style, spacing, indentation, alignment;
- hyperlink target/text mutation;
- image replacement and dimensions;
- lists/numbering where numbering relationships are authoritative;
- comments, footnotes/endnotes, bookmarks, simple fields;
- section/header/footer expansion;
- table cell formatting and selected multi-paragraph cells;
- bounded add/remove paragraph, image, and simple table operations.

Tracked changes, OLE, macros, complex field graphs, and ambiguous content controls remain fail-closed until separately proven.

### PPTX targets

- run/paragraph style;
- shape move/resize/rotation;
- hyperlinks/actions;
- image replacement/crop;
- add/remove bounded simple shapes/text boxes;
- notes mutation expansion;
- table styling;
- slide reordering and bounded add/remove simple slides;
- chart title/data mutations with embedded workbook synchronization where authoritative.

Themes, masters/layout inheritance, SmartArt, OLE, and complex chart/external-workbook cases remain guarded.

### XLSX targets

- `set_cell_formula`;
- hyperlink/comment edits;
- cell style/number format;
- row/column size/visibility;
- freeze panes;
- data validation/conditional-format ranges where safely patchable;
- sheet rename/add/remove;
- row/column insertion/removal with formula/reference rewriting only after independent validation;
- image and chart mutations.

## Phase F3: text and structured parity

### Plain text / Markdown

Source-span editing preserves detected encoding, BOM, newline convention, and final-newline state. Unsupported encoding transitions fail closed rather than silently re-encoding the whole file.

### CSV

Preserve delimiter, quote/escape convention, line endings, encoding, and rectangular/ragged shape semantics. Support cell edits first; structural row operations later.

### JSON

Use source-aware token/span patching for scalar edits so untouched lexical representation, key order, indentation, and whitespace remain unchanged. Structural object/array edits require deterministic formatting localized to the affected container.

### XML

Use namespace-aware secure parsing plus source/native locators. Text/attribute edits precede structural element edits. DTD/external entity/network resolution is disabled.

### HTML

Support text, selected attributes, links, image alt/src, table cells, and bounded structural edits. Script/style/template-owned or parser-recovery-ambiguous regions remain protected by default.

## Phase F4: notebooks, publications, archives

### IPYNB

Model cells explicitly. Support Markdown/code source and selected metadata. Code edits must have an explicit output policy: preserve, clear, or reject; default is reject when stale output ambiguity exists.

### EPUB

Treat EPUB as ZIP + OPF + XHTML + navigation + resources. Patch chapters/metadata/assets while preserving unrelated resources. Encrypted/DRM content is read-only/rejected.

### ZIP

ZIP is a preservation container. A nested supported artifact may be round-tripped and replaced into its exact member. Defend against Zip Slip, duplicate names, recursion bombs, extreme expansion, and compression-ratio abuse.

## Phase F5: PDF

PDF mutation is split from extraction. OCR text is derived/read-only unless an explicit image/page-content replacement is requested.

Native-safe mutation targets metadata, annotations, form fields, links, selected images, and bounded text objects only when object/font encoding is authoritative. Incremental update is preferred where valid. Re-rendering the entire PDF is not considered native round-trip fidelity.

## Phase F6: media and legacy binary formats

### Images

Native-editable: EXIF/XMP/IPTC/comments and explicit resource/pixel replacement. OCR/LLM descriptions are derived/read-only.

### Audio

Native-editable: format metadata, artwork, selected chapter/comment fields. Transcription is derived/read-only. Waveform replacement/transcoding must be an explicit resource operation.

### Outlook MSG

Patch bounded MAPI/compound-file properties only when the binary writer can prove preservation. MSG->EML->MSG conversion is not an acceptable native writer.

### XLS

BIFF/OLE is a separate adapter after XLSX. Start with cell/value structures and preserve unrelated records; do not treat XLS as XLSX with a different extension.

## Phase F7: remote and cloud-source parity

RSS/Wikipedia/YouTube/Bing gain source-aware readers and local materialization, but no source writeback. Azure extraction results gain provenance/derived capability labeling and can feed native writers only through authoritative locators.

## Public edit vocabulary

The long-term public vocabulary stays intentionally small. Current operations remain; new operations are added only when their semantics cannot be expressed safely by an existing operation.

Planned families:

- text: `replace_text`, `set_text_style`;
- geometry: `move_resize`;
- resources: `replace_resource`, `set_alt_text`;
- tables: `update_table_cells`;
- spreadsheet: `set_cell_value`, later `set_cell_formula`;
- structure: `add_node`, `remove_node`, later a narrowly-defined move operation if required;
- metadata/links: add only when native semantics require first-class preconditions.

Format-specific implementation data belongs in constraints/native locators, not in dozens of public operation names.

## Security invariants

All new adapters must preserve the existing fail-closed stance.

Required invariants include:

- bounded input/package/XML sizes;
- no implicit network fetch during parsing/verification;
- no external entity expansion;
- no archive path traversal;
- duplicate package-member rejection where ambiguity affects authority;
- exact internal/external relationship handling;
- deterministic locator resolution;
- explicit limits for recursive containers;
- finite numeric requirements;
- no mutation after failed preflight;
- source digest checks for source-locked writers.

## Testing program

Every writable format requires four layers.

### 1. Synthetic unit/TDD fixtures

Each capability begins with a failing regression test. Tests cover positive cases and precise fail-closed boundaries.

### 2. Property/adversarial tests

Key invariants:

- no-op produces byte-identical output when the writer contract promises byte identity;
- stale preconditions never mutate;
- invalid edits never mutate;
- untouched native regions remain equal;
- semantic re-read equals expected semantics;
- malformed namespaces/relationships never gain authority;
- size/path/recursion limits are enforced.

### 3. Real-world corpus

Build a legal/public/anonymized corpus from multiple producers, including Microsoft Office, LibreOffice, Google exports, OnlyOffice, browser/Adobe/LaTeX PDF producers, common EPUB generators, and representative structured text encodings.

Corpus results feed the capability coverage benchmark. Unsupported corpus cases remain explicit, not coerced into green results.

### 4. Differential validation

Where practical, validate output using an implementation independent from the writer: e.g. `openpyxl` for XLSX semantic checks, `python-docx`, `python-pptx`, independent JSON/XML parsers, and office/headless validators in dedicated compatibility jobs.

## CI and release gates

A capability is not production-ready until all applicable gates are green:

1. test-only RED evidence exists;
2. focused GREEN tests pass;
3. existing regression suite passes;
4. adversarial/fuzz invariants pass;
5. real-world corpus tranche passes at its declared boundary;
6. no-op byte identity passes where promised;
7. untouched-native preservation passes;
8. semantic re-read passes;
9. Python 3.10, 3.11, 3.12, and 3.13 package tests pass;
10. OCR/plugin compatibility matrix passes;
11. pre-commit passes;
12. exact PR head is green;
13. tested synthetic merge commit/tree is recorded;
14. actual merge tree equals the tested tree;
15. release tag points to the verified merge commit.

No release claim may say "bug-free" in the absolute sense. Release quality is expressed through the exact verified invariants and test evidence.

## Release sequence

Planned sequence, subject to evidence rather than calendar dates:

- `2ways-v0.3.0`: F0 Capability Kernel + first production XLSX scalar-cell round-trip;
- `2ways-v0.4.0`: deeper DOCX/PPTX/XLSX editing;
- `2ways-v0.5.0`: plain text/Markdown + CSV/JSON/XML/HTML native parity;
- `2ways-v0.6.0`: IPYNB + EPUB + recursive ZIP preservation;
- `2ways-v0.7.0`: PDF native-safe mutation tranche;
- `2ways-v0.8.0`: image/audio metadata + MSG + XLS bounded mutation;
- `2ways-v0.9.0`: remote/cloud source parity and full capability accounting;
- `2ways-v1.0.0`: only after capability contracts, fidelity boundaries, compatibility matrices, and migration promises are stable enough to maintain long-term.

## Immediate implementation tranche

The branch `nolane/phase-f-format-parity-foundation` implements only the independently releasable first tranche:

1. F0 typed capability model;
2. deterministic capability coverage reporting;
3. migration of already-proven DOCX/PPTX capabilities without changing writer behavior;
4. XLSX OOXML reader with worksheets/cell IR and conservative diagnostics;
5. `set_cell_value` validation/preconditions;
6. source-locked XLSX XML patch writer for supported scalar cells;
7. target semantic re-read and untouched-member/native-subtree verification;
8. identity Markdown integration only where the representation is reversible; otherwise typed API support is sufficient for v0.3.0;
9. full regression/CI hardening and documentation.

Later phases are not implemented on this branch merely because they appear in this master design. This prevents the parity program from becoming an unreviewable mega-PR.
