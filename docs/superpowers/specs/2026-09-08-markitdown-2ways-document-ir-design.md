# MarkItDown 2Ways — Document IR and High-Fidelity Round-Trip Architecture

**Date:** 2026-09-08  
**Status:** Design baseline  
**Branch:** `nolane/2way-document-ir-v0`  
**Upstream baseline:** `microsoft/markitdown@b6e8bbdce628d564c6af031b5f26cda6e818ea10`

## 1. Executive decision

MarkItDown 2Ways will preserve Microsoft MarkItDown as the ingestion foundation, but it will **not** make Markdown the canonical representation for round-trip editing.

The canonical representation will be a versioned **Document IR** that combines:

- semantic structure,
- reading order and hierarchy,
- page/slide geometry,
- style information,
- resources and relationships,
- source provenance,
- stable native-object locators,
- optional source-package preservation,
- and an explicit edit/patch history.

Markdown remains a first-class projection optimized for humans and LLMs. It is intentionally lossy unless emitted with MarkItDown 2Ways identity markers and backed by a preserved Document IR bundle.

For high-fidelity Office round trips, the preferred writer strategy is **surgical patching of the original OOXML package**, not rebuilding the whole document. Rebuild is a separate fallback mode for Markdown-only or synthetic documents.

This preserves the strongest part of the Microsoft architecture — simple, robust format-specific converters — while adding the missing half: structured intermediate representation, writers, round-trip provenance, and fidelity verification.

## 2. Why this architecture

### 2.1 MarkItDown's current strength

The current MarkItDown core already has a clean converter protocol, prioritized converter registration, optional dependencies, and plugins. Its public contract is optimized for:

`input document -> Markdown`

That path must remain stable. Existing callers of `MarkItDown.convert()`, `convert_stream()`, and `DocumentConverterResult.markdown` must continue to work without opting into 2Ways.

### 2.2 What we learn from other projects

This design intentionally learns architectural patterns from several mature projects without copying their implementations.

- **Docling / docling-core**: a unified document model with hierarchy, layout/bounding boxes, provenance, typed content items, and serializer abstractions. Important lesson: the rich model is canonical; Markdown is only one serializer and can flatten information such as table spans.
- **Pandoc**: the `Reader -> AST -> Writer` M×N architecture. Important lesson: readers and writers should be independent around one stable intermediate model. Also important: Pandoc explicitly documents that its AST is less expressive than many source formats, so formatting-perfect conversion cannot be guaranteed when the IR is too small.
- **pptx-automizer**: template-preserving PowerPoint manipulation, direct OOXML mutation, stable `creationId` usage, master/layout preservation, and deferred modification operations. Important lesson: when a native document already exists, patch the existing package instead of regenerating everything.
- **PptxGenJS**: a strong native OOXML generation API for synthetic presentations. Important lesson: generation and round-trip patching are different modes and should not be conflated.
- **Marp CLI**: strong Markdown-to-slide semantics and theming. Important negative lesson: its editable PPTX path currently routes through PDF and LibreOffice, and the source itself warns that slide reproducibility is not fully guaranteed; this is unsuitable as our fidelity core.
- **python-pptx**: already an optional MarkItDown dependency and a practical Python object model for reading/generating/editing PPTX. Important lesson: it is the natural first implementation substrate, with direct OOXML access used where higher fidelity is required.

## 3. Product goals

### 3.1 Primary goals

1. Keep the upstream Microsoft conversion behavior working by default.
2. Add a reusable Document IR that can represent both semantic and layout information.
3. Support `document -> IR -> Markdown` without losing source provenance inside the IR.
4. Support `Markdown projection -> IR edits` when stable identity markers are present.
5. Support `IR -> PPTX` in two distinct modes:
   - **patch**: preserve and minimally modify the original PPTX;
   - **rebuild**: generate a new PPTX when no suitable source package exists.
6. Make the reader/writer model extensible to DOCX, XLSX, HTML, PDF-derived layout documents, and plugins.
7. Add deterministic fidelity checks so "round-trip" has measurable meaning.
8. Preserve an easy upstream-sync path with `microsoft/markitdown`.

### 3.2 Secondary goals

- Give AI systems a compact Markdown view while keeping high-fidelity data outside the prompt.
- Allow edits to be represented as explicit operations, not only opaque document replacements.
- Permit future external writer bridges such as PptxGenJS without making Node.js a core dependency.
- Support a portable bundle format that can keep IR, assets, and source-package evidence together.

## 4. Non-goals for the first implementation wave

The first implementation will not claim pixel-perfect support for every PowerPoint feature. Specifically, the initial wave does not need full editing support for SmartArt, arbitrary embedded OLE objects, VBA, every chart subtype, every animation, or every transition.

However, unsupported native content must be **preserved whenever possible** in patch mode. "Not editable yet" is acceptable; silently deleting or rebuilding unknown content is not.

PDF is not treated as a symmetric editable source format. PDF can produce a rich layout IR, but a PDF-derived IR reconstructed into PPTX/DOCX is a transformation, not an exact round trip.

## 5. Compatibility contract with upstream MarkItDown

### 5.1 Existing API stays valid

The following behavior is frozen unless upstream changes it:

- `MarkItDown.convert(...) -> DocumentConverterResult`
- `MarkItDown.convert_stream(...)`
- `.markdown` and `.text_content`
- converter priority behavior
- existing `markitdown.plugin` converter plugins
- existing CLI behavior when no 2Ways flags are used

### 5.2 New functionality is additive

2Ways functionality is exposed through additive APIs. Proposed facade:

```python
from markitdown import MarkItDown
from markitdown.twoways import TwoWayMarkItDown

reader = MarkItDown()
twoway = TwoWayMarkItDown(markitdown=reader)

ir = twoway.read("deck.pptx")
markdown = twoway.to_markdown(ir, identity_markers=True)
result = twoway.write(ir, "deck-edited.pptx", mode="patch")
```

A later compatibility convenience may add methods on `MarkItDown`, but the first implementation should avoid making the upstream class responsible for both ingestion and writing.

## 6. High-level architecture

```text
                         INPUT
                           |
          +----------------+----------------+
          |                |                |
        PPTX             DOCX             MD/HTML ...
          |                |                |
          v                v                v
   Format IR Reader   Format IR Reader  Semantic Reader
          \                |               /
           \               |              /
            +--------------+-------------+
                           |
                           v
                  +------------------+
                  |   DOCUMENT IR    |
                  |------------------|
                  | semantics        |
                  | hierarchy        |
                  | reading order    |
                  | geometry         |
                  | styles           |
                  | resources        |
                  | relationships    |
                  | provenance       |
                  | native locators  |
                  | source package   |
                  | edit operations  |
                  +---------+--------+
                            |
             +--------------+-------------------+
             |              |                   |
             v              v                   v
         Markdown        JSON/bundle         AI edits
         projection          |                   |
             |               |                   |
             +---------------+-------------------+
                             |
                             v
                     Writer Registry
                             |
              +--------------+----------------+
              |                               |
              v                               v
       Round-trip patch                 Synthetic rebuild
       existing OOXML                   new document
              |                               |
              +---------------+---------------+
                              v
                            OUTPUT
```

## 7. Document IR

### 7.1 Design requirements

The IR must be:

- versioned,
- deterministic to serialize,
- stable enough for plugins,
- richer than Markdown,
- independent of a single Office format,
- capable of native-format extensions,
- explicit about provenance,
- and safe to partially understand.

The first implementation should use Python dataclasses / standard typing where practical to avoid making a heavy new runtime dependency mandatory. JSON serialization can be implemented explicitly. If schema complexity later justifies Pydantic, it can remain optional or be introduced in a major schema revision.

### 7.2 Top-level model

Proposed conceptual model:

```python
DocumentIR(
    schema_version: str,
    document_id: str,
    source: SourceDescriptor | None,
    metadata: DocumentMetadata,
    canvases: list[Canvas],
    nodes: dict[str, Node],
    resources: dict[str, Resource],
    relationships: list[Relationship],
    native_payloads: dict[str, NativePayload],
    edits: list[EditOperation],
    diagnostics: list[Diagnostic],
)
```

`Canvas` means slide/page/sheet-like surface. It avoids forcing a presentation vocabulary onto all formats.

### 7.3 Node model

All nodes share:

- stable IR node id,
- semantic role,
- parent/children references,
- order index,
- optional geometry,
- optional style,
- provenance,
- native locator,
- optional source text span.

Initial node families:

- `TextNode`
- `ImageNode`
- `TableNode`
- `ChartNode`
- `GroupNode`
- `ShapeNode`
- `LinkNode`
- `NoteNode`
- `UnknownNativeNode`

`UnknownNativeNode` is important. Unsupported content must still have identity/provenance and preservation status.

### 7.4 Geometry

Geometry is normalized but retains source units:

```text
Geometry:
  x, y, width, height
  rotation
  coordinate_origin
  unit
  transform
  source_bbox
```

For PPTX, the source representation should retain EMU values in native metadata even if convenience values are also expressed in inches or normalized coordinates.

### 7.5 Style

Style is layered rather than flattened:

```text
Style:
  direct properties
  inherited properties
  theme references
  resolved properties (optional cache)
```

This distinction is required because "font size 28" may come from a theme/master rather than a direct run property. Rewriting the resolved value as a direct property can change behavior and fidelity.

### 7.6 Provenance

Each node can point back to its source:

```text
Provenance:
  source_format
  canvas index
  native part URI
  object id / creationId
  relationship id
  bbox
  character span
  extraction method
  confidence (if inferred)
```

This mirrors the useful provenance principle in Docling but adds Office-native locators needed for mutation.

### 7.7 Native locator

For PPTX, preferred locator order:

1. Office `creationId` when available;
2. stable non-visual property id (`cNvPr/@id`);
3. shape name plus structural context;
4. XML path as a last-resort locator.

Locators must be treated as evidence, not globally unique truth. A writer validates the located element before applying an operation.

## 8. Source package and bundle model

### 8.1 Why source preservation matters

A semantic/layout model can never fully enumerate every current and future OOXML extension. To preserve unknown features, a true round-trip workflow should retain the original package.

### 8.2 TwoWays bundle

Proposed portable bundle extension: `.m2w`.

Conceptual layout:

```text
document.m2w
  /manifest.json
  /document.json
  /projections/document.md
  /assets/<sha256>.*
  /native/source.pptx
  /native/metadata.json
  /edits/operations.jsonl
```

The bundle is optional. Pure `DocumentIR` objects can exist in memory or JSON, but patch mode that promises source preservation requires source-package evidence.

### 8.3 Integrity

Store SHA-256 digests for:

- source package,
- resources,
- important OOXML parts,
- projection version.

The writer refuses strict patch mode when source evidence no longer matches the expected digest.

## 9. Markdown projection and re-import

### 9.1 Markdown is a projection, not the database

Default human/LLM Markdown remains clean. An opt-in identity-preserving projection adds unobtrusive markers:

```markdown
<!-- m2w:node=txt_01 canvas=1 -->
# Quarterly Revenue

<!-- m2w:node=txt_02 canvas=1 -->
Revenue increased **38%** year over year.
```

### 9.2 Projection metadata

The projection header records:

- schema version,
- document id,
- source digest,
- projection version,
- whether geometry/style details are externalized.

### 9.3 Re-import behavior

When a marked projection is re-imported:

1. parse identity markers;
2. map blocks back to IR nodes;
3. compute semantic changes;
4. create typed `EditOperation` records;
5. preserve non-projected properties unchanged;
6. reject ambiguous identity collisions in strict mode.

Markdown without identity markers is accepted only as a semantic source for rebuild mode. It cannot claim high-fidelity round-trip semantics.

## 10. Reader architecture

### 10.1 Existing converters remain unchanged

The existing `DocumentConverter` protocol continues to own Markdown ingestion.

### 10.2 New IR readers

Introduce a parallel protocol:

```python
class DocumentIRReader(Protocol):
    def accepts(self, file_stream, stream_info, **kwargs) -> bool: ...
    def read(self, file_stream, stream_info, **kwargs) -> DocumentIR: ...
```

Registration mirrors MarkItDown priorities:

```python
@dataclass(frozen=True)
class IRReaderRegistration:
    reader: DocumentIRReader
    priority: float
```

### 10.3 Composition with existing MarkItDown

An IR reader may reuse existing converter output as one semantic signal, but rich format readers should extract structure directly from the native object model.

For PPTX, do not parse the generated Markdown back into IR. Read the presentation object and OOXML once, then generate Markdown from the resulting IR.

## 11. Writer architecture

### 11.1 Writer protocol

```python
class DocumentWriter(Protocol):
    def accepts(self, ir: DocumentIR, target: TargetInfo, **kwargs) -> bool: ...
    def write(self, ir: DocumentIR, target: BinaryIO | Path, **kwargs) -> WriterResult: ...
```

`WriterResult` includes:

- target format,
- mode used (`patch`, `rebuild`, `projection`),
- bytes/path written,
- warnings,
- fidelity report,
- unsupported edit report.

### 11.2 Writer registry

Use prioritized registrations analogous to converter registrations. This keeps the mental model consistent with upstream MarkItDown and makes plugins easy to add later.

Future entry-point group:

```toml
[project.entry-points."markitdown.writer"]
...
```

Do not overload the existing `markitdown.plugin` interface version without an explicit compatibility layer.

## 12. Edit operations

Changes are explicit commands applied to nodes rather than uncontrolled mutation when possible.

Initial operations:

- `ReplaceText`
- `ReplaceRichText`
- `SetTextStyle`
- `MoveResizeNode`
- `ReplaceImage`
- `SetAltText`
- `UpdateTableCells`
- `UpdateChartData`
- `AddNode`
- `RemoveNode`
- `ReorderNode`

Each operation records:

- operation id,
- target node id,
- precondition digest,
- old/new semantic values where appropriate,
- writer capability requirements,
- timestamp/source label only when explicitly requested (deterministic serialization should not inject wall-clock timestamps by default).

Precondition digests prevent an edit from silently targeting a different native object after the source changes.

## 13. PPTX implementation strategy

PPTX is the first full two-way format because the fork already has a mature `PptxConverter` and `python-pptx` is already the optional dependency.

### 13.1 PPTX IR reader

The reader extracts:

- presentation metadata and slide size,
- slides in presentation order,
- masters/layout references,
- shape tree including groups,
- text frames, paragraphs, runs,
- tables,
- pictures and media relationships,
- charts at least as native/provenance nodes initially,
- notes,
- geometry,
- alt text,
- shape ids/names/creationIds,
- relevant relationship ids,
- native OOXML part URIs.

The current `PptxConverter`'s shape traversal, picture handling, SVG fallback logic, chart extraction, and notes handling are reusable knowledge. The new reader should share helper utilities where doing so does not destabilize the converter.

### 13.2 PPTX patch writer

Patch mode starts from the preserved source PPTX.

Algorithm:

1. verify source package digest;
2. copy the source ZIP package to an output transaction;
3. identify the minimum set of affected OOXML parts;
4. validate node locators and edit preconditions;
5. apply only supported operations;
6. preserve untouched ZIP members unchanged;
7. update relationships/content types only if an operation requires it;
8. write the output package;
9. reopen with `python-pptx` as a structural smoke test;
10. produce a fidelity report.

For high-fidelity operations, direct OOXML patching is allowed behind isolated adapter code. It must not leak private XML assumptions throughout the package.

### 13.3 PPTX rebuild writer

Rebuild mode creates a new presentation from IR. Initial implementation can use `python-pptx` because it is already in the Python dependency model.

A future optional writer bridge may target PptxGenJS for features where it is clearly stronger, but Node.js will not be required by the core Python package.

### 13.4 Modes

`mode="auto"`:

- use `patch` when source package + valid provenance are present;
- otherwise use `rebuild`.

`mode="patch"`:

- fail if required provenance or source package is unavailable;
- never silently fall back to rebuild.

`mode="rebuild"`:

- always generate a new presentation and report unsupported properties.

## 14. DOCX strategy

DOCX follows the same architecture after PPTX proves the IR/writer contracts.

Reader should preserve:

- paragraphs/runs,
- styles and inheritance,
- sections,
- tables and merged cells,
- headers/footers,
- lists/numbering,
- images/relationships,
- comments/notes where supported,
- native part references.

Patch mode should preserve the original Word package and edit minimum OOXML parts. Rebuild can use `python-docx` or an OOXML writer behind a format adapter; dependency choice is made during the DOCX implementation phase based on fidelity tests, not convenience alone.

## 15. XLSX strategy

XLSX requires a sheet/cell-specific extension of the common IR rather than pretending a spreadsheet is a paginated document.

Common `DocumentIR` metadata can be reused, but spreadsheet-native payloads must preserve:

- workbook/sheet identities,
- cells and formulas,
- number formats,
- merged regions,
- dimensions,
- charts/drawings,
- named ranges,
- styles,
- relationships.

`openpyxl`, already used by the project, is the initial implementation substrate.

## 16. PDF strategy

PDF reader can produce layout-rich IR with provenance. PDF output from edited IR is supported as a rendering/export target.

Do not label `PDF -> IR -> PPTX` as lossless round trip. The fidelity report must identify it as reconstruction because PDF usually lacks the editable source semantics of Office files.

Docling integration is best treated as an optional high-quality reader/backend or model adapter, not as a mandatory core dependency.

## 17. Public API proposal

### 17.1 Read

```python
ir = twoway.read(
    "deck.pptx",
    preserve_source=True,
    fidelity="high",
)
```

### 17.2 Project

```python
md = twoway.to_markdown(
    ir,
    identity_markers=True,
    include_notes=True,
)
```

### 17.3 Apply edited Markdown

```python
edit_result = twoway.apply_markdown(
    ir,
    edited_markdown,
    strict_identity=True,
)
```

### 17.4 Write

```python
result = twoway.write(
    ir,
    "out.pptx",
    mode="patch",
    verify=True,
)
```

### 17.5 Direct conversion convenience

```python
twoway.convert_to(
    "slides.md",
    "slides.pptx",
    mode="rebuild",
)
```

## 18. CLI proposal

Existing CLI behavior is unchanged.

New options:

```text
markitdown input.pptx --to-ir document.m2w
markitdown input.pptx --to markdown --identity-markers -o document.md
markitdown document.m2w --apply-markdown edited.md --to pptx -o edited.pptx
markitdown slides.md --to pptx -o slides.pptx
markitdown document.m2w --to pptx --mode patch -o patched.pptx
```

The exact parser wiring is implemented only after API contracts stabilize.

## 19. Fidelity model

"Looks right" is not sufficient. Writer results include measurable fidelity information.

### 19.1 Patch fidelity checks

- source package digest verified before edit;
- untouched ZIP member set comparison;
- byte identity for untouched members where feasible;
- relationship graph validity;
- content-types validity;
- successful reopen with `python-pptx`;
- target nodes re-resolved after write;
- requested edits re-read and compared semantically.

### 19.2 Rebuild fidelity checks

- output opens structurally;
- canvas count and ordering;
- node count by supported type;
- geometry tolerance;
- text equality / normalized rich-text equality;
- media digest equality where copied;
- table structure equality for supported features;
- explicit unsupported-feature list.

### 19.3 Fidelity tiers

- `exact-preserve`: untouched native package content preserved and supported edits applied surgically;
- `high`: native semantics/layout largely retained but some serialization may change;
- `semantic`: content structure preserved, visual fidelity not guaranteed;
- `reconstructed`: target synthesized from a less expressive source.

A result must never claim a stronger tier than the verification evidence supports.

## 20. Error handling

Introduce typed errors:

- `TwoWayError`
- `IRValidationError`
- `SourcePackageMismatchError`
- `WriterNotFoundError`
- `UnsupportedEditError`
- `AmbiguousNativeLocatorError`
- `PatchPreconditionError`
- `RoundTripVerificationError`

Strict patch mode is fail-closed. Best-effort mode is opt-in and returns warnings per skipped operation.

## 21. Security

2Ways expands the attack surface because it reads and rewrites ZIP/XML packages.

Required controls:

- ZIP path traversal protection;
- decompressed-size and member-count limits;
- protection against XML external entities;
- no automatic resolution of external Office relationships;
- resource size limits;
- MIME/extension validation;
- no execution of embedded macros or OLE payloads;
- preserve-but-do-not-execute policy for unknown binary parts;
- deterministic temporary file cleanup;
- explicit opt-in for network resources.

The project must keep MarkItDown's existing security posture of running with the current process privileges and should document that round-trip writers may preserve potentially active content from trusted source files.

## 22. Package layout proposal

```text
packages/markitdown/src/markitdown/
  twoways/
    __init__.py
    _facade.py
    _errors.py
    _registry.py
    ir/
      __init__.py
      document.py
      nodes.py
      geometry.py
      style.py
      provenance.py
      resources.py
      edits.py
      serialization.py
    projection/
      markdown.py
    readers/
      base.py
      markdown_reader.py
      pptx_reader.py
    writers/
      base.py
      pptx_patch.py
      pptx_rebuild.py
    native/
      ooxml_package.py
      pptx_locators.py
      pptx_xml.py
    verification/
      pptx.py
      fidelity.py
```

Files should remain small and responsibility-focused. Shared private OOXML helpers should be isolated under `native/`, not mixed into high-level IR code.

## 23. Dependency strategy

Core MarkItDown dependencies must not become significantly heavier for users who only want one-way Markdown extraction.

Proposed extras:

```toml
[project.optional-dependencies]
twoway = []
twoway-pptx = ["python-pptx"]
twoway-docx = [...]
twoway-all = [...]
```

The final naming can be reconciled with existing `pptx`, `docx`, and `all` extras during implementation. Prefer reusing existing extras rather than duplicating dependency graphs when possible.

Docling and Node/PptxGenJS integrations, if added, are separate optional bridges.

## 24. Upstream synchronization strategy

The fork should remain recognizably MarkItDown.

Rules:

1. Avoid rewriting upstream converter files unless a shared helper genuinely benefits both paths.
2. Put most 2Ways code under a new namespace.
3. Preserve upstream tests and CLI defaults.
4. Keep 2Ways commits logically separated from upstream sync commits.
5. Document the upstream commit used for each release.
6. Prefer additive hooks to invasive changes.

## 25. Testing strategy

### 25.1 Compatibility tests

- run all existing MarkItDown tests unchanged;
- verify representative conversion output is unchanged when 2Ways is unused;
- verify plugin loading remains unchanged.

### 25.2 IR unit tests

- deterministic ids when source native ids are stable;
- JSON serialize/deserialize round trip;
- schema validation;
- hierarchy consistency;
- geometry/unit conversion;
- resource digest behavior;
- edit preconditions.

### 25.3 Markdown projection tests

- deterministic projection;
- clean projection without markers;
- identity projection with markers;
- marked Markdown -> edits -> IR mapping;
- ambiguity and deleted-marker failures.

### 25.4 PPTX reader tests

Fixtures for:

- titles and body text;
- rich text runs;
- grouped shapes;
- images including SVG edge cases already handled by the existing converter;
- tables;
- charts;
- speaker notes;
- custom masters/layouts;
- shape ids/creationIds;
- hidden/unknown content preservation evidence.

### 25.5 PPTX patch tests

- replace one text run and verify unrelated ZIP members are byte-identical;
- edit table cells;
- replace image while maintaining relationships;
- reject wrong source digest;
- reject stale node precondition;
- preserve unknown parts;
- reopen output with `python-pptx`;
- read output back into IR and verify requested edits.

### 25.6 PPTX rebuild tests

- Markdown -> PPTX smoke test;
- geometry/layout test;
- text/table/image generation;
- notes;
- output reopenability;
- explicit fidelity tier.

### 25.7 Property and corruption tests

- malformed ZIP;
- duplicate member names;
- oversized compressed members;
- malformed XML;
- broken relationships;
- missing assets;
- ambiguous locators.

## 26. Implementation phases

### Phase A — Core IR contract

Deliver:

- `DocumentIR` data model;
- deterministic serialization;
- errors;
- reader/writer interfaces and registries;
- fidelity result model;
- tests.

Exit criteria: no change to existing MarkItDown behavior; IR unit suite green.

### Phase B — Markdown projection loop

Deliver:

- IR -> Markdown projection;
- optional identity markers;
- marked Markdown -> edit operations;
- semantic Markdown reader for rebuild workflows.

Exit criteria: edit a marked Markdown paragraph and map it deterministically back to the same IR node.

### Phase C — PPTX high-fidelity reader

Deliver:

- PPTX -> rich IR;
- source package capture;
- native locator extraction;
- slide/master/layout metadata;
- shared image/SVG helpers where safe.

Exit criteria: fixtures produce stable semantic/layout/native identifiers and preserved source evidence.

### Phase D — PPTX patch writer

Deliver:

- transactional OOXML package copy/patch;
- text edits first;
- table and image edits next;
- verification report.

Exit criteria: one-text-node edit changes only required package parts and output reopens correctly.

### Phase E — PPTX rebuild writer

Deliver:

- Markdown/IR -> new PPTX;
- master/theme strategy;
- core text/image/table/shape generation;
- fidelity reporting.

Exit criteria: useful editable PPTX generation without LibreOffice/PDF detour.

### Phase F — DOCX two-way

Apply the proven reader/patch/rebuild pattern to DOCX.

### Phase G — XLSX and layout/PDF adapters

Add spreadsheet-native extensions and optional Docling-based rich layout ingestion.

### Phase H — writer plugins and external bridges

Stabilize plugin interface and optionally add PptxGenJS or other writer adapters when they provide measurable value.

## 27. Acceptance definition for "2Ways"

The project may call a format "two-way supported" only when all of these exist:

1. native format reader -> Document IR;
2. Markdown/AI-editable projection;
3. IR writer to the native format;
4. at least one verified edit round trip;
5. fidelity report;
6. unsupported-feature behavior is explicit;
7. regression fixtures cover the supported contract.

A format with only `Markdown -> format` generation is a writer, not full two-way support.

## 28. First engineering slice after this spec

The first code slice should be deliberately foundational rather than flashy:

1. create `markitdown.twoways` namespace;
2. implement `DocumentIR`, `Canvas`, core node/provenance/geometry/resource models;
3. implement deterministic JSON serialization;
4. implement `DocumentIRReader` / `DocumentWriter` protocols and priority registries;
5. add fidelity/result/errors;
6. add tests before production implementation for each contract;
7. keep the existing `MarkItDown` tests untouched and green.

Only after this substrate is stable should the PPTX reader and patch writer be layered in.

## 29. Research references

- Microsoft MarkItDown: https://github.com/microsoft/markitdown
- Docling: https://github.com/docling-project/docling
- Docling Core: https://github.com/docling-project/docling-core
- Pandoc: https://github.com/jgm/pandoc
- pptx-automizer: https://github.com/singerla/pptx-automizer
- PptxGenJS: https://github.com/gitbrent/PptxGenJS
- Marp CLI: https://github.com/marp-team/marp-cli
- python-pptx: https://github.com/scanny/python-pptx

## 30. Design invariants

These invariants are the core of the project and should be treated as review blockers if violated:

1. **Markdown is never the only source of truth for a claimed high-fidelity round trip.**
2. **Patch mode never silently rebuilds.**
3. **Unknown native content is preserved when possible, not discarded because the IR cannot edit it yet.**
4. **Existing MarkItDown one-way behavior remains opt-out-free and backwards compatible.**
5. **Readers and writers are separated by a versioned IR contract.**
6. **Fidelity claims are evidence-based and machine-reported.**
7. **Core Python use does not require Node.js, LibreOffice, or cloud services.**
8. **Upstream syncability is a first-class engineering constraint.**
