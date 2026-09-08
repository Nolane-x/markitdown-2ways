# MarkItDown 2Ways — Phase C Native PPTX Round-Trip Design

**Date:** 2026-09-08  
**Status:** Design ready for user review  
**Parent:** `2026-09-08-markitdown-2ways-phase-b-markdown-roundtrip-design.md`  
**Branch:** `nolane/2way-document-ir-v0`

## 1. Objective

Phase C turns the Phase A/B contracts into the first real rich-document round trip:

```text
original.pptx
    │
    ▼
PPTX native reader
    │
    ▼
DocumentIR + native locators + source digest
    │
    ├──► clean / identity Markdown
    │                    │
    │                 AI edit
    │                    │
    ◄──── typed EditOperation(s)
    │
    ▼
PPTX minimal patch writer
    │
    ▼
edited.pptx
```

The primary product invariant is:

> If the requested edit touches one semantic object, MarkItDown 2Ways changes the minimum necessary OOXML and preserves unrelated package content rather than rebuilding the presentation.

Phase C v1 supports native PPTX reading plus conservative patching for:

- `replace_text` on patch-compatible text shapes/notes;
- `set_alt_text` on picture shapes.

It does **not** silently fall back to rebuilding a PPTX when patching is unsafe.

## 2. Current upstream seam

The existing MarkItDown `PptxConverter` already uses `python-pptx` and understands slide titles, text frames, tables, charts, pictures, notes and grouped shapes. It also reaches into native elements/relationships for image alt text and SVG handling.

Phase C deliberately leaves this one-way converter unchanged. The two-way engine is introduced beside it under `markitdown.twoways`, so upstream `MarkItDown.convert()` behavior and optional-dependency semantics remain stable.

The existing `pptx` optional feature already installs `python-pptx`. Phase C may use `lxml` directly for narrowly scoped OOXML mutations, so `lxml` becomes an explicit member of the `pptx` optional dependency rather than relying only on a transitive dependency.

## 3. Approaches considered

### A. Load and save the whole deck through `python-pptx`

Advantages:

- smallest implementation;
- convenient high-level object API.

Rejected as preservation authority because a complete library save may regenerate package structures and cannot be assumed to preserve every unsupported or extension OOXML node byte-for-byte.

`python-pptx` remains useful for semantic reading and post-write validation.

### B. Raw textual XML replacement

Advantages:

- can touch very few bytes.

Rejected because XML attribute ordering, escaping, namespace variation, whitespace and legitimate OOXML structure make string replacement too fragile for a production patch engine.

### C. Hybrid semantic reader + native package patcher — selected

Selected architecture:

- `python-pptx` provides semantic/object access;
- the original ZIP/OPC package is the preservation authority;
- native locators bind IR nodes to source OOXML;
- a safe XML parser mutates only explicitly supported elements;
- only touched XML parts are reserialized;
- all untouched members are copied with identical uncompressed content bytes;
- output is reopened and reread for verification.

This mirrors the useful preservation principle learned from `pptx-automizer` while staying native to MarkItDown's Python stack.

## 4. Module boundaries

```text
markitdown/twoways/
  ooxml/
    __init__.py
    package.py
    relationships.py
    xml.py
    limits.py

  formats/
    __init__.py
    pptx/
      __init__.py
      model.py
      reader.py
      locators.py
      text.py
      shapes.py
      resources.py
      patch.py
      writer.py
      verify.py
```

### Generic OOXML layer

`ooxml/package.py`
- validates and inventories an OPC/ZIP package;
- records member order, metadata and content digests;
- supports a sparse `part_name -> replacement_bytes` override map;
- writes a new package without interpreting format-specific slide semantics.

`ooxml/relationships.py`
- parses package/part `.rels` files;
- normalizes relationship targets without resolving external URIs;
- exposes read-only relationship records in Phase C v1.

`ooxml/xml.py`
- safe XML parser/serializer configuration;
- namespace constants/helpers;
- no entity resolution, network access or DTD loading.

`ooxml/limits.py`
- configurable package safety limits.

The generic layer is intentionally small. It exists because DOCX later needs the same package/content-type/relationship preservation substrate, but Phase C does not create a generic Office object model.

### PPTX layer

`pptx/model.py`
- format-specific result/options/value contracts.

`pptx/reader.py`
- `PPTX -> DocumentIR` orchestration.

`pptx/locators.py`
- derive/resolve slide and shape native locators;
- creation-id and shape-id logic;
- ambiguity detection.

`pptx/text.py`
- rich-text extraction;
- patch-compatibility analysis;
- run-preserving text allocation/mutation.

`pptx/shapes.py`
- geometry, group recursion, titles/placeholders and unknown shapes.

`pptx/resources.py`
- picture/media/resource discovery and digests;
- alt text and relationship metadata.

`pptx/patch.py`
- typed edit validation and per-slide XML mutation.

`pptx/writer.py`
- public writer/helper orchestration and fidelity result.

`pptx/verify.py`
- member preservation, reopen, locator and semantic readback checks.

## 5. Optional dependency boundary

Phase C format code is optional.

Importing:

```python
import markitdown.twoways
```

must **not** import `pptx` or `lxml`.

PPTX APIs live at:

```python
from markitdown.twoways.formats.pptx import ...
```

If the `pptx` feature is absent, using the PPTX reader/writer raises a typed missing-dependency error at the operation boundary rather than breaking base package import.

The `pptx` optional dependency becomes conceptually:

```toml
pptx = ["python-pptx", "lxml"]
```

No Node.js, LibreOffice or cloud service is required by Phase C.

## 6. Public API

Phase C introduces format-specific public contracts without adding them to the root `markitdown.twoways.__all__`.

```python
@dataclass(frozen=True)
class PptxReadOptions:
    include_notes: bool = True
    include_resources: bool = True
    preserve_unknown_native: bool = True
    limits: OOXMLPackageLimits = OOXMLPackageLimits()


@dataclass(frozen=True)
class PptxPatchOptions:
    strict: bool = True
    verify_output: bool = True
    preserve_zip_metadata: bool = True
    limits: OOXMLPackageLimits = OOXMLPackageLimits()


class PptxIRReader(DocumentIRReader): ...
class PptxPatchWriter(DocumentWriter): ...


def read_pptx_ir(
    file_stream: BinaryIO,
    stream_info: StreamInfo | None = None,
    *,
    options: PptxReadOptions | None = None,
) -> DocumentIR: ...


def patch_pptx(
    document: DocumentIR,
    source_stream: BinaryIO,
    output: BinaryIO,
    *,
    edits: Sequence[EditOperation],
    options: PptxPatchOptions | None = None,
) -> WriterResult: ...
```

`edits` is explicit. `patch_pptx()` never implicitly applies `document.edits`, because that field may represent history rather than pending operations.

`PptxPatchWriter.write()` follows the existing `DocumentWriter` protocol and requires `source_stream` and explicit `edits` through keyword arguments.

## 7. Source authority and package identity

The original PPTX remains required for patch mode.

Reader populates:

```text
DocumentIR.source.format = "pptx"
DocumentIR.source.sha256 = SHA-256(original PPTX bytes)
DocumentIR.source.size_bytes = original byte length
DocumentIR.source.preserved_source_ref = "pptx:sha256:<digest>"
```

The IR never embeds the source archive bytes.

Patch mode requires the caller to provide `source_stream` again. Before any mutation it hashes that source and verifies equality with `DocumentIR.source.sha256`.

Mismatch raises `SourcePackageMismatchError` before a target locator is trusted.

This makes a stale IR + newer PPTX combination fail closed instead of patching the wrong deck.

## 8. OPC package snapshot

`OOXMLPackageSnapshot` is runtime state, not canonical IR.

Conceptual fields:

```text
source_sha256
source_size
entries (ordered)
content_types
package_relationships
```

Each entry records:

```text
name
uncompressed_sha256
uncompressed_size
compressed_size
compression_method
crc
zip metadata required for best-effort metadata preservation
```

Package paths are normalized to slash-separated relative OPC names.

Reject:

- duplicate member names;
- absolute paths;
- `..` traversal components;
- malformed ZIPs;
- encrypted members in Phase C v1;
- entries/packages exceeding configured limits.

No ZIP member is extracted to a path supplied by the archive.

## 9. What “preserve” means

The engine distinguishes three levels explicitly.

### 9.1 Exact archive preservation

If `edits` is empty, `patch_pptx()` copies the original source stream unchanged when possible.

Expected:

```text
SHA256(output.pptx) == SHA256(input.pptx)
```

### 9.2 Untouched member-content preservation

When edits exist, the ZIP container may necessarily be rewritten/recompressed.

For every package member not in the explicit touched-part set:

```text
SHA256(uncompressed output member bytes)
==
SHA256(uncompressed input member bytes)
```

The implementation does **not** claim whole-archive byte equality after an intentional edit.

### 9.3 Semantic/native preservation

Verification also checks:

- part inventory is unchanged in Phase C v1;
- relationship inventory is unchanged for text/alt-text edits;
- touched native locators still resolve;
- requested semantic values read back correctly;
- unrelated IR nodes remain semantically equal.

## 10. Safe XML handling

Only explicitly touched XML parts are parsed for mutation.

The XML parser is configured with:

```text
resolve_entities = false
load_dtd = false
no_network = true
huge_tree = false
```

External relationship targets are inert strings and are never fetched.

Serialization uses controlled namespace handling. Tests compare semantic XML and preservation invariants rather than relying on source attribute order for touched parts.

OOXML schema child order is respected when Phase C inserts anything. Phase C v1 primarily edits attributes/text nodes and avoids adding new DrawingML property structures unless a test proves the exact schema order.

## 11. Slide identity

Every slide canvas records a PPTX native locator.

Initial fields:

```text
backend = "pptx-ooxml"
part_uri = "/ppt/slides/slideN.xml"
creation_id = slide p14:creationId when present
relationship_id = presentation -> slide rId when available
attributes.slide_index = zero-based logical index
```

Slide creation IDs are additional identity evidence, not a replacement for source digest and part URI.

## 12. Shape identity

Shape locators bind identity **inside a specific slide part**.

Evidence priority:

1. exact `part_uri` — mandatory in strict patch mode;
2. `a16:creationId` when present;
3. `p:cNvPr@id` / `shape.shape_id`;
4. name/path only as diagnostic/fallback evidence.

Conceptual locator:

```text
backend = "pptx-ooxml"
part_uri = "/ppt/slides/slide3.xml"
object_id = "17"
creation_id = "{GUID}" | None
name = "Revenue callout"
path = "/p:sld/p:cSld/p:spTree/..."
attributes = {
  "slide_index": 2,
  "shape_type": ...,
  "z_order": ...
}
```

A drawing `creationId` is not treated as globally unique across the deck. It is always resolved together with `part_uri`.

Strict resolution rules:

- if a locator supplies `creation_id`, exactly one matching shape in the designated part must exist;
- otherwise `object_id` must resolve uniquely inside that part;
- if both are present, they must identify the same shape;
- name alone never authorizes a strict patch;
- ambiguity raises `AmbiguousNativeLocatorError`.

## 13. Deterministic node identity

PPTX IR node ids are derived deterministically from stable native evidence.

Preferred material:

```text
source document identity seed
slide part URI
shape creationId when present, otherwise cNvPr id
node kind
```

Changing text must not change `node_id`.

Run ids/locators similarly use shape identity plus paragraph/run ordinal and raw XML path evidence.

## 14. Slide and shape traversal

A slide becomes `Canvas(kind="slide")` with presentation slide width/height in EMU.

The reader stores two orders:

- `metadata["pptx:z_order"]` from native shape sequence;
- projection/root order optimized for deterministic human reading, using geometry (`top`, then `left`) while preserving stable tie-breaking by z-order/native id.

Group shapes become `Node(kind="group")`; child nodes retain native group ordering and local geometry evidence.

Reading order is never used as native identity.

## 15. Geometry

PPTX geometry is preserved using `Geometry(unit="emu")`.

Read:

```text
x = shape.left
y = shape.top
width = shape.width
height = shape.height
rotation = shape.rotation
```

Source-native integer EMU values are retained in `source_values` to avoid repeated conversion loss.

Off-canvas coordinates remain legal.

## 16. Text extraction

A text-bearing shape becomes a `text` node or a shape node with a text payload according to structural needs.

`TextPayload` preserves:

- normalized convenience text;
- ordered paragraphs;
- ordered runs;
- paragraph list level/alignment metadata;
- direct run formatting where explicitly present;
- hyperlinks/unsupported run properties via native metadata/payload references.

Direct style extraction must not materialize inherited theme values as direct formatting.

Each text node records whether its native text structure is patch-compatible in Phase C v1.

## 17. Patch-compatible text definition

Phase C v1 can patch a text node only when all of these hold:

- target shape/notes shape resolves uniquely;
- text is represented by ordinary DrawingML paragraphs/runs;
- each semantic text segment can be mapped to `<a:t>` nodes deterministically;
- no unsupported field element requires semantic regeneration;
- no structural newline/paragraph-count change is requested;
- preconditions match.

Unsupported structures may still be read and projected, but the PPTX writer returns `UnsupportedEditError` instead of flattening them.

This is capability negotiation, not data loss.

## 18. Shared semantic preconditions

Phase B currently creates semantic/native-locator digests for edit preconditions. Phase C must verify the same definitions without creating a dependency from PPTX code to the Markdown subsystem.

Before PPTX writer implementation, move the format-agnostic helpers into a Core IR semantic module, conceptually:

```text
markitdown/twoways/ir/semantics.py
```

Stable helpers:

```python
node_semantic_text(node) -> str
node_semantic_digest(node) -> str
native_locator_digest(node) -> str | None
```

Phase B imports the shared helpers and regression tests prove digest values do not change during the refactor.

PPTX patch precondition checks use exactly those helpers.

## 19. Text patch algorithm

Assigning to `shape.text` or clearing a text frame is forbidden in patch mode because it destroys run structure.

Phase C operates on existing `<a:t>` nodes.

### 19.1 Paragraph boundary rule

The old and new semantic text are split by paragraph boundaries.

Phase C v1 requires the same number of paragraphs. Adding/removing a paragraph is reported unsupported until a later phase explicitly models paragraph creation and inheritance.

### 19.2 Run-preserving character diff

For each paragraph:

1. concatenate existing run text;
2. map every old character position to its source run;
3. use deterministic sequence diff with `autojunk=False`;
4. unchanged spans remain assigned to their original runs;
5. deleted characters disappear from their owning runs;
6. inserted/replacement characters inherit the nearest deterministic style context:
   - run immediately left of insertion when available;
   - otherwise run immediately right;
   - if neither exists, the paragraph is not v1 patch-compatible;
7. write resulting strings back to the same existing `<a:t>` elements;
8. do not delete/reorder run property nodes.

This preserves run count and `<a:rPr>` structures while allowing ordinary wording edits across bold/italic boundaries.

### 19.3 XML whitespace

When an `<a:t>` value begins or ends with whitespace, the writer ensures the XML whitespace-preservation attribute required for round-trip text is present. When not needed, it avoids introducing unrelated whitespace attributes.

### 19.4 Formatting boundary evidence

Verification records whether inserted/replaced characters inherited style from a neighboring run. This does not fail a valid edit, but it prevents overstating fidelity.

## 20. `replace_text` preconditions

Before mutating:

- target node exists;
- target kind/payload supports text;
- `expected_semantic_digest`, when supplied, equals current node semantic digest;
- `expected_native_locator_digest`, when supplied, equals current locator digest;
- `expected_old_value`, when supplied, equals current semantic text;
- native locator resolves to the same source shape.

Mismatch raises `PatchPreconditionError` before XML output is produced.

## 21. `set_alt_text`

Picture alt text is bound to the native non-visual drawing properties (`cNvPr`).

Phase C v1 updates only the description/alt-text attribute corresponding to the IR image alt text.

It does not:

- replace media bytes;
- change image relationships;
- rename the shape;
- alter crop/effects;
- synthesize LLM captions.

Changing an image resource remains unsupported in Phase C v1.

## 22. Pictures and resources in the reader

Picture nodes include:

- `ImagePayload.resource_id`;
- alt text;
- original dimensions/crop when reliably available;
- native shape locator.

`Resource` records:

```text
sha256
content_type
filename
size_bytes
storage_ref = package part URI / relationship reference
```

Reader supports native image relationships including the SVG-extension case already encountered by upstream MarkItDown. Unsupported picture variants remain representable as `unknown_native` rather than being dropped.

## 23. Tables

Tables are read into `TablePayload` where structure can be represented.

Reader records row/column spans and cell text when available.

The table shape also retains native locator/payload evidence.

Table mutation is **read-only in Phase C v1** even if Phase B can display a simple table. No table edit is silently converted to a shape rebuild.

## 24. Charts

Charts produce a semantic `ChartPayload` when `python-pptx` exposes categories/series safely.

The chart's native relationship/part references remain preservation evidence.

Chart mutation is read-only in Phase C v1.

Unsupported chart families create diagnostics plus native preservation hooks rather than an empty destructive representation.

## 25. Notes

Notes are represented as note/text nodes associated with their source slide.

Reader stores native notes part/shape locators.

`replace_text` may be supported when the note's DrawingML text structure meets the same patch-compatibility rules as ordinary text shapes. Otherwise it is read-only with an explicit capability diagnostic.

## 26. Unknown native content

Every unsupported shape/content class follows:

```text
unsupported != disposable
```

Create `Node(kind="unknown_native")` with:

- native locator;
- compact summary/type metadata;
- `NativePayload.storage_ref` pointing into the preserved source package;
- no executable payload evaluation.

Because patch mode starts from the original PPTX and touches only explicit parts/elements, unknown content survives without the common IR having to understand it.

## 27. Package mutation set

For Phase C v1 `replace_text` and `set_alt_text`, the expected mutation set is normally only the slide or notes XML part containing the target shape.

Relationships, themes, masters, layouts, charts, media and content-types must remain untouched.

If an operation would require a relationship/content-type/resource mutation, v1 reports unsupported rather than widening the mutation set implicitly.

## 28. Writer transaction model

Patch output is transactional from the caller's perspective.

Sequence:

```text
validate IR
  ↓
hash + validate source package
  ↓
validate all edit preconditions
  ↓
resolve all native locators
  ↓
compute in-memory part overrides
  ↓
verify mutation-set policy
  ↓
write output package
  ↓
post-write verification
  ↓
return WriterResult
```

No output bytes are considered successful until all requested edits and preservation checks pass.

For a seekable destination, failed verification may truncate/reset output when practical. API documentation still tells callers to treat output as invalid when an exception is raised.

## 29. Post-write verification

When `verify_output=True`, perform all applicable checks.

### Package checks

- output is a valid ZIP/OPC package;
- package member inventory equals input inventory;
- untouched member content digests match exactly;
- only declared touched parts differ;
- relationship inventory is unchanged for Phase C v1 operations.

### `python-pptx` reopen check

Open the generated presentation with `pptx.Presentation`.

Failure raises `RoundTripVerificationError`.

### Native locator checks

Every edited target must still resolve by strict native locator policy.

### Semantic readback

Reread the generated PPTX into `DocumentIR` and verify:

- target text/alt text equals requested edit;
- unrelated nodes that can be correlated by locator retain their previous semantic digest;
- source-native unsupported content inventory has not disappeared.

## 30. Fidelity report

Phase C returns evidence rather than a vague success flag.

Typical successful text patch:

```text
claimed tier: high

PASS source_package_digest
PASS target_locator_resolved
PASS edit_precondition
PASS member_inventory_preserved
PASS untouched_member_content_digests
PASS relationship_inventory_preserved
PASS output_reopened
PASS requested_semantic_readback
PASS unrelated_semantic_readback
INFO inserted_text_style_context (when applicable)
```

No-op exact byte copy may claim `exact-preserve` when source/output archive digests match.

An intentional content edit normally claims `high`, not `exact-preserve`.

## 31. Errors

Reuse existing Phase A errors where semantics already fit:

- `SourcePackageMismatchError`
- `AmbiguousNativeLocatorError`
- `PatchPreconditionError`
- `UnsupportedEditError`
- `RoundTripVerificationError`

Add PPTX/package-specific subclasses only for stable concerns not represented above, for example:

```text
OOXMLPackageError
OOXMLPackageLimitError
PptxReadError
PptxPatchError
PptxLocatorError
```

All errors expose stable `code` and structured details.

## 32. Security limits

`OOXMLPackageLimits` includes finite defaults for:

```text
max_member_count
max_member_uncompressed_bytes
max_total_uncompressed_bytes
max_compression_ratio
max_xml_part_bytes
```

Reader/writer rejects package bombs before materializing unbounded content.

No external relationship URI is fetched.

No embedded OLE object, macro, script or media payload is executed.

Phase C accepts `.pptx`; macro-enabled `.pptm` is not automatically treated as equivalent unless a future phase explicitly preserves/tests VBA package semantics.

## 33. Determinism

Given identical source bytes, options and edits:

- generated IR ids/locators/digests are deterministic;
- touched XML semantic output is deterministic;
- edit resolution order is deterministic;
- verification evidence ordering is deterministic.

ZIP timestamps must not be replaced with current time. Existing entry metadata is copied where supported.

Whole edited archive bytes are not promised identical across unrelated ZIP implementations; member-content and semantic determinism are the contract.

## 34. No-op round trip

The most important preservation baseline is:

```python
document = read_pptx_ir(source)
patch_pptx(document, source_again, output, edits=())
```

Expected output is byte-identical to source when the source stream can be copied directly.

This test prevents the writer from accidentally becoming a whole-document regenerator.

## 35. Required golden PPTX corpus

Phase C creates small programmatic/generated test decks covering:

- one title + plain text shape;
- multi-run bold/italic text;
- multiple paragraphs;
- grouped shapes;
- image with alt text;
- SVG picture relationship when fixture support permits;
- simple table;
- chart;
- speaker notes;
- shape with `a16:creationId`;
- shape without `a16:creationId` to test `cNvPr@id` fallback;
- duplicated names;
- unsupported/native shape retained as opaque evidence.

Fixtures should be generated where practical so licensing/provenance is clear.

## 36. Reader tests

Verify:

- source SHA and preservation ref;
- slide canvases and dimensions;
- deterministic IDs;
- shape geometry;
- title semantic role;
- paragraph/run text and direct bold/italic;
- group hierarchy;
- image resource digest/alt text;
- simple table/chart semantics;
- notes;
- unknown native preservation;
- creationId + shape-id locator fields;
- repeated reads produce semantically equal canonical IR.

## 37. Package tests

Verify:

- valid PPTX inventory;
- duplicate ZIP member rejection;
- traversal/absolute path rejection;
- configured size/ratio limits;
- relationship parsing with internal/external targets as inert data;
- untouched member content copy;
- sparse part override writes;
- no-op source byte copy.

## 38. Locator tests

Verify strict resolution:

- creationId wins within designated slide part;
- creationId and object id must agree when both supplied;
- object-id fallback works when creationId absent;
- duplicate/ambiguous creationId in one slide fails;
- same shape creationId on different slides does not collide;
- duplicate names do not authorize ambiguous patching;
- wrong slide part never falls through to another slide.

## 39. Text patch tests

RED/GREEN cases include:

- replace one word in a single run;
- insert text inside a bold run;
- replace text spanning plain + bold runs while preserving existing run properties;
- delete text spanning runs;
- insertion at run boundary has deterministic style inheritance;
- leading/trailing spaces preserve XML text whitespace;
- hyperlink/run property nodes survive;
- paragraph count change fails unsupported;
- field/unsupported text structure fails unsupported;
- stale semantic digest fails precondition;
- stale locator digest fails precondition;
- stale source package fails before locator resolution.

## 40. Alt-text patch tests

Verify:

- description changes;
- shape name unchanged;
- media relationship unchanged;
- media blob digest unchanged;
- all unrelated slide XML semantically unchanged;
- stale precondition fails closed.

## 41. Preservation tests

For one text edit:

- exactly one expected slide XML part differs;
- every media/theme/master/layout/chart member content digest is identical;
- relationship files are identical;
- package inventory identical;
- output reopens;
- target edit reads back;
- unrelated nodes retain semantic digests.

For two edits on two slides:

- touched set contains exactly those two slide parts.

## 42. Existing upstream regression gate

Existing one-way PPTX tests, including SVG and `None`-text cases, run unchanged.

Phase C does not modify `_pptx_converter.py` unless a later focused refactor explicitly proves behavior parity first.

All existing MarkItDown tests must remain green.

## 43. Type/import gates

- Python 3.10–3.13 syntax support remains required.
- mypy runs under the existing repository configuration.
- root `markitdown.twoways` import remains lightweight without PPTX extras.
- PPTX-specific tests are skipped with a clear reason when optional PPTX dependencies are absent; repository `hatch test` installs `all` and therefore runs them.

## 44. Explicit non-goals for Phase C

Not included yet:

- synthetic/rebuild PPTX generation from arbitrary Markdown;
- add/remove/reorder slides;
- add/remove arbitrary shapes;
- table edits;
- chart edits;
- image byte replacement;
- master/layout/theme editing;
- animations/transitions editing;
- SmartArt semantic editing;
- embedded OLE mutation;
- macro/VBA mutation;
- arbitrary paragraph structure creation;
- automatic fallback from patch mode to rebuild mode.

These remain future writer capabilities and must never be inferred from a Phase C patch failure.

## 45. Phase C completion gate

Phase C is complete only when all are true:

1. a native PPTX can be read into validated deterministic `DocumentIR`;
2. source package SHA and native locators are recorded;
3. no-op patch returns byte-identical source output;
4. a supported `replace_text` edit changes only the expected slide/notes part;
5. existing run properties survive supported rich-text edits;
6. a supported `set_alt_text` changes no media/relationship content;
7. stale source/semantic/locator preconditions fail closed;
8. unknown/unsupported native content survives patching;
9. untouched package member content digests remain identical;
10. output reopens with `python-pptx`;
11. semantic readback proves requested edits and unrelated-node preservation;
12. existing one-way MarkItDown behavior/tests remain unchanged;
13. full Phase A+B+C focused tests pass;
14. repository type/CI gates pass when GitHub Actions evidence is available.

## 46. What Phase D may assume

After Phase C is green, the project has a trustworthy preservation path for editing existing PPTX files.

Phase D may then add a separate **rebuild/synthesis writer** for cases where there is no original PPTX or the requested operation intentionally creates/restructures content.

The important separation remains permanent:

```text
PATCH = preserve original native document and mutate minimally
REBUILD = synthesize a new document from IR
```

A caller always knows which mode was used.