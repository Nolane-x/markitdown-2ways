# MarkItDown 2Ways — Phase A Core IR Design

**Date:** 2026-09-08  
**Status:** Phase-specific design ready for review  
**Parent design:** `2026-09-08-markitdown-2ways-document-ir-design.md`  
**Branch:** `nolane/2way-document-ir-v0`

## 1. Phase A objective

Phase A creates only the substrate required by every later two-way format:

- versioned Document IR models,
- deterministic serialization,
- reader/writer contracts,
- prioritized registries,
- edit-operation contracts,
- fidelity/result contracts,
- typed errors,
- and tests proving that all of this can coexist with upstream MarkItDown without changing existing one-way behavior.

Phase A deliberately does **not** parse or write PPTX yet. It defines the public/internal contracts that the PPTX implementation will consume in the next phase.

## 2. Namespace and compatibility boundary

All new code lives under:

`packages/markitdown/src/markitdown/twoways/`

Existing modules such as `_markitdown.py`, `_base_converter.py`, and current converters stay unchanged during Phase A except for a minimal export in the package root if later review shows it is necessary. The preferred first version requires users to import `markitdown.twoways` explicitly.

This means all existing MarkItDown tests should pass without needing updates.

## 3. Module boundaries

```text
markitdown/twoways/
  __init__.py
  _errors.py
  _registry.py
  _results.py
  readers/
    __init__.py
    base.py
  writers/
    __init__.py
    base.py
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
```

Responsibilities are intentionally narrow:

- `document.py`: top-level `DocumentIR`, `Canvas`, source/metadata models;
- `nodes.py`: common node families and hierarchy fields;
- `geometry.py`: coordinates and transforms;
- `style.py`: portable style representation and native references;
- `provenance.py`: extraction/native locator evidence;
- `resources.py`: binary-resource metadata and relationships;
- `edits.py`: typed edit-operation envelope and initial edit variants;
- `serialization.py`: deterministic dict/JSON encode/decode and schema validation;
- `readers/base.py`: reader protocol only;
- `writers/base.py`: writer protocol and target description only;
- `_registry.py`: priority registration/selection mechanics;
- `_results.py`: writer/fidelity result objects;
- `_errors.py`: typed exception hierarchy.

No one module should import a format-specific library such as `pptx` in Phase A.

## 4. Schema versioning

The first schema version is:

`0.1.0`

It follows semantic-version intent:

- patch: serialization/validation fixes that remain backwards compatible;
- minor: additive fields/node kinds with safe defaults;
- major: incompatible structure or semantics.

Every serialized IR object includes:

```json
{
  "schema_name": "MarkItDown2WaysDocument",
  "schema_version": "0.1.0"
}
```

Unknown major versions are rejected. Unknown minor fields are ignored only when the decoder is explicitly configured for forward-compatible mode; strict mode rejects them so tests can catch accidental schema drift.

## 5. Identity model

### 5.1 Document identity

`document_id` is a stable opaque string. Readers may derive it from stable source identity where available, but the IR contract does not require a specific algorithm.

Synthetic callers may supply a document id. If omitted, Phase A provides a deterministic document-local id factory rather than an implicit random UUID. The factory is seeded by caller-provided identity material; when no seed is available it uses a monotonically assigned in-memory id and marks it as non-reproducible in diagnostics.

No wall-clock time or random value is inserted during deterministic serialization.

### 5.2 Node identity

`node_id` is stable inside a document and is never recomputed merely because node text changes.

Format readers later choose ids using native stable locators when possible. The Phase A core only validates uniqueness.

### 5.3 Canvas identity

Each slide/page/sheet-like surface has a `canvas_id` and ordered `index`.

The common model does not assume that every document has canvases. Flow documents may use one implicit canvas or no physical canvas until a format adapter supplies one.

## 6. Top-level DocumentIR

Conceptual Python contract:

```python
@dataclass(frozen=True)
class DocumentIR:
    schema_name: str
    schema_version: str
    document_id: str
    source: SourceDescriptor | None
    metadata: DocumentMetadata
    canvases: tuple[Canvas, ...]
    nodes: Mapping[str, Node]
    root_node_ids: tuple[str, ...]
    resources: Mapping[str, Resource]
    relationships: tuple[Relationship, ...]
    native_payloads: Mapping[str, NativePayload]
    edits: tuple[EditOperation, ...]
    diagnostics: tuple[Diagnostic, ...]
```

The implementation does not have to make every nested object frozen if that makes edit workflows impractical, but serialization must behave as if state is explicit and ordered.

### 6.1 SourceDescriptor

Fields:

- `format`: normalized format name such as `pptx`, `docx`, `markdown`;
- `filename`: optional original filename;
- `mimetype`: optional MIME type;
- `uri`: optional source URI, excluded from network access by default;
- `sha256`: optional digest of original source bytes;
- `size_bytes`: optional source size;
- `preserved_source_ref`: optional reference to a future bundle/native payload.

### 6.2 DocumentMetadata

Initial portable fields:

- `title`
- `subject`
- `author`
- `company`
- `language`
- arbitrary namespaced `custom` values.

Metadata values must be JSON-compatible scalars, lists, or mappings.

## 7. Canvas model

Fields:

```text
canvas_id
index
kind
name
width
height
unit
root_node_ids
native_locator
metadata
```

`kind` is an enum-like string with initial values:

- `page`
- `slide`
- `sheet`
- `flow`
- `unknown`

Unknown future string values are preserved in permissive mode.

A canvas's node order is expressed by `root_node_ids` and child ordering, not inferred from the node mapping's dictionary order.

## 8. Node model

### 8.1 Base fields

Every node contains:

```text
node_id
kind
semantic_role
parent_id
children
order
canvas_id
geometry
style
provenance
native_locator
metadata
```

`children` is ordered.

`parent_id` and `children` must agree. Validation rejects cycles, missing children and a child referenced by multiple parents unless the future node type explicitly supports graph semantics.

### 8.2 Initial node kinds

Phase A implements model classes or discriminated payloads for:

- `text`
- `image`
- `table`
- `chart`
- `group`
- `shape`
- `note`
- `unknown_native`

The core should not create dozens of inheritance layers. Prefer a small base node plus typed payload objects when that is easier to serialize and maintain.

### 8.3 Text payload

Phase A text representation supports both plain and rich text without imposing a PowerPoint-specific model.

```text
TextPayload:
  text
  paragraphs

Paragraph:
  runs
  list_level
  alignment
  metadata

TextRun:
  text
  style
  native_locator
```

`text` is a normalized convenience projection; when `paragraphs` exist they are the richer source. Validation checks that writers can deliberately choose which representation they support.

### 8.4 Image payload

Metadata only in Phase A:

- `resource_id`
- `alt_text`
- optional crop metadata
- optional original dimensions.

Actual bytes live behind `Resource`.

### 8.5 Table payload

Portable structural fields:

- rows,
- columns,
- cells,
- row/column spans,
- cell node/content ids where appropriate.

Merged-cell structure must be representable even though Markdown cannot express it.

### 8.6 Chart payload

Phase A supports a lightweight portable descriptor plus native preservation hook:

- chart type if known,
- title if known,
- series/category semantic data if known,
- native payload reference.

The model must permit `unknown_native` chart details to survive without pretending the portable schema is complete.

## 9. Geometry model

`Geometry` fields:

```text
x
y
width
height
rotation
unit
origin
transform
source_values
```

Supported portable units initially:

- `pt`
- `in`
- `px`
- `emu`
- `normalized`

The model preserves source-native values in `source_values` rather than repeatedly converting and losing precision.

Validation rules:

- width/height cannot be negative;
- NaN and infinity are rejected;
- rotation is normalized for portable output but original value may remain in source values;
- coordinates may be outside the canvas because Office files can intentionally place shapes partially off-canvas.

## 10. Style model

The portable `Style` model is intentionally sparse and additive.

Initial groups:

- typography,
- fill,
- line/border,
- opacity,
- alignment,
- spacing,
- theme references,
- native style reference.

The core distinguishes:

- `direct`: properties explicitly set on the node/run;
- `inherited`: optional values reported by a reader;
- `resolved`: optional convenience view.

Writers must not blindly materialize `resolved` values as direct formatting.

## 11. Provenance and native locator

### 11.1 Provenance

Fields:

```text
source_format
canvas_index
part_uri
bbox
char_span
extraction_method
confidence
metadata
```

`confidence` is optional and bounded to `[0, 1]` when present.

### 11.2 NativeLocator

Portable envelope:

```text
backend
part_uri
object_id
creation_id
relationship_id
name
path
attributes
```

All fields except `backend` are optional because different formats expose different identities.

`attributes` is namespaced metadata, not a dumping ground for arbitrary unbounded source documents.

Locators are evidence to be validated by a writer, never trusted without checking.

## 12. Resource model

`Resource` fields:

```text
resource_id
sha256
content_type
filename
size_bytes
storage_ref
metadata
```

Phase A does not mandate an on-disk asset store. `storage_ref` is an opaque reference resolved by a caller/bundle implementation later.

Resource identity is digest-oriented so duplicate media can be deduplicated.

No binary blobs are inlined in the canonical JSON by default.

## 13. Relationship model

Generic relationships allow the IR to represent links without forcing native OOXML rel syntax into every node.

Fields:

- `relationship_id`
- `source_id`
- `target_id` or external target
- `kind`
- `native_locator`
- metadata.

External targets are inert data. Phase A performs no network fetch.

## 14. NativePayload

`NativePayload` is a preservation escape hatch for data the common IR does not understand.

Fields:

```text
payload_id
backend
content_type
sha256
storage_ref
scope
metadata
```

It never directly executes or interprets embedded active content.

Later formats may attach native payload refs to nodes, canvases or documents.

## 15. Diagnostics

Diagnostic fields:

- code,
- severity (`info`, `warning`, `error`),
- message,
- node/canvas reference,
- machine-readable details.

Diagnostics are deterministic data. They do not include automatically generated timestamps.

## 16. Edit operation contract

Phase A defines the typed envelope and a small initial set sufficient for Markdown-edit and PPTX text work.

### 16.1 Common fields

```text
operation_id
type
target_node_id
precondition
payload
source_label
```

### 16.2 Precondition

A precondition can include:

- expected semantic digest,
- expected native locator digest,
- expected old value.

Writers later decide which preconditions they can enforce, but strict mode must fail if a declared precondition cannot be verified.

### 16.3 Initial operation types

- `replace_text`
- `set_text_style`
- `move_resize`
- `replace_resource`
- `set_alt_text`
- `update_table_cells`
- `add_node`
- `remove_node`

Operations not understood by a writer are reported as unsupported; they are never silently discarded.

## 17. Deterministic serialization

### 17.1 Canonical dict

All models expose a plain JSON-compatible dictionary representation.

Rules:

- explicit discriminator fields (`kind`, `type`, etc.);
- mappings serialized in sorted-key order;
- ordered semantic lists preserve their defined order;
- floats reject NaN/Infinity;
- bytes are never silently stringified;
- absent optional fields use a single consistent policy across schema versions;
- no timestamps/random UUIDs generated as a side effect of serialization.

### 17.2 Canonical JSON

Canonical JSON encoding uses:

- UTF-8,
- sorted object keys,
- stable separators,
- deterministic Unicode behavior,
- trailing newline only when writing a text file, not when computing digests.

A helper returns both canonical bytes and SHA-256 digest.

### 17.3 Round-trip guarantee

For any valid Phase A IR:

`decode(encode(ir)) == ir`

under semantic equality.

The tests compare the second canonical encoding byte-for-byte with the first.

## 18. Validation

Validation runs at explicit boundaries rather than on every property assignment.

`validate_document(ir)` checks:

- supported schema major version;
- unique document/canvas/node/resource/relationship ids;
- canvas indices/order consistency;
- valid root references;
- parent/child consistency;
- acyclic hierarchy;
- canvas references;
- resource references;
- native payload references;
- edit target references;
- geometry numeric validity;
- provenance confidence bounds;
- digest syntax when present.

The function returns no warnings on a valid document. It raises `IRValidationError` with structured violations on invalid input.

## 19. Reader protocol

```python
class DocumentIRReader(Protocol):
    def accepts(
        self,
        file_stream: BinaryIO,
        stream_info: StreamInfo,
        **kwargs: Any,
    ) -> bool: ...

    def read(
        self,
        file_stream: BinaryIO,
        stream_info: StreamInfo,
        **kwargs: Any,
    ) -> DocumentIR: ...
```

The stream-position rule matches `DocumentConverter.accepts`: `accepts()` must restore the original position.

Phase A only defines the protocol; no built-in format reader is registered.

## 20. Writer protocol

```python
@dataclass(frozen=True)
class TargetInfo:
    format: str
    mimetype: str | None = None
    extension: str | None = None

class DocumentWriter(Protocol):
    def accepts(
        self,
        document: DocumentIR,
        target: TargetInfo,
        **kwargs: Any,
    ) -> bool: ...

    def write(
        self,
        document: DocumentIR,
        output: BinaryIO,
        target: TargetInfo,
        **kwargs: Any,
    ) -> WriterResult: ...
```

The first contract writes to a binary stream so file/path convenience can live in the later facade rather than every writer.

## 21. Registry behavior

Reader/writer registrations follow upstream MarkItDown's priority semantics:

- lower numeric priority is tried first;
- registration order is stable;
- for equal priorities, most recently registered implementation is tried first.

Proposed generic registration:

```python
@dataclass(frozen=True)
class Registration(Generic[T]):
    implementation: T
    priority: float
    name: str | None = None
```

Registry operations:

- `register(implementation, priority=0, name=None)`
- `iter_candidates()`
- no hidden global mutable registry; instances own registrations.

Phase A registry is format-agnostic and can be used by both readers and writers.

## 22. Writer and fidelity results

### 22.1 Fidelity tier

Enum/string values:

- `exact-preserve`
- `high`
- `semantic`
- `reconstructed`
- `unknown`

### 22.2 FidelityEvidence

Fields:

- check code,
- passed/failed/not-applicable,
- description,
- expected/actual compact values,
- affected node ids.

### 22.3 FidelityReport

Fields:

- claimed tier,
- evidence list,
- unsupported feature list,
- warnings.

Validation rule: a report cannot claim `exact-preserve` when it contains failed required-preservation evidence.

### 22.4 WriterResult

Fields:

```text
format
mode
bytes_written
fidelity
warnings
unsupported_operations
metadata
```

The actual output stream is supplied by the caller; `WriterResult` does not duplicate output bytes.

## 23. Error hierarchy

```text
TwoWayError
├── IRValidationError
├── UnsupportedSchemaVersionError
├── ReaderNotFoundError
├── WriterNotFoundError
├── UnsupportedEditError
├── SourcePackageMismatchError
├── AmbiguousNativeLocatorError
├── PatchPreconditionError
└── RoundTripVerificationError
```

Phase A implements the hierarchy even when some errors are not raised until later phases. This prevents later format code from inventing incompatible exceptions.

All errors carry a stable `code` string and structured `details` mapping.

## 24. Public exports for Phase A

`markitdown.twoways` exports only stable contract objects:

- `DocumentIR`
- `Canvas`
- core node classes/payloads
- `Geometry`
- `Style`
- `Provenance`
- `NativeLocator`
- `Resource`
- `EditOperation`
- `DocumentIRReader`
- `DocumentWriter`
- `TargetInfo`
- `WriterResult`
- `FidelityReport`
- base error types
- canonical serialization helpers.

Internal registry mechanics can remain semi-private until the facade phase.

## 25. Test design

### 25.1 No-regression baseline

Run the existing MarkItDown test suite unchanged.

### 25.2 Model tests

Construct one representative IR containing:

- two canvases,
- nested group/text/image/table nodes,
- geometry in multiple units,
- resource references,
- provenance/native locators,
- an unknown-native node,
- two edit operations.

Verify all references and validation.

### 25.3 Serialization tests

- canonical encoding is deterministic;
- encode/decode/encode byte equality;
- Unicode content survives;
- unknown major schema rejected;
- NaN/Infinity rejected;
- invalid digest rejected;
- unexpected strict-mode field rejected.

### 25.4 Graph validation tests

Reject:

- duplicate node ids,
- missing child,
- parent/child disagreement,
- cycles,
- nonexistent canvas ids,
- missing resources,
- invalid edit targets.

### 25.5 Registry tests

Verify exact upstream-equivalent priority behavior:

- priority `-1` before `0` before `10`;
- later registration wins among equal priorities;
- candidate iteration does not mutate registration state.

### 25.6 Protocol fixture tests

Create tiny fake readers/writers to prove:

- `accepts()` dispatch behavior;
- writer selection by target format;
- result/fidelity plumbing;
- failures are typed and preserve structured details.

## 26. Quality gates

Phase A is complete only when:

1. all existing MarkItDown tests pass unchanged;
2. new twoways tests pass on the project's supported Python versions;
3. type checking succeeds under the existing project mypy configuration;
4. no format-specific dependency is imported by core IR modules;
5. canonical JSON determinism is demonstrated by tests;
6. invalid graph/reference structures fail closed;
7. reader/writer priority tests match upstream semantics;
8. package import remains lightweight when optional Office dependencies are absent.

## 27. Explicit design choices

### Dataclasses over Pydantic for Phase A

Use standard-library dataclasses and explicit serializers first. This avoids imposing a new mandatory dependency on all MarkItDown users and keeps schema behavior fully controlled.

### Mapping plus ordered references

Store nodes/resources by id for efficient lookup, while preserving semantic order through explicit ordered id lists. Never rely on dictionary iteration as document order.

### Immutable-ish public contract

Favor value-like objects and explicit edit operations. Avoid format writers mutating arbitrary nested dicts in place.

### Unknown-native as a first-class state

The schema must represent content it cannot understand. Unsupported does not mean disposable.

### Strict deterministic core

Timestamps, random ids, environment-dependent paths and network access are outside canonical serialization unless explicitly supplied by the caller.

## 28. What Phase B may assume

Once Phase A quality gates are green, Phase B may safely build:

- clean Markdown projection,
- identity-marked Markdown projection,
- Markdown re-import to typed edits,
- semantic Markdown reader for rebuild workflows.

Phase C/D may then build PPTX readers/writers against the same contracts without redefining the IR foundation.
