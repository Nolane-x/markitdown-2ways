# MarkItDown 2Ways — Phase B Markdown Round-Trip Bridge Design

**Date:** 2026-09-08  
**Status:** Design ready for user review  
**Parent:** `2026-09-08-markitdown-2ways-phase-a-core-ir-design.md`  
**Branch:** `nolane/2way-document-ir-v0`

## 1. Objective

Phase B creates the reversible bridge between the Phase A `DocumentIR` and Markdown used by humans/LLMs.

It adds four capabilities:

1. **Clean Markdown projection** — readable, token-efficient Markdown with no round-trip machinery exposed.
2. **Identity Markdown projection** — readable Markdown plus deterministic invisible identity markers.
3. **Conservative Markdown re-import** — compare edited identity Markdown against the originating IR and produce typed `EditOperation` objects.
4. **Semantic Markdown reader** — create a new `DocumentIR` from ordinary Markdown for rebuild/generation workflows where no original rich document exists.

Phase B does **not** write PPTX/DOCX. It prepares edits that later native writers can apply.

## 2. Why Markdown must remain a projection

Markdown cannot represent all information in Office/PDF documents: geometry, theme inheritance, shape identity, chart internals, native relationships, animations, masters, merged-table semantics, and arbitrary OOXML extensions.

Therefore:

```text
DocumentIR ──► Markdown projection ──► human / AI edit
    ▲                                  │
    └──────── typed EditOperations ◄───┘
```

The edited Markdown is **not** promoted to canonical truth. The canonical source remains the original `DocumentIR` plus typed edits.

This preserves the Phase A rule that unknown/native information must survive even when Markdown cannot express it.

## 3. Approaches considered

### A. Inline identity comments only

Example:

```md
<!-- m2w:node id="n12" -->
Revenue increased 38%.
```

Advantages:

- one portable file;
- easy for LLMs to preserve;
- comments are invisible in normal Markdown rendering.

Weaknesses:

- comments can be deleted, duplicated, or moved;
- no strong binding to the originating document by themselves;
- difficult to prove whether an apparently valid marker belongs to stale content.

### B. Sidecar manifest only

Keep clean Markdown plus a separate offset/range map.

Advantages:

- completely clean Markdown;
- metadata can be arbitrarily rich.

Weaknesses:

- ordinary text edits invalidate offsets quickly;
- Markdown and sidecar can become separated;
- poor copy/paste and LLM workflow ergonomics.

### C. Hybrid markers + projection manifest — selected

The selected design combines:

- small inline markers for stable local identity;
- a deterministic in-memory/serializable projection manifest with source digests and block records.

This gives readable Markdown while allowing the importer to fail closed when markers are stale, duplicated, missing, or reassigned.

The manifest is a derived artifact, not part of canonical `DocumentIR` schema `0.1.0`.

## 4. Module boundaries

New Phase B code lives under:

```text
markitdown/twoways/markdown/
  __init__.py
  model.py
  projection.py
  rendering.py
  identity.py
  importer.py
  semantic_reader.py
```

Responsibilities:

- `model.py` — projection mode/options/result, manifest and block-record dataclasses.
- `projection.py` — orchestrates deterministic IR traversal and projection.
- `rendering.py` — node-kind-specific clean Markdown rendering.
- `identity.py` — marker grammar, encoder/parser, marker validation.
- `importer.py` — parses edited identity Markdown and produces typed edits.
- `semantic_reader.py` — ordinary Markdown → fresh semantic `DocumentIR` for rebuild use.

No format-specific Office dependency is allowed in these modules.

## 5. Public API

Phase B adds the following stable APIs to `markitdown.twoways`:

```python
class MarkdownProjectionMode(str, Enum):
    CLEAN = "clean"
    IDENTITY = "identity"

@dataclass(frozen=True)
class MarkdownProjectionOptions:
    mode: MarkdownProjectionMode = MarkdownProjectionMode.CLEAN
    include_document_title: bool = True
    include_notes: bool = True
    include_unknown_placeholders: bool = False
    resource_uri_scheme: str = "m2w-resource"

@dataclass(frozen=True)
class MarkdownProjection:
    markdown: str
    manifest: ProjectionManifest


def project_markdown(
    document: DocumentIR,
    *,
    options: MarkdownProjectionOptions | None = None,
) -> MarkdownProjection: ...


def import_identity_markdown(
    edited_markdown: str,
    *,
    original_document: DocumentIR,
    manifest: ProjectionManifest,
    strict: bool = True,
) -> tuple[EditOperation, ...]: ...


def read_markdown_ir(
    markdown: str,
    *,
    document_id: str | None = None,
    source_name: str | None = None,
) -> DocumentIR: ...
```

The manifest is returned in both clean and identity modes so callers can inspect projection coverage and diagnostics. Only identity mode is eligible for reliable re-import.

## 6. Projection manifest

`ProjectionManifest` is deterministic and serializable independently from the IR.

Conceptual contract:

```python
@dataclass(frozen=True)
class ProjectionManifest:
    format_version: str
    document_id: str
    document_schema_version: str
    source_document_digest: str
    projection_mode: str
    blocks: tuple[ProjectionBlock, ...]
    diagnostics: tuple[ProjectionDiagnostic, ...]
```

Initial format version:

`1`

`ProjectionBlock`:

```text
projection_id
node_id
canvas_id
node_kind
semantic_role
ordinal
source_semantic_digest
native_locator_digest
editable_capabilities
rendered_digest
```

`projection_id` is deterministic from document id, node id and ordinal. No UUID, time, filesystem path or environment value is used.

The manifest never stores native binary data.

## 7. Identity marker grammar

Markers are one-line HTML comments so standard Markdown renderers hide them.

Document header:

```md
<!-- m2w:projection v="1" doc="doc1" base="sha256:<digest>" -->
```

Block marker:

```md
<!-- m2w:block pid="p_ab12" node="text7" kind="text" src="sha256:<semantic-digest>" -->
```

Rules:

- marker keys are ASCII lowercase;
- values are quoted and escaped by one canonical encoder;
- one physical line only;
- unknown marker keys are rejected in strict mode and preserved as diagnostics in permissive mode;
- duplicate keys are invalid;
- duplicate `pid` or `node` assignments are invalid for independently editable blocks;
- malformed `m2w:` comments are errors, not silently treated as user prose;
- ordinary unrelated HTML comments remain ordinary Markdown content.

The importer does not trust node ids merely because they appear in a marker. It verifies them against the supplied manifest and original document.

## 8. Source semantic digests

Each independently editable projected block gets a semantic digest.

The digest is computed from a canonical semantic view rather than raw Markdown formatting.

For text nodes, initial digest material is:

```text
node kind
semantic role
normalized text payload
ordered paragraph/run textual content
```

It intentionally excludes geometry and presentation style so harmless layout/style differences do not invalidate a text edit workflow.

Native locator digest is stored separately in the manifest and can later be transferred into `EditPrecondition.expected_native_locator_digest` for PPTX patch writers.

## 9. Deterministic traversal

Projection order must never depend on mapping iteration.

Traversal order:

1. canvases by explicit `Canvas.index`;
2. each canvas's `root_node_ids` order;
3. children in each node's explicit `children` order;
4. document-level roots not already reached, in `root_node_ids` order;
5. orphan/non-rendered nodes do not silently appear; they generate projection diagnostics.

A visited set prevents accidental duplicate rendering when malformed data is supplied, but Phase A validation runs before projection and invalid graphs fail before rendering.

## 10. Rendering model by node kind

### 10.1 Text

Text is the primary editable Phase B content.

Semantic roles map to Markdown when known:

- title → `#`
- section headings → appropriate `##`…`######`
- list semantic data → Markdown list syntax when structurally representable
- ordinary text → paragraphs
- code-like role → fenced code block only when explicitly declared; never infer code solely from punctuation.

Rich formatting in runs is projected conservatively:

- bold → `**...**`
- italic → `*...*`
- code → backticks when explicitly represented

Unsupported typography is omitted from clean Markdown but preserved in IR.

### 10.2 Notes

Notes are rendered when enabled:

```md
### Notes

...
```

In identity mode notes receive their own block marker and may support `replace_text`.

### 10.3 Images

Images render as:

```md
![alt text](m2w-resource:<resource_id>)
```

No local path is invented.

Initial identity import capability is `set_alt_text` only. Changing the resource URI is not accepted as `replace_resource` in Phase B v1 because arbitrary replacement bytes/resources are not carried in Markdown.

### 10.4 Tables

If the table is rectangular with no row/column spans and cells can be represented as plain text, render a GitHub-style Markdown table.

If fidelity would be lost (merged cells, nested nodes, rich cell structure), render a readable HTML table or a compact placeholder according to projection options and add a manifest diagnostic.

Phase B v1 treats the table as non-editable unless a future cell-identity representation is explicitly added. It must never pretend a lossy Markdown table can safely round-trip complex native table structure.

### 10.5 Charts

Render a semantic summary when available:

```md
### Chart: Revenue

- Q1: 10
- Q2: 14
```

Chart projections are read-only in Phase B v1.

### 10.6 Group

Groups are structural containers. They emit no wrapper text by default; children render in order.

### 10.7 Shape

A shape with meaningful textual child/content delegates to that text representation. Decorative shape-only information is not emitted.

### 10.8 Unknown native

Clean mode omits it by default.

Identity mode may emit a non-editable invisible marker plus optional readable placeholder when `include_unknown_placeholders=True`.

Unknown-native content is never converted into a destructive removal simply because Markdown cannot display it.

## 11. Projection normalization

The renderer owns one canonical textual normalization policy:

- internal newline: `\n`;
- no trailing spaces;
- maximum two consecutive blank lines between blocks;
- final document ends with exactly one newline unless empty;
- Unicode is preserved, not ASCII-escaped;
- user text containing strings resembling `m2w:` comments is escaped/handled so it cannot impersonate engine markers.

This normalization is deterministic across Python hash seeds.

## 12. Importer trust model

`import_identity_markdown` requires all three:

1. edited identity Markdown;
2. the original `DocumentIR`;
3. its matching `ProjectionManifest`.

It verifies before producing edits:

- header format version supported;
- header `doc` matches original document id;
- source document digest matches the supplied original IR;
- manifest's source digest matches original IR;
- each marker exists in manifest;
- marker node id/kind/digest matches its manifest block;
- no duplicate projection id;
- no illegal reuse of node id;
- editable capabilities authorize the detected edit type.

A mismatch fails closed in strict mode.

## 13. Block extraction

A block begins immediately after an `m2w:block` marker and extends until the next recognized engine block marker or end of projection.

Document header is not part of user-editable text.

The importer compares **semantic parsed content**, not raw byte text, so harmless Markdown normalization does not necessarily become an edit.

Examples that should not create a text edit when semantics are unchanged:

- one vs two blank lines around the paragraph;
- final newline changes;
- canonical equivalent Markdown emitted by the parser.

Changes in actual text do create edits.

## 14. Typed edit generation

### 14.1 Replace text

For an editable text/note block whose semantic text changed:

```python
EditOperation(
    operation_id=<deterministic id>,
    type="replace_text",
    target_node_id=<node id>,
    precondition=EditPrecondition(
        expected_semantic_digest=<source digest>,
        expected_native_locator_digest=<locator digest or None>,
        expected_old_value=<old semantic text>,
    ),
    payload={"text": <new semantic text>},
    source_label="markdown.identity.v1",
)
```

Operation ids are deterministic from projection id, edit type and resulting semantic digest.

### 14.2 Image alt text

Changed image alt text generates `set_alt_text` with expected old alt text.

### 14.3 No implicit remove

Deleting an entire marked block does **not** automatically mean `remove_node` in Phase B v1.

A missing block is ambiguous: the marker may have been accidentally deleted. Strict mode raises an import integrity error. Explicit node removal needs a future deliberate syntax/operation affordance.

### 14.4 No implicit add

Unmarked prose inserted between known blocks is not silently attached to a random node.

In strict identity import it is reported as unanchored content and fails if semantically substantive.

Adding new nodes belongs either to semantic Markdown rebuild mode or a future explicit identity add-block syntax.

## 15. Import result and diagnostics

Rather than returning only edits internally, the importer uses:

```python
@dataclass(frozen=True)
class MarkdownImportResult:
    edits: tuple[EditOperation, ...]
    unchanged_node_ids: tuple[str, ...]
    diagnostics: tuple[MarkdownImportDiagnostic, ...]
```

The public convenience function may return the result object directly; the earlier tuple-only signature is superseded by this richer contract.

Diagnostics carry stable codes, severity, projection/node id, and structured details. No timestamp is generated.

Initial failure/diagnostic codes include:

```text
markdown.marker.malformed
markdown.marker.duplicate_projection_id
markdown.marker.duplicate_node
markdown.marker.unknown_projection_id
markdown.marker.metadata_mismatch
markdown.header.missing
markdown.header.document_mismatch
markdown.header.source_digest_mismatch
markdown.block.missing
markdown.block.unanchored_content
markdown.edit.unsupported
markdown.edit.read_only
markdown.semantic.parse_error
```

Integrity failures use typed `TwoWayError` subclasses rather than generic `ValueError`.

## 16. New error types

Phase B adds:

```text
MarkdownProjectionError
MarkdownImportError
MarkdownIdentityError
MarkdownSemanticParseError
```

All inherit `TwoWayError`, expose stable codes, and carry structured details.

Existing Phase A error types remain unchanged.

## 17. Semantic Markdown reader

`read_markdown_ir()` is deliberately separate from identity import.

Identity import asks:

> What changed relative to this existing rich document?

Semantic Markdown reader asks:

> Build a new semantic document from this Markdown.

It creates a fresh flow-oriented `DocumentIR`:

```text
DocumentIR
  source.format = markdown
  Canvas(kind="flow")
  nodes = headings / paragraphs / lists / code / images / simple tables
```

It does not invent physical geometry.

Node ids are deterministic from caller-supplied document identity plus structural position/content. If no reproducible identity is supplied, Phase A's non-reproducible id path is used and diagnostics record that fact.

## 18. Markdown parsing strategy

Phase B should avoid introducing a heavy mandatory Markdown parser unless tests demonstrate a need.

Selected implementation strategy:

- identity marker scanning uses a dedicated strict line parser;
- engine-emitted Markdown is parsed by a small deterministic parser covering the exact subset the renderer itself emits;
- semantic reader initially supports a conservative CommonMark-like subset;
- HTML/table support may use existing MarkItDown dependencies only if already mandatory and dependency direction remains clean.

The important invariant is: the importer must parse everything the identity renderer emits. It does not need to interpret every Markdown extension on earth in Phase B.

Unsupported constructs produce diagnostics or semantic-reader fallback text rather than corrupt structure.

## 19. Security and robustness

Markdown is untrusted input.

Phase B performs no:

- network fetch;
- local file read from Markdown links;
- script execution;
- HTML execution;
- data URI decoding into arbitrary memory blobs;
- plugin invocation as a side effect of identity import.

Links and HTML are inert text/data at this stage.

Size/complexity guards should exist for:

- marker count;
- maximum marker line length;
- maximum total Markdown bytes accepted by identity importer when caller provides a configured limit;
- pathological nesting in the semantic reader.

Defaults must be generous enough for real documents but deterministic and configurable.

## 20. Fidelity model

Projection fidelity is reported separately from writer fidelity.

Suggested projection tiers:

```text
semantic-complete
semantic-partial
readable-only
```

Examples:

- pure text document → semantic-complete;
- complex PPTX table/chart rendered as summaries → semantic-partial;
- unknown native object with no semantic projection → readable-only for that block/diagnostic.

Projection fidelity never claims that Markdown preserves visual/layout fidelity.

## 21. Determinism requirements

For the same valid IR and options:

```text
project_markdown(ir).markdown
```

must be byte-identical across repeated runs and Python hash seeds.

The manifest canonical representation must also be byte-identical.

Identity import of the same edited Markdown, original IR and manifest must produce edit operations in the same order with identical deterministic operation ids.

No timestamps, random ids or environment paths.

## 22. Tests

Phase B adds focused tests under:

```text
packages/markitdown/tests/twoways/markdown/
```

Required categories:

### Clean projection

- title/paragraph/list/note rendering;
- image resource URI and alt text;
- simple table rendering;
- group traversal order;
- chart semantic summary;
- unknown-native omission/placeholder option;
- Unicode and escaping.

### Identity projection

- deterministic header and block markers;
- stable manifest records;
- marker grammar canonical encoding;
- user content cannot spoof engine markers;
- repeated projection byte equality;
- hash-seed determinism.

### Identity import

- unchanged Markdown → zero edits;
- text change → one `replace_text`;
- alt change → one `set_alt_text`;
- whitespace-only semantic no-op → zero edits;
- duplicate marker → fail closed;
- missing marker/block → fail closed;
- stale document digest → fail closed;
- marker/node mismatch → fail closed;
- substantive unanchored text → fail closed;
- read-only table/chart edit → fail closed;
- deterministic operation ids/order.

### Semantic reader

- headings and paragraphs become flow nodes;
- list order preserved;
- image remains an inert resource reference/link descriptor;
- no geometry invented;
- Unicode preserved;
- same seed/source yields deterministic ids.

### Regression gates

All Phase A tests remain unchanged and green.

## 23. Quality gates

Phase B is complete only when:

1. every Phase A focused test still passes unchanged;
2. all Phase B tests pass;
3. clean projection is deterministic;
4. identity projection + manifest are deterministic;
5. identity importer is fail-closed for stale/ambiguous markers;
6. unchanged identity Markdown produces no edits;
7. supported edits carry semantic/native preconditions;
8. importer performs no network/filesystem access;
9. public `markitdown.twoways` import remains lightweight;
10. no Office-specific dependency appears in Markdown modules;
11. Python 3.10 syntax/type compatibility is preserved;
12. GitHub full workflow matrix is reported separately from local focused verification and is never claimed green without run evidence.

## 24. Explicit Phase B non-goals

Phase B v1 does not:

- recreate PPTX/DOCX;
- apply native OOXML patches;
- round-trip geometry through Markdown;
- edit charts via Markdown;
- safely edit complex/merged tables;
- infer node deletion from a missing marker;
- infer node creation from unmarked prose;
- fetch linked images/files;
- execute embedded HTML;
- promise visual fidelity.

These restrictions are intentional because a reversible system must refuse ambiguous edits instead of inventing destructive meaning.

## 25. Phase C handoff

Once Phase B is green, PPTX-native work may rely on:

```text
PPTX reader
   ↓
DocumentIR
   ↓
identity Markdown
   ↓
AI/human edit
   ↓
MarkdownImportResult
   ↓
EditOperation + preconditions
   ↓
PPTX minimal-patch writer
```

Phase C therefore does not need to understand Markdown. It consumes typed edits against validated IR/native locators, keeping format-specific patch logic isolated from human/LLM text interaction.
