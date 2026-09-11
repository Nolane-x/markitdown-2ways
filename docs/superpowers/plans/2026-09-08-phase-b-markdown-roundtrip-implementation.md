# MarkItDown 2Ways Phase B Markdown Round-Trip Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a deterministic Markdown bridge that projects `DocumentIR` into clean/identity Markdown and conservatively converts edited identity Markdown back into typed `EditOperation` objects, while also supporting ordinary Markdown → semantic `DocumentIR` rebuild input.

**Architecture:** Add an isolated `markitdown.twoways.markdown` package with separate value models, rendering, identity-marker parsing, importer, and semantic reader modules. Identity import is fail-closed and requires the originating `DocumentIR` plus matching manifest; clean Markdown remains presentation-only and cannot be re-imported as authoritative edits.

**Tech Stack:** Python 3.10+, stdlib `dataclasses`, `enum`, `hashlib`, `html`, `re`, `json`, `typing`; existing Phase A Core IR; pytest. No new mandatory dependency.

**Spec:** `docs/superpowers/specs/2026-09-08-markitdown-2ways-phase-b-markdown-roundtrip-design.md`

## Global Constraints

- `DocumentIR` schema remains exactly `MarkItDown2WaysDocument` version `0.1.0`; Phase B does not change the Phase A schema.
- New production code lives under `packages/markitdown/src/markitdown/twoways/markdown/` except stable public exports/errors added to the existing `markitdown.twoways` namespace.
- Existing `MarkItDown.convert()`, converters, CLI and plugin behavior remain unchanged.
- Clean Markdown is never eligible for identity re-import.
- Identity importer requires edited Markdown + original `DocumentIR` + matching `ProjectionManifest`.
- Missing/stale/duplicate/mismatched engine markers fail closed in strict mode; importer never guesses node identity.
- Missing marked blocks are not implicit `remove_node`; unmarked inserted prose is not implicit `add_node`.
- Phase B v1 editable operations are `replace_text` for text/note nodes and `set_alt_text` for image alt text. Unsupported formatting-only edits are reported, not silently discarded.
- Charts and complex tables are read-only in Phase B v1.
- User text that resembles an engine marker must be deterministically anti-spoof escaped before identity rendering.
- No network fetch, local file read, script/HTML execution, arbitrary data-URI decoding or plugin invocation occurs during projection/import.
- Projection manifests, block ids and generated edit ids are deterministic and contain no timestamps, randomness or environment-dependent paths.
- Core Markdown modules must not import `pptx`, Mammoth, pandas, openpyxl, LibreOffice, Node bridges, Docling or cloud SDKs.

---

## File Map

### Production

- `packages/markitdown/src/markitdown/twoways/markdown/__init__.py` — stable Markdown bridge exports.
- `packages/markitdown/src/markitdown/twoways/markdown/model.py` — projection/import options, manifest/block/diagnostic/result dataclasses.
- `packages/markitdown/src/markitdown/twoways/markdown/identity.py` — canonical marker grammar, encoder/parser, anti-spoof escaping.
- `packages/markitdown/src/markitdown/twoways/markdown/rendering.py` — deterministic semantic rendering for supported IR node kinds.
- `packages/markitdown/src/markitdown/twoways/markdown/projection.py` — validated traversal, clean/identity assembly, manifest creation.
- `packages/markitdown/src/markitdown/twoways/markdown/importer.py` — strict identity validation, semantic diff and typed edit generation.
- `packages/markitdown/src/markitdown/twoways/markdown/semantic_reader.py` — conservative ordinary Markdown → flow `DocumentIR`.
- `packages/markitdown/src/markitdown/twoways/_errors.py` — add Phase B typed Markdown errors.
- `packages/markitdown/src/markitdown/twoways/__init__.py` — add stable Phase B public exports only.

### Tests

- `packages/markitdown/tests/twoways/test_markdown_model_identity.py`
- `packages/markitdown/tests/twoways/test_markdown_projection.py`
- `packages/markitdown/tests/twoways/test_markdown_importer.py`
- `packages/markitdown/tests/twoways/test_markdown_semantic_reader.py`
- `packages/markitdown/tests/twoways/test_markdown_public_imports.py`

---

### Task 1: Projection/import value models and typed Markdown errors

**Files:**
- Create: `packages/markitdown/src/markitdown/twoways/markdown/model.py`
- Create: `packages/markitdown/src/markitdown/twoways/markdown/__init__.py`
- Modify: `packages/markitdown/src/markitdown/twoways/_errors.py`
- Test: `packages/markitdown/tests/twoways/test_markdown_model_identity.py`

**Interfaces:**
- Consumes: Phase A `DocumentIR`, `EditOperation`, `TwoWayError`.
- Produces: `MarkdownProjectionMode`, `MarkdownProjectionOptions`, `ProjectionDiagnostic`, `ProjectionBlock`, `ProjectionManifest`, `MarkdownProjection`, `MarkdownImportDiagnostic`, `MarkdownImportResult`.
- Produces errors: `MarkdownProjectionError`, `MarkdownImportError`, `MarkdownIdentityError`, `MarkdownSemanticParseError`.

- [ ] **Step 1: Write the failing tests**

```python
from markitdown.twoways.markdown import (
    MarkdownProjectionMode,
    MarkdownProjectionOptions,
    ProjectionBlock,
    ProjectionManifest,
)
from markitdown.twoways import MarkdownIdentityError


def test_projection_options_default_to_clean_mode():
    options = MarkdownProjectionOptions()
    assert options.mode is MarkdownProjectionMode.CLEAN
    assert options.resource_uri_scheme == "m2w-resource"


def test_projection_manifest_is_tuple_backed_and_versioned():
    block = ProjectionBlock(
        projection_id="p1",
        node_id="n1",
        canvas_id="c1",
        node_kind="text",
        semantic_role=None,
        ordinal=0,
        source_semantic_digest="a" * 64,
        native_locator_digest=None,
        editable_capabilities=("replace_text",),
        rendered_digest="b" * 64,
    )
    manifest = ProjectionManifest(
        format_version="1",
        document_id="doc1",
        document_schema_version="0.1.0",
        source_document_digest="c" * 64,
        projection_mode="identity",
        blocks=[block],
    )
    assert manifest.blocks == (block,)


def test_markdown_identity_error_keeps_structured_details():
    exc = MarkdownIdentityError("bad marker", details={"line": 4})
    assert exc.code == "markdown.identity"
    assert exc.details == {"line": 4}
```

- [ ] **Step 2: Run test and verify RED**

Run:

```bash
PYTHONPATH=packages/markitdown/src pytest -q packages/markitdown/tests/twoways/test_markdown_model_identity.py
```

Expected: import/collection failure because `markitdown.twoways.markdown` and Phase B errors do not exist.

- [ ] **Step 3: Implement minimum models/errors**

Requirements:

```python
class MarkdownProjectionMode(str, Enum):
    CLEAN = "clean"
    IDENTITY = "identity"
```

All tuple-like public fields defensively normalize lists to tuples in `__post_init__`. Mapping details are copied. Diagnostic severities are restricted to `info`, `warning`, `error`. `ProjectionManifest.format_version` is non-empty and v1 construction uses exactly `"1"`. Error subclasses inherit `TwoWayError` with stable default codes:

```text
markdown.projection
markdown.import
markdown.identity
markdown.semantic_parse
```

Do not add rendering/import logic in this task.

- [ ] **Step 4: Run focused test and verify GREEN**

Run the same pytest command. Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add packages/markitdown/src/markitdown/twoways/markdown packages/markitdown/src/markitdown/twoways/_errors.py packages/markitdown/tests/twoways/test_markdown_model_identity.py
git commit -m "feat(twoways): add Markdown bridge contracts"
```

---

### Task 2: Strict identity grammar, anti-spoof escaping and manifest serialization

**Files:**
- Create: `packages/markitdown/src/markitdown/twoways/markdown/identity.py`
- Modify: `packages/markitdown/src/markitdown/twoways/markdown/model.py`
- Test: `packages/markitdown/tests/twoways/test_markdown_model_identity.py`

**Interfaces:**
- Produces `encode_projection_header(...) -> str`, `encode_block_marker(...) -> str`, `parse_marker_line(line, *, strict=True) -> ParsedMarker | None`.
- Produces `escape_marker_like_text(text) -> str` and `unescape_marker_like_text(text) -> str`.
- Produces `projection_manifest_bytes(manifest) -> bytes` and `projection_manifest_digest(manifest) -> str`.

- [ ] **Step 1: Add failing identity tests**

```python
from markitdown.twoways.markdown.identity import (
    encode_block_marker,
    encode_projection_header,
    escape_marker_like_text,
    parse_marker_line,
)


def test_identity_marker_encoder_is_canonical_and_one_line():
    marker = encode_block_marker(
        projection_id="p1", node_id="n1", kind="text", source_digest="a" * 64
    )
    assert marker == '<!-- m2w:block pid="p1" node="n1" kind="text" src="sha256:' + "a" * 64 + '" -->'
    assert "\n" not in marker


def test_duplicate_marker_keys_fail_closed():
    line = '<!-- m2w:block pid="p1" pid="p2" node="n1" kind="text" src="sha256:' + "a" * 64 + '" -->'
    with pytest.raises(MarkdownIdentityError):
        parse_marker_line(line)


def test_unrelated_html_comment_is_not_engine_marker():
    assert parse_marker_line("<!-- ordinary comment -->") is None


def test_marker_like_user_text_is_escaped():
    escaped = escape_marker_like_text('hello <!-- m2w:block pid="evil" --> world')
    assert "<!-- m2w:block" not in escaped
```

Add tests that malformed `m2w:` comments raise, marker values reject physical newlines, header keys are canonical, unknown keys fail strict mode, and manifest bytes are byte-identical across repeated encoding.

- [ ] **Step 2: Verify RED**

Run focused test. Expected: missing identity functions.

- [ ] **Step 3: Implement marker parser/encoder and deterministic manifest codec**

Use a strict one-line grammar and explicit allowed-key sets:

```text
projection: v, doc, base
block: pid, node, kind, src
```

HTML-escape marker values on encoding and reverse that only for parsed marker attributes. Anti-spoof user text replaces the exact `<!-- m2w:` opener with a deterministic inert representation that normal Markdown readers render as text and `unescape_marker_like_text()` reverses. Do not globally unescape unrelated HTML entities.

Manifest encoding uses JSON UTF-8, sorted keys, stable separators, no timestamp, no NaN/Infinity and preserves block order.

- [ ] **Step 4: Verify GREEN**

Run focused identity/model tests. Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add packages/markitdown/src/markitdown/twoways/markdown packages/markitdown/tests/twoways/test_markdown_model_identity.py
git commit -m "feat(twoways): add strict Markdown identity grammar"
```

---

### Task 3: Deterministic clean and identity Markdown projection

**Files:**
- Create: `packages/markitdown/src/markitdown/twoways/markdown/rendering.py`
- Create: `packages/markitdown/src/markitdown/twoways/markdown/projection.py`
- Create: `packages/markitdown/tests/twoways/test_markdown_projection.py`
- Reuse: `packages/markitdown/tests/twoways/_fixtures.py`

**Interfaces:**
- Consumes `validate_document`, Phase A nodes/payloads, identity encoder and projection models.
- Produces `project_markdown(document, *, options=None) -> MarkdownProjection`.
- Internal rendering result records semantic text, Markdown text, editable capabilities and diagnostics per node.

- [ ] **Step 1: Write failing projection tests**

```python
from markitdown.twoways.markdown import (
    MarkdownProjectionMode,
    MarkdownProjectionOptions,
    project_markdown,
)
from ._fixtures import make_representative_document


def test_clean_projection_contains_no_engine_markers():
    projection = project_markdown(make_representative_document())
    assert projection.manifest.projection_mode == "clean"
    assert "<!-- m2w:" not in projection.markdown


def test_identity_projection_has_header_and_block_markers():
    result = project_markdown(
        make_representative_document(),
        options=MarkdownProjectionOptions(mode=MarkdownProjectionMode.IDENTITY),
    )
    assert result.markdown.startswith("<!-- m2w:projection ")
    assert '<!-- m2w:block ' in result.markdown
    assert result.manifest.projection_mode == "identity"


def test_projection_order_uses_canvas_and_explicit_child_order():
    result = project_markdown(make_representative_document())
    first = result.markdown.index("Quarterly Revenue")
    second = result.markdown.index("second slide")
    assert first < second
```

Add tests for text title/headings, rich text bold/italic, notes option, images using `m2w-resource:<id>`, simple tables, chart summaries, groups rendering children only, unknown-native omission/default diagnostics, one final newline, no trailing spaces, deterministic result across repeated calls, and marker-like source text anti-spoofing.

- [ ] **Step 2: Verify RED**

Expected: `project_markdown` missing.

- [ ] **Step 3: Implement deterministic traversal/rendering**

Traversal must call `validate_document(document)` first and follow:

1. canvases sorted by explicit `Canvas.index`;
2. each canvas `root_node_ids` order;
3. recursive `children` order;
4. document `root_node_ids` not already visited;
5. emit diagnostic for orphan/unprojected nodes rather than silently rendering mapping order.

Text rendering uses `TextPayload.paragraphs` when present, otherwise `TextPayload.text`. Title role maps to `#`; heading roles map conservatively; plain paragraphs stay plain. Bold/italic are emitted only from explicit run style direct values. Tables with spans or nested node ids are read-only/lossy diagnostic cases. Charts render readable semantic summary but no edit capability. Identity mode prepends one canonical block marker per independently projectable block and returns manifest records with semantic/native/rendered digests.

- [ ] **Step 4: Verify GREEN**

Run:

```bash
PYTHONPATH=packages/markitdown/src pytest -q packages/markitdown/tests/twoways/test_markdown_projection.py packages/markitdown/tests/twoways/test_markdown_model_identity.py
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add packages/markitdown/src/markitdown/twoways/markdown packages/markitdown/tests/twoways/test_markdown_projection.py
git commit -m "feat(twoways): project IR to deterministic Markdown"
```

---

### Task 4: Fail-closed identity importer and typed text/alt edits

**Files:**
- Create: `packages/markitdown/src/markitdown/twoways/markdown/importer.py`
- Create: `packages/markitdown/tests/twoways/test_markdown_importer.py`

**Interfaces:**
- Consumes identity Markdown, original `DocumentIR`, matching `ProjectionManifest`.
- Produces `import_identity_markdown(..., strict=True) -> MarkdownImportResult`.
- Generates only `replace_text` and `set_alt_text` in Phase B v1.

- [ ] **Step 1: Write failing importer tests**

```python
from markitdown.twoways.markdown import (
    MarkdownProjectionMode,
    MarkdownProjectionOptions,
    import_identity_markdown,
    project_markdown,
)
from ._fixtures import make_representative_document


def identity_fixture():
    doc = make_representative_document()
    projection = project_markdown(
        doc, options=MarkdownProjectionOptions(mode=MarkdownProjectionMode.IDENTITY)
    )
    return doc, projection


def test_unchanged_identity_projection_yields_no_edits():
    doc, projection = identity_fixture()
    result = import_identity_markdown(
        projection.markdown,
        original_document=doc,
        manifest=projection.manifest,
    )
    assert result.edits == ()


def test_text_change_generates_replace_text_with_preconditions():
    doc, projection = identity_fixture()
    edited = projection.markdown.replace("Revenue increased", "Revenue grew")
    result = import_identity_markdown(
        edited, original_document=doc, manifest=projection.manifest
    )
    edit = next(item for item in result.edits if item.type == "replace_text")
    assert edit.precondition.expected_old_value is not None
    assert edit.precondition.expected_semantic_digest
    assert edit.source_label == "markdown.identity.v1"
```

Add tests for changed image alt text; stale document digest; missing header; missing block; duplicate projection id; duplicate node marker; unknown projection id; metadata mismatch; substantive unanchored prose; clean-manifest rejection; unsupported formatting-only change; read-only chart/table change; deterministic operation ids; harmless blank-line/final-newline normalization yielding no edit.

- [ ] **Step 2: Verify RED**

Expected: importer missing.

- [ ] **Step 3: Implement integrity checks before semantic diff**

Importer order is mandatory:

1. reject non-identity manifest;
2. validate original document and recompute canonical source digest;
3. parse/validate header;
4. scan block markers and reject malformed/duplicate/unknown identity;
5. ensure every manifest identity block is present exactly once;
6. detect substantive unanchored content;
7. parse each editable block using the exact renderer-supported subset;
8. compare semantic content to source block semantics;
9. authorize operation using `editable_capabilities`;
10. emit deterministic typed edits.

Text edit precondition uses source semantic digest, native locator digest and old semantic text. Formatting-only changes that alter Markdown but not plain text must produce `markdown.edit.unsupported`/raise in strict mode rather than being classified unchanged. Missing block is `markdown.block.missing`, never `remove_node`.

- [ ] **Step 4: Verify GREEN**

Run importer + projection + identity tests. Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add packages/markitdown/src/markitdown/twoways/markdown/importer.py packages/markitdown/tests/twoways/test_markdown_importer.py
git commit -m "feat(twoways): import identity Markdown as typed edits"
```

---

### Task 5: Conservative semantic Markdown reader for rebuild workflows

**Files:**
- Create: `packages/markitdown/src/markitdown/twoways/markdown/semantic_reader.py`
- Create: `packages/markitdown/tests/twoways/test_markdown_semantic_reader.py`

**Interfaces:**
- Produces `read_markdown_ir(markdown, *, document_id=None, source_name=None) -> DocumentIR`.
- Creates exactly one `Canvas(kind="flow")` in Phase B v1.

- [ ] **Step 1: Write failing semantic-reader tests**

```python
from markitdown.twoways.markdown import read_markdown_ir
from markitdown.twoways import TextPayload, validate_document


def test_semantic_reader_builds_flow_document():
    doc = read_markdown_ir("# Title\n\nHello **world**.\n", document_id="md-doc")
    validate_document(doc)
    assert doc.document_id == "md-doc"
    assert len(doc.canvases) == 1
    assert doc.canvases[0].kind == "flow"
    assert doc.source.format == "markdown"


def test_semantic_reader_is_deterministic_with_explicit_document_id():
    source = "# Title\n\nHello.\n"
    a = read_markdown_ir(source, document_id="same")
    b = read_markdown_ir(source, document_id="same")
    assert tuple(a.nodes) == tuple(b.nodes)
```

Add coverage for headings, paragraphs, unordered/ordered list paragraphs with list levels, fenced code blocks represented as text nodes with code semantic role, image links as inert semantic references without file/network access, simple Markdown tables, marker-like text treated as ordinary semantic content in non-identity reader, source filename, and non-reproducible diagnostic when no deterministic document id is supplied.

- [ ] **Step 2: Verify RED**

Expected: reader missing.

- [ ] **Step 3: Implement small deterministic parser for supported subset**

The parser recognizes only syntax Phase B intentionally supports. It must never fetch URLs/files. Unsupported constructs fall back to paragraph text rather than executing/interpreting HTML. Node ids are generated from deterministic identity + structural ordinal/content; with explicit `document_id`, repeated input must produce the same ids.

Use `TextPayload`/`Paragraph`/`TextRun` and existing `ImagePayload`/`TablePayload` only where enough information exists to build valid IR. Do not invent geometry.

- [ ] **Step 4: Verify GREEN**

Run semantic-reader tests plus Phase A validation/serialization tests. Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add packages/markitdown/src/markitdown/twoways/markdown/semantic_reader.py packages/markitdown/tests/twoways/test_markdown_semantic_reader.py
git commit -m "feat(twoways): read semantic Markdown into IR"
```

---

### Task 6: Stable public exports, dependency boundary and full Phase A+B regression

**Files:**
- Modify: `packages/markitdown/src/markitdown/twoways/markdown/__init__.py`
- Modify: `packages/markitdown/src/markitdown/twoways/__init__.py`
- Create: `packages/markitdown/tests/twoways/test_markdown_public_imports.py`
- Modify only if necessary: existing Markdown tests from Tasks 1–5.

**Interfaces:**
- Root public API adds only the stable Phase B objects/functions declared in the spec.
- Internal parser/render helpers remain out of root `__all__`.

- [ ] **Step 1: Write failing public-surface tests**

```python
import markitdown.twoways as tw


def test_phase_b_public_api_is_exported():
    expected = {
        "MarkdownProjectionMode",
        "MarkdownProjectionOptions",
        "MarkdownProjection",
        "ProjectionManifest",
        "MarkdownImportResult",
        "project_markdown",
        "import_identity_markdown",
        "read_markdown_ir",
        "projection_manifest_bytes",
        "projection_manifest_digest",
        "MarkdownProjectionError",
        "MarkdownImportError",
        "MarkdownIdentityError",
        "MarkdownSemanticParseError",
    }
    assert expected <= set(tw.__all__)


def test_internal_identity_parser_is_not_root_exported():
    assert "parse_marker_line" not in tw.__all__
```

- [ ] **Step 2: Verify RED**

Expected: Phase B root exports incomplete.

- [ ] **Step 3: Add stable exports only**

Keep `_registry`, marker parser internals, rendering internals and parser helper types private. Root import must remain lightweight and must not import any format-specific dependency.

- [ ] **Step 4: Run complete verification**

Run:

```bash
PYTHONPATH=packages/markitdown/src pytest -q packages/markitdown/tests/twoways
PYTHONHASHSEED=1 PYTHONPATH=packages/markitdown/src pytest -q packages/markitdown/tests/twoways/test_markdown_projection.py packages/markitdown/tests/twoways/test_markdown_model_identity.py
PYTHONHASHSEED=777 PYTHONPATH=packages/markitdown/src pytest -q packages/markitdown/tests/twoways/test_markdown_projection.py packages/markitdown/tests/twoways/test_markdown_model_identity.py
python -m compileall -q packages/markitdown/src/markitdown/twoways
```

Then inspect Phase B imports and assert no forbidden format/cloud dependency appears.

Expected: all focused tests PASS; hash-seed projection tests produce the same manifest/Markdown behavior; compileall exits 0; dependency scan is clean.

- [ ] **Step 5: Commit**

```bash
git add packages/markitdown/src/markitdown/twoways packages/markitdown/tests/twoways
git commit -m "feat(twoways): expose verified Markdown round-trip bridge"
```

---

### Task 7: PR evidence and Phase B execution status

**Files:**
- Create: `docs/superpowers/plans/2026-09-08-phase-b-execution-status.md`
- Update PR #1 body/comment with exact evidence.

**Interfaces:**
- No production API change.
- Produces a durable handoff containing exact head SHA, test commands/results, unresolved CI limitations and Phase C prerequisites.

- [ ] **Step 1: Record exact verification facts**

Include only commands actually run and their observed result counts. Do not claim the repository's Python 3.10–3.13 GitHub matrix is green unless workflow runs exist for the exact head SHA.

- [ ] **Step 2: Compare branch against `main`**

Verify branch `behind_by == 0` or document exact drift before continuing.

- [ ] **Step 3: Check exact-head GitHub workflow runs/status**

Use the exact Phase B head SHA. If the fork still produces zero runs/checks, record this as an environment/integration gate, not a code-pass claim.

- [ ] **Step 4: Commit execution status and update PR**

The status must state whether Phase B local focused gates are green and what remains before Phase C/PPTX native reader work begins.
