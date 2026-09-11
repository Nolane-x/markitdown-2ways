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

## 2. Why Markdown remains a projection

Markdown cannot represent all information in Office/PDF documents: geometry, theme inheritance, shape identity, chart internals, native relationships, animations, masters, merged-table semantics, and arbitrary OOXML extensions.

Therefore:

```text
DocumentIR ──► Markdown projection ──► human / AI edit
    ▲                                  │
    └──────── typed EditOperations ◄───┘
```

The edited Markdown is **not** promoted to canonical truth. The canonical state remains the original `DocumentIR` plus typed edits.

Unknown/native information therefore survives even when Markdown cannot express it.

## 3. Approaches considered

### A. Inline identity comments only

```md
<!-- m2w:node id="n12" -->
Revenue increased 38%.
```

Advantages: one portable file, invisible markers in rendered Markdown, good LLM ergonomics.

Weaknesses: markers can be deleted, duplicated, moved, or copied from stale projections; comments alone do not strongly bind the file to one source IR.

### B. Sidecar manifest only

Keep clean Markdown plus offsets/ranges in a separate file.

Advantages: completely clean Markdown and arbitrarily rich metadata.

Weaknesses: text edits invalidate offsets quickly; sidecar and Markdown can separate; copy/paste workflows are fragile.

### C. Hybrid markers + projection manifest — selected

The selected design combines small inline identity markers with a deterministic manifest carrying source/document/block digests.

This gives readable Markdown while allowing the importer to **fail closed** when identity evidence is stale, duplicated, missing, moved incorrectly, or inconsistent.

The manifest is a derived artifact, not part of canonical `DocumentIR` schema `0.1.0`.

## 4. Module boundaries

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

- `model.py` — projection options/results, manifest/block records, import results/diagnostics.
- `projection.py` — validates IR, traverses it deterministically, orchestrates rendering.
- `rendering.py` — node-kind-specific Markdown rendering and semantic block models.
- `identity.py` — canonical marker grammar, marker encoding/parsing and anti-spoofing rules.
- `importer.py` — validates edited identity Markdown and produces typed edits.
- `semantic_reader.py` — ordinary Markdown → fresh semantic `DocumentIR` for rebuild workflows.

No Office-format dependency is allowed in these modules.

## 5. Public API

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

@dataclass(frozen=True)
class MarkdownImportResult:
    edits: tuple[EditOperation, ...]
    unchanged_node_ids: tuple[str, ...]
    diagnostics: tuple[MarkdownImportDiagnostic, ...]


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
) -> MarkdownImportResult: ...


def projection_manifest_bytes(manifest: ProjectionManifest) -> bytes: ...

def projection_manifest_digest(manifest: ProjectionManifest) -> str: ...


def read_markdown_ir(
    markdown: str,
    *,
    document_id: str | None = None,
    source_name: str | None = None,
) -> DocumentIR: ...
```

The manifest is returned for both modes to expose projection coverage/diagnostics. **Only `IDENTITY` projections may be passed to `import_identity_markdown`; clean-mode manifests are rejected with `MarkdownIdentityError`.**

## 6. Projection manifest

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

Initial `format_version` is exactly `1`.

`ProjectionBlock` fields:

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

Digest fields inside dataclasses are lowercase 64-character SHA-256 hex strings. Marker text prefixes them with `sha256:` for human/debug clarity.

`projection_id` is deterministic from document id, node id and ordinal. No UUID, clock, environment path or hash-map ordering is used.

`projection_manifest_bytes()` uses deterministic UTF-8 JSON with sorted keys and stable separators, following the same determinism principles as Phase A canonical serialization.

The manifest never stores native binary data.

## 7. Identity marker grammar

Markers are one-line HTML comments so normal Markdown renderers hide engine metadata.

Document header:

```md
<!-- m2w:projection v="1" doc="doc1" base="sha256:<digest>" -->
```

Block marker:

```md
<!-- m2w:block pid="p_ab12" node="text7" kind="text" src="sha256:<semantic-digest>" -->
```

Rules:

- marker keys are lowercase ASCII;
- values are quoted and escaped by one canonical encoder;
- marker occupies exactly one physical line;
- unknown engine-marker keys are errors in strict mode and diagnostics in permissive mode;
- duplicate keys are invalid;
- duplicate `pid` is always invalid;
- independently editable nodes may have at most one editable projection block;
- malformed comments beginning with exact prefix `<!-- m2w:` are engine-integrity errors, never ordinary user comments;
- unrelated HTML comments remain ordinary content.

The importer never trusts a marker merely because its node id exists. It verifies marker → manifest → original IR consistency.

### 7.1 Anti-spoof escaping

User semantic text that contains a line which would begin with exact engine prefix `<!-- m2w:` is rendered with the leading `<` entity-escaped:

```md
&lt;!-- m2w:block ... -->
```

Normal Markdown rendering still presents the user's literal text, while the identity scanner cannot mistake it for an engine marker.

The importer reverses only this renderer-owned anti-spoof transform inside the semantic block parser; it does not globally decode arbitrary HTML.

## 8. Semantic and native digests

Every independently editable block receives `source_semantic_digest`.

For text/note nodes the initial semantic digest covers a canonical semantic view containing:

```text
node kind
semantic role
normalized plain text
ordered paragraph textual content
ordered run textual content
portable rich-text flags represented by Phase B renderer
```

Geometry and presentation-specific style are excluded.

A separate `native_locator_digest` is computed from the canonical Phase A `NativeLocator` representation when present. That digest is propagated to `EditPrecondition.expected_native_locator_digest` so future PPTX patch writers can verify they are changing the intended native object.

## 9. Deterministic traversal

Projection order must not depend on dictionary iteration.

Order:

1. canvases sorted by explicit `Canvas.index`;
2. each canvas's `root_node_ids` in stored order;
3. each node's `children` in stored order;
4. document-level roots not already reached, in `DocumentIR.root_node_ids` order;
5. unreferenced/orphan nodes are not silently rendered and create projection diagnostics.

Phase A validation runs before projection. Invalid graphs fail before rendering.

## 10. Rendering by node kind

### 10.1 Text

Text is the main editable content.

Known roles map to Markdown:

- title → `#`
- section headings → `##` through `######`
- ordered/unordered list structure → list syntax when representable
- ordinary text → paragraphs
- explicitly code-like content → fenced code block

Portable rich-run projection supports only flags Phase B can parse deterministically, initially bold, italic and inline-code where explicitly represented.

Unsupported typography is omitted from Markdown but remains untouched in IR.

**Identity-import rule:** semantic text changes may become `replace_text`; formatting-only changes to bold/italic/code are **not silently ignored**. Until an explicit safe `set_text_style` mapping is implemented and tested, a formatting-only difference is `markdown.edit.read_only`/`markdown.edit.unsupported` and fails in strict mode.

### 10.2 Notes

When enabled:

```md
### Notes

...
```

Identity mode gives notes their own marker and `replace_text` capability.

### 10.3 Images

```md
![alt text](m2w-resource:<resource_id>)
```

No local path is invented.

Phase B v1 allows only `set_alt_text`. Changing `m2w-resource:` is read-only/unsupported because Markdown does not carry replacement bytes or a validated replacement `Resource` object.

### 10.4 Tables

A rectangular table with no spans/nested rich structure may render as a GitHub-style Markdown table.

Merged or structurally complex tables render as readable HTML or a compact placeholder according to options, plus a projection diagnostic.

All table projections are read-only in Phase B v1. A user edit to table content does not become `update_table_cells` until cell-level identity is designed explicitly.

### 10.5 Charts

Semantic data may render as a readable summary, for example:

```md
### Chart: Revenue

- Q1: 10
- Q2: 14
```

Charts are read-only in Phase B v1.

### 10.6 Group

Groups are structural and emit no wrapper content; children render in order.

### 10.7 Shape

Text-bearing shapes delegate to their semantic text child/payload. Decorative shape-only information is not emitted.

### 10.8 Unknown native

Clean mode omits unknown-native content by default.

Identity mode may emit a non-editable invisible marker and, when requested, a readable placeholder.

Unknown native content is never converted to deletion merely because Markdown cannot represent it.

## 11. Projection normalization

Canonical projection rules:

- newline is `\n`;
- no trailing spaces;
- at most two consecutive blank lines between projected blocks;
- exactly one final newline unless output is empty;
- Unicode remains UTF-8, never ASCII-escaped;
- renderer applies anti-spoof escaping from section 7.1;
- pipe/backtick/emphasis characters are escaped only through deterministic renderer functions for the corresponding node kind.

Same IR + same options must produce byte-identical Markdown across runs and Python hash seeds.

## 12. Importer trust model

`import_identity_markdown()` requires:

1. edited identity Markdown;
2. originating `DocumentIR`;
3. matching identity `ProjectionManifest`.

Before edit generation it verifies:

- manifest mode is `identity`;
- supported header/manifest format version;
- header document id matches original IR;
- header source digest matches original IR canonical digest;
- manifest source digest matches original IR;
- every engine block marker resolves to exactly one manifest record;
- marker pid/node/kind/source digest equals manifest evidence;
- referenced node exists in original IR and its current semantic digest matches manifest source digest;
- duplicate pid/node constraints hold;
- declared editable capability authorizes detected change.

Any integrity mismatch fails closed in strict mode.

## 13. Block extraction and semantic comparison

A block begins immediately after `m2w:block` and ends immediately before the next recognized engine block marker or end of document.

The document header is not editable content.

Importer parses renderer-emitted Markdown into a semantic block model and compares semantics rather than raw bytes. Therefore the following may be no-ops when semantic content is identical:

- one vs two surrounding blank lines;
- final newline changes;
- renderer-equivalent escaping.

Actual text changes create edits. Rich-format-only changes are detected separately and are unsupported/read-only unless explicitly mapped.

## 14. Typed edit generation

### 14.1 `replace_text`

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

Operation id is SHA-256-derived deterministically from projection id, edit type and resulting semantic digest.

### 14.2 `set_alt_text`

Changing only image alt text produces `set_alt_text` with expected old alt text and locator precondition where available.

### 14.3 No implicit removal

Deleting a marked block is ambiguous and **does not** mean `remove_node`. Strict mode raises `markdown.block.missing`.

### 14.4 No implicit addition

Substantive unmarked content inserted outside known blocks is not attached heuristically. Strict identity import raises `markdown.block.unanchored_content`.

Node addition belongs to semantic Markdown rebuild mode or a future explicit identity add syntax.

### 14.5 Stable edit ordering

Edits are returned in original projection-block order, not discovery hash order or edit-type order.

## 15. Import result and diagnostic codes

```python
@dataclass(frozen=True)
class MarkdownImportResult:
    edits: tuple[EditOperation, ...]
    unchanged_node_ids: tuple[str, ...]
    diagnostics: tuple[MarkdownImportDiagnostic, ...]
```

Diagnostics contain stable code, severity, optional projection/node id and structured details. They contain no generated timestamp.

Initial codes:

```text
markdown.marker.malformed
markdown.marker.duplicate_projection_id
markdown.marker.duplicate_node
markdown.marker.unknown_projection_id
markdown.marker.metadata_mismatch
markdown.header.missing
markdown.header.document_mismatch
markdown.header.source_digest_mismatch
markdown.manifest.mode_mismatch
markdown.block.missing
markdown.block.unanchored_content
markdown.edit.unsupported
markdown.edit.read_only
markdown.semantic.parse_error
```

## 16. Error hierarchy additions

```text
MarkdownProjectionError
MarkdownImportError
MarkdownIdentityError
MarkdownSemanticParseError
```

All inherit `TwoWayError`, have stable codes and structured details.

Phase A errors remain unchanged.

## 17. Semantic Markdown reader

`read_markdown_ir()` is deliberately separate from identity import.

Identity import answers: **what changed relative to this existing rich document?**

Semantic reader answers: **build a new semantic document from this Markdown.**

It creates:

```text
DocumentIR
  source.format = markdown
  Canvas(kind="flow")
  nodes = headings / paragraphs / lists / code / images / simple tables
```

It never invents physical geometry.

With caller-supplied reproducible document identity, node ids derive deterministically from identity + structural position + semantic content. Without a reproducible seed, the Phase A non-reproducible identity path is used and diagnostics record this.

Links/images are inert semantic references; no network/local file access occurs.

## 18. Parsing strategy

Phase B does not add a heavy mandatory Markdown dependency unless implementation tests prove one is necessary.

Selected strategy:

- strict dedicated line parser for `m2w:` engine markers;
- deterministic semantic parser for the exact subset emitted by our renderer;
- conservative CommonMark-like subset for `read_markdown_ir()`;
- existing mandatory MarkItDown dependencies may be reused only when dependency direction stays lightweight and deterministic.

The required invariant is: **the importer can parse every construct the identity renderer itself emits.** It does not need universal Markdown-extension support in Phase B.

Unsupported semantic-reader constructs degrade to inert/plain semantic text with diagnostics rather than corrupting graph structure.

## 19. Security and resource limits

Markdown is untrusted input.

No importer/reader side effect may:

- fetch network resources;
- open arbitrary linked local files;
- execute script/HTML;
- decode arbitrary data URIs into resources;
- invoke plugins;
- resolve Office relationships.

Links/HTML are inert data.

Configurable deterministic limits cover:

- maximum Markdown input bytes;
- maximum marker count;
- maximum marker line length;
- maximum semantic nesting depth/block count.

Limit violations raise typed errors with stable codes.

## 20. Projection fidelity

Projection fidelity is separate from native writer fidelity.

Initial conceptual tiers:

```text
semantic-complete
semantic-partial
readable-only
```

Pure textual material may be semantic-complete. Complex tables/charts are semantic-partial. Unknown-native content may be readable-only/unprojected with diagnostics.

Markdown projection never claims visual/layout fidelity.

## 21. Determinism requirements

For same valid IR + options:

```text
project_markdown(ir).markdown
projection_manifest_bytes(manifest)
```

must be byte-identical across repeated runs and hash seeds.

Same edited Markdown + original IR + manifest must produce identical ordered edits and operation ids.

No timestamp, random UUID or environment-dependent path.

## 22. Required tests

Tests live under:

```text
packages/markitdown/tests/twoways/markdown/
```

### Clean projection

- title/heading/paragraph/list/note rendering;
- image alt/resource URI;
- simple table;
- group traversal order;
- chart summary;
- unknown-native omission/placeholder;
- Unicode/escaping.

### Identity projection

- deterministic header/block markers;
- stable manifest records and manifest bytes;
- marker canonical encoding/parsing;
- exact `m2w:` user text cannot spoof markers;
- repeated projection byte equality;
- different `PYTHONHASHSEED` equality.

### Identity import

- unchanged identity Markdown → zero edits;
- text change → one deterministic `replace_text`;
- alt change → one deterministic `set_alt_text`;
- harmless whitespace normalization → zero edits;
- formatting-only difference → unsupported/read-only, never silent no-op;
- resource URI change → unsupported/read-only;
- duplicate marker → fail closed;
- missing marker/block → fail closed;
- clean-mode manifest → fail closed;
- stale document digest → fail closed;
- marker/node/source digest mismatch → fail closed;
- substantive unanchored content → fail closed;
- table/chart edit → fail closed;
- deterministic edit order/id.

### Semantic reader

- headings/paragraphs become flow nodes;
- ordered/unordered list order retained;
- inert image/link representation;
- no geometry invented;
- Unicode retained;
- deterministic ids with same seed;
- no filesystem/network access.

### Regression

All Phase A tests stay unchanged and green.

## 23. Quality gates

Phase B is complete only when:

1. all Phase A focused tests pass unchanged;
2. all Phase B tests pass;
3. clean projection is deterministic;
4. identity projection and manifest serialization are deterministic;
5. identity importer fails closed for stale/ambiguous identity evidence;
6. unchanged identity Markdown produces zero edits;
7. supported edits carry semantic and available native-locator preconditions;
8. formatting-only/read-only mutations cannot disappear silently;
9. importer/reader performs no network or linked-filesystem access;
10. `markitdown.twoways` public import remains lightweight;
11. Markdown modules import no Office-specific library;
12. Python 3.10 syntax/type compatibility is retained;
13. GitHub workflow matrix status is reported separately and is never claimed green without actual run evidence.

## 24. Explicit non-goals for v1

Phase B does not:

- generate/rewrite PPTX or DOCX;
- patch OOXML;
- round-trip geometry via Markdown;
- edit charts;
- edit complex/merged tables;
- map arbitrary Markdown styling to Office style operations;
- infer deletion from missing markers;
- infer addition from unanchored prose;
- fetch linked images/files;
- execute HTML;
- promise visual fidelity.

These are intentional safety/fidelity boundaries: ambiguous edits are refused rather than guessed.

## 25. Phase C handoff

Once Phase B is verified:

```text
PPTX reader
   ↓
DocumentIR
   ↓
identity Markdown + manifest
   ↓
AI / human edit
   ↓
MarkdownImportResult
   ↓
EditOperation + semantic/native preconditions
   ↓
PPTX minimal-patch writer
```

Phase C therefore consumes typed edits and native locators. It does not need to understand Markdown, keeping native OOXML mutation isolated from the human/LLM text layer.
