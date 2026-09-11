# MarkItDown 2Ways Full-Parity Program Design

## Status

Approved architectural direction for the post-v0.2.0 program. The program starts from `main@fa897976a92aea707ba12a9b2294fdce5f067615` and keeps the project bounded to a document/file round-trip engine. It must not become a general office platform, collaboration product, workflow system, autonomous agent framework, cloud service, or editor application.

## Goal

Bring the 2Ways layer toward parity with the file/source families supported by MarkItDown one-way while making the writable subset materially stronger than v0.2.0. “Parity” is capability-aware: every supported source must be representable through a deterministic IR path, but native writeback is exposed only when the source format has an authoritative mutation model and the edit can be proven safe.

The project must optimize for three properties in this order:

1. **No silent corruption.** If an edit cannot be proven safe, reject it before writing output.
2. **Preservation.** Preserve untouched native package members/subtrees/resources whenever the format permits source-preserving mutation.
3. **Coverage.** Expand the number of formats and mutation capabilities only behind explicit capability and verification contracts.

## Scope ceiling

The following are explicitly in scope:

- deterministic source reading into `DocumentIR`;
- capability discovery and read-only diagnostics;
- identity/semantic Markdown projections when reversible enough for the requested operation;
- typed edits with stale-source protection;
- format-native or source-preserving writers;
- semantic re-read verification;
- native preservation verification;
- corpus, fuzz, adversarial, differential and performance validation;
- source adapters for remote/derived sources that materialize local artifacts without pretending to mutate the remote source.

The following are explicitly out of scope:

- web or desktop editor UI;
- account, collaboration or cloud-storage features;
- workflow engines, task schedulers and autonomous agents;
- databases or SaaS backends;
- plugin marketplaces;
- generic Office automation APIs unrelated to round-trip editing;
- automatic mutation of Wikipedia, YouTube, Bing or other remote sources;
- pretending OCR/transcription/LLM captions are native editable source text.

## Existing baseline

v0.2.0 already provides:

- deterministic/versioned `DocumentIR`;
- source descriptors, provenance, resources and native locators;
- canonical serialization and digests;
- typed edit preconditions;
- identity and semantic Markdown paths;
- source-locked DOCX and PPTX writers;
- text, image-alt-text and simple table-cell mutation for selected structures;
- no-op byte identity in the supported OOXML paths;
- native/semantic preservation checks;
- malformed OOXML, namespace, relationship and archive hardening.

The one-way converter registry currently covers plain text, HTML, RSS, Wikipedia, YouTube, Bing SERP, IPYNB, PDF, DOCX, XLSX, XLS, PPTX, audio, image, Outlook MSG, ZIP, EPUB and CSV, plus Azure Document Intelligence / Content Understanding when configured.

## Architecture

The program uses a **Capability Kernel + format adapters** architecture:

```text
Source bytes / source URI
        |
        v
 Format/source reader
        |
        v
    DocumentIR
        |
        +--> Capability Kernel --> capability report / read-only reasons
        |
        v
   Typed edits
        |
        v
  Format preflight
        |
        v
Transactional writer
        |
        v
 Native verifier + semantic re-read
        |
        v
  Verified output bytes
```

No writer may infer editability merely because a node exists in IR. An operation is writable only when the format reader/adapter declares a matching capability and the writer re-validates the native preconditions.

## Capability Kernel

### Wire compatibility

The v0.x program must not bump the entire `DocumentIR` schema solely to introduce capabilities. Node capability declarations are stored in a reserved metadata namespace and surfaced through typed APIs.

Reserved key:

```text
metadata["twoways.capabilities.v1"]
```

The wire value is a sequence of objects with the following fields:

```json
{
  "operation": "replace_text",
  "state": "writable",
  "reason_code": null,
  "constraints": {
    "preservation": "native-subtree",
    "identity_markdown": true
  }
}
```

Allowed states:

- `writable`: the operation is currently authorized for this node subject to constraints and edit preconditions;
- `read-only`: the node is semantically readable but this operation is intentionally not writable;
- `derived`: the visible semantic content was extracted/generated from another native representation and must not be mutated as if it were authoritative source text.

Unknown or absent capability declarations default to read-only.

### Typed API

Add public typed contracts under `markitdown.twoways.capabilities`:

- `CapabilityState`
- `CapabilityDecision`
- `NodeCapabilityProfile`
- `CapabilityReasonSummary`
- `CapabilityReport`
- `capabilities_for_node(node)`
- `build_capability_report(document)`

The report must count total nodes, nodes with at least one writable operation, read-only nodes, derived nodes, writable counts by operation, and read-only/derived reason-code frequencies. Results must be deterministic and sorted.

### Reason codes

Reason codes are machine-readable and stable within a minor release. Examples:

- `capability.unspecified`
- `docx.table.merged_cells`
- `docx.text.ambiguous_run_layout`
- `pptx.chart.external_workbook`
- `xlsx.cell.formula_requires_explicit_formula_edit`
- `xlsx.cell.merged_range`
- `xlsx.sheet.unsupported_structure`
- `pdf.text.unrepresentable_font_encoding`
- `image.ocr.derived`
- `audio.transcript.derived`
- `remote.source.not_native_writable`

Human-readable diagnostics may change without changing reason-code semantics.

## Mutation safety contract

Every native mutation follows this sequence:

1. verify source bytes/hash/package identity;
2. resolve the target by authoritative native locator;
3. verify semantic digest/native locator digest/expected old value;
4. verify declared capability and capability constraints;
5. preflight the complete edit set before writing any output;
6. mutate a transactional in-memory representation;
7. verify the resulting native structure;
8. re-read the target semantics;
9. compare expected semantics with re-read semantics;
10. verify untouched native members/subtrees/resources according to the format contract;
11. return bytes only after all required checks pass.

If any required step fails, no partially mutated output is returned.

## Format classes

### Class A: source-preserving native packages

DOCX, PPTX, XLSX, EPUB and ZIP-contained supported files. Writers patch the original archive/package and preserve unrelated members where possible.

### Class B: source-preserving textual/structured formats

Plain text, Markdown, CSV, JSON, XML and HTML. Writers prefer byte/source-span patching and preserve encoding, line endings, quoting or untouched lexical form when the format permits.

### Class C: complex binary/native formats

PDF, XLS, Outlook MSG, images and audio. Native mutation is added only in narrowly verified tranches. Derived OCR/transcription/caption content remains explicitly derived unless the operation is a resource replacement.

### Class D: remote/derived source adapters

RSS URLs, Wikipedia, YouTube, Bing SERP, Azure Document Intelligence and Azure Content Understanding are readable into IR. They do not imply writeback to the remote origin. Edits may materialize a local artifact or feed a compatible native writer when authoritative locators map back to a local source file.

## Release program

### v0.3.0 — Capability Kernel + XLSX foundation

- typed capability model and reports;
- deterministic read-only reasons;
- XLSX package reader using existing OOXML safety primitives;
- worksheet canvases and cell semantics;
- direct typed cell value edits for a conservative set of native cells;
- identity Markdown round trip for lossless simple text-cell regions;
- transactional XLSX writer;
- native and semantic verification;
- XLSX corpus/adversarial tests;
- no structural row/column/sheet mutation in the first tranche.

### v0.4.0 — Office deep editing

Expand DOCX/PPTX/XLSX formatting, resource and bounded structural edits while retaining format-specific preservation proofs.

### v0.5.0 — Text and structured parity

Plain text/Markdown, CSV, JSON, XML and HTML source-preserving writers.

### v0.6.0 — Notebook/publication/container parity

IPYNB, EPUB and recursive ZIP preservation container editing.

### v0.7.0 — PDF native-safe editing

Metadata, annotations/forms/links and only then selected text/image operations with font/object-graph proof.

### v0.8.0 — Media, MSG and legacy XLS

Native metadata/resource mutation for images/audio, bounded Outlook MSG mutation and BIFF/XLS work.

### v0.9.0 — full one-way input parity semantics

Remote/derived source adapters and Azure reader bridges with explicit non-native-writeback semantics.

### v1.0.0 gate

Only after public capability contracts, source-preservation semantics and the format support matrix are stable enough to maintain long term.

## XLSX design

### Principle

The 2Ways XLSX writer must not use `openpyxl.save()` as the production mutation path because a library round-trip may rewrite workbook structure unrelated to the requested change. `openpyxl` may be used only for differential validation in tests.

The native path uses the existing safe OOXML package layer and direct SpreadsheetML parsing/patching.

### Part discovery

The reader must discover and validate:

- package content types;
- office-document relationship to workbook;
- workbook part;
- workbook relationships;
- worksheet parts;
- optional shared strings;
- optional styles;
- optional calculation chain, drawings, tables, comments and other relationships for preservation awareness.

Ambiguous workbook relationships, duplicate authoritative parts, invalid internal targets, unsupported namespace mixing or malformed XML fail closed.

### IR mapping

Each worksheet maps to one `Canvas` with `kind="worksheet"`. The sheet’s used cell region maps to a `table` node whose `TableCell.metadata` preserves cell address and native cell semantics. The first tranche records at minimum:

- `address`;
- `data_type`;
- `formula` when present;
- `style_id` when present;
- `number_format_id` when resolvable;
- `native_value_kind`;
- merge membership;
- worksheet part locator and cell reference locator.

The display text in `TableCell.text` is a projection. Writers must use metadata/native XML, not the display text alone, to determine typed cell edits.

### First writable cell classes

Initial `update_sheet_cells` support is limited to cells that satisfy all of the following:

- worksheet/cell locator resolves uniquely;
- cell is not inside a merged range;
- cell has no formula;
- edit does not change row/column structure;
- target value is one of string, integer/float, boolean or blank;
- cell style is preserved unchanged;
- formula, data-validation, conditional-formatting, table, chart and drawing relationships are not structurally changed.

For string writes, the writer may convert the target cell to SpreadsheetML inline string representation so the change remains local to the cell and does not mutate shared-string entries referenced elsewhere. This is a supported native representation change and must be reported as high fidelity rather than exact native-subtree identity for the target cell.

Numeric/boolean/blank writes patch only the target cell representation required by SpreadsheetML.

Formula cells are read-only in the first tranche with reason `xlsx.cell.formula_requires_explicit_formula_edit`; formula mutation is a later capability and must never be smuggled through a scalar-value edit.

### XLSX edit type

Add a single spreadsheet-specific edit type:

```text
update_sheet_cells
```

Payload:

```json
{
  "sheet": "Sheet1",
  "updates": [
    {
      "row": 0,
      "column": 1,
      "old_value": "North",
      "value": "South"
    }
  ]
}
```

Coordinates are zero-based in the typed API. Updates are deterministic, unique and sorted by `(row, column)`. Boolean coordinates are rejected. Duplicate coordinates, stale old values, out-of-range coordinates and no-op updates are rejected before mutation.

The operation carries the same semantic/native precondition discipline as existing edit operations.

### Markdown path

Identity Markdown support is enabled only when the worksheet region can be represented losslessly under the identity-table rules. The importer emits `update_sheet_cells`, not generic `update_table_cells`, for XLSX-backed worksheet nodes. Typed scalar fidelity remains authoritative; if Markdown cannot preserve the original type unambiguously, that cell remains read-only through Markdown even if direct typed edit APIs can mutate it.

### Verification

Required XLSX checks include:

- source package digest matches expected source;
- target worksheet part and cell locator remain authoritative;
- all requested target cells re-read to the expected typed value;
- no unrequested cell semantic changes in the target worksheet;
- untouched package members remain byte-identical;
- unrelated worksheet XML subtrees remain preserved under canonical/native checks;
- no-op write is byte-identical;
- malformed/ambiguous workbook structures fail closed;
- output opens through an independent library in differential tests when the optional dependency is present.

## DOCX/PPTX deepening rules

Subsequent Office tranches may add run/style/geometry/resource/structure mutation, but every capability must be narrower than the native structure it can prove. Complex tracked changes, SmartArt, macros, OLE, external workbook links, unsupported fields, theme/master relationships and other ambiguous features remain read-only until a dedicated verified implementation exists.

## Text/structured format rules

Plain text and CSV must preserve source encoding/line endings/quoting conventions. JSON/XML/HTML should prefer source-span or subtree patching over whole-document pretty-printing. Any transformation that would rewrite unrelated lexical content must be reported explicitly and gated behind a lower fidelity tier or rejected when the caller requires source preservation.

## Derived-content rules

OCR text, audio transcripts, LLM image descriptions and remote extraction results are `derived`. Editing that semantic text never implicitly edits pixels, waveforms, videos or remote pages. Native changes require explicit resource/metadata operations.

## Test strategy

Every capability tranche must contain:

- test-first RED evidence;
- focused GREEN tests;
- stale-precondition tests;
- no-op identity tests where the format contract permits;
- target-only mutation tests;
- malformed/adversarial tests;
- serialization/public-import tests for new stable contracts;
- corpus tests from multiple producers when available;
- property-based/fuzz tests for parsers and edit validation;
- differential validation using independent libraries where practical;
- full existing regression suite;
- Python 3.10–3.13 CI;
- pre-commit CI;
- exact-head verification before merge;
- tested synthetic merge tree verification before release.

## Release rule

A format is never advertised as writable merely because it parses or because a library can save it. A format/capability is advertised only after the reader, writer, precondition checks, semantic verifier and native preservation verifier all exist and pass the required release gates.
