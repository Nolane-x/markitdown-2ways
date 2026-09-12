# Phase H5 HTML Source Preservation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add conservative source-preserving HTML text and quoted-attribute mutation with exact lexical ownership, recovery-stability proof, untouched-byte verification and candidate re-read validation.

**Architecture:** H5 keeps source ownership and parser recovery separate. A pure-Python lexical scanner owns exact source spans, a BeautifulSoup/`html.parser` recovery oracle proves that explicit lexical structure maps one-to-one to recovered structure, and a transactional writer patches only authorized scalar spans before byte-preservation and candidate-recovery verification.

**Tech Stack:** Python 3.10+, existing MarkItDown 2Ways IR/capability/readers/writers framework, H1 reversible text codec primitives, `beautifulsoup4`, Python `html`/`html.parser` helpers where safe, pytest, pre-commit/Black 23.7.0, GitHub Actions Python 3.10-3.13 package/OCR matrices.

**Spec:** `docs/superpowers/specs/2026-09-12-markitdown-2ways-phase-h5-html-source-preservation-design.md`

## Global Constraints

- H5 starts from exact-head-green H4 XML `9c927af2ca964864ecad0c186c44e34525f04de0` and stays stacked until H4 integration is resolved.
- Existing one-way `HtmlConverter`, converter registry, CLI and public one-way API remain unchanged.
- No DOM serializer, pretty-printer or BeautifulSoup writeback may emit production bytes.
- No browser execution, JavaScript/CSS evaluation, resource loading, URL resolution, network fetch or subprocess path.
- Native writable acceptance is only `.html`, `.htm` and `text/html`; XHTML/XML/foreign-content mutation is excluded.
- First-tranche writes are only normal data-state text and existing quoted non-duplicate attribute values.
- Unquoted/boolean/duplicate attributes, rawtext, RCDATA, template, foreign content and recovery-sensitive structure are read-only.
- Direct typed HTML edits are authoritative; identity Markdown is inspection-only.
- Destination emission occurs only after source authority, native evidence, encoded untouched-byte proof, lexical candidate re-read and recovery-signature verification.
- Exact final head must pass pre-commit plus package and OCR tests on Python 3.10, 3.11, 3.12 and 3.13.

---

### Task 1: HTML representation, lexical ownership and recovery stability

**Files:**
- Create: `packages/markitdown/src/markitdown/twoways/formats/html/__init__.py`
- Create: `packages/markitdown/src/markitdown/twoways/formats/html/model.py`
- Create: `packages/markitdown/src/markitdown/twoways/formats/html/codec.py`
- Create: `packages/markitdown/src/markitdown/twoways/formats/html/lexical.py`
- Create: `packages/markitdown/src/markitdown/twoways/formats/html/recovery.py`
- Test: `packages/markitdown/tests/twoways/test_html_lexical.py`
- Test: `packages/markitdown/tests/twoways/test_html_recovery.py`

**Interfaces:**
- Produces `HtmlLexicalError`, `HtmlLexicalNode`, `HtmlLexicalDocument`, `ParsedHtmlSource`, `HtmlRecoverySignature`.
- Produces `decode_html_source(source: bytes, *, encoding: str | None = None) -> tuple[str, TextRepresentation, tuple[HtmlEncodingDeclaration, ...]]`.
- Produces `scan_html_text(text: str) -> HtmlLexicalDocument`.
- Produces `build_recovery_signature(text: str) -> HtmlRecoverySignature` and `parse_html_source(source: bytes, *, encoding: str | None = None) -> ParsedHtmlSource`.

- [ ] **Step 1: Write RED lexical ownership tests**

Cover stable nested HTML, mixed source tag/attribute case, void elements, doctype, comments, both attribute quote styles, boolean/unquoted attributes, text owners and named/numeric character references. Assert exact spans/raw source, normalized names and stable paths.

Representative test:

```python
def test_scans_stable_html_with_exact_paths() -> None:
    text = '<HTML><body><p CLASS="hero">A&amp;B<br>tail</p></body></HTML>'
    document = scan_html_text(text)
    nodes = {node.path: node for node in document.nodes}

    assert "/html[1]/body[1]/p[1]" in nodes
    attribute = nodes["/html[1]/body[1]/p[1]/@class"]
    assert attribute.qname == "CLASS"
    assert attribute.normalized_name == "class"
    assert text[attribute.value_start:attribute.value_end] == "hero"
    assert nodes["/html[1]/body[1]/p[1]/#text[1]"].value == "A&B"
```

- [ ] **Step 2: Commit the tests alone and observe RED**

Expected failure: collection/import failure because `markitdown.twoways.formats.html` production modules do not exist.

- [ ] **Step 3: Add RED encoding authority tests**

Cover UTF-8/BOM, explicit legacy encoding, one unambiguous `<meta charset>`, compatible explicit/meta evidence, conflicting explicit/meta evidence, conflicting multiple meta declarations and non-roundtrippable readable sources.

- [ ] **Step 4: Add RED recovery-stability tests**

Stable explicit nesting must produce a lexical/recovered one-to-one mapping. Cases requiring implied closes, mismatched/unclosed tags, nested `<p>`, recovery-sensitive list omission, table foster/implied-container behavior, template and SVG/MathML must return `recovery_stable=False` with a deterministic reason.

Representative cases:

```python
@pytest.mark.parametrize(
    "text",
    [
        "<p>one<p>two",
        "<table><td>x</td></table>",
        "<template><p>x</p></template>",
        "<svg><text>x</text></svg>",
    ],
)
def test_recovery_sensitive_html_is_not_writable(text: str) -> None:
    parsed = parse_html_source(text.encode("utf-8"))
    assert parsed.recovery_stable is False
    assert parsed.recovery_reason is not None
```

- [ ] **Step 5: Implement immutable lexical/representation model**

Validate unique paths, source spans, value spans, quote values, normalized names, parent/children ownership, raw digests and read-only recovery reasons in frozen dataclasses.

- [ ] **Step 6: Implement HTML encoding authority**

Reuse H1 decoding primitives after conservatively discovering HTML meta-encoding declarations from an initial ASCII-compatible byte prefix. Preserve BOM/codec exactness, record declaration spans/raw digests, reject conflicting authority for writes and keep readable-but-nonroundtrippable sources inspection-only.

- [ ] **Step 7: Implement the conservative HTML lexical scanner**

Recognize explicit elements, exact start/end tag spans, HTML void elements, comments, doctype, quoted/unquoted/boolean attributes, normal text, script/style rawtext and title/textarea RCDATA. Normalize ASCII HTML names without changing source spelling. Reject ambiguous malformed token boundaries.

- [ ] **Step 8: Implement independent recovery signature and stability gate**

Use `BeautifulSoup(text, "html.parser")` only to build a deterministic structural signature. Compare explicit lexical structure against recovered tag nesting/order/name/attribute-name sets. Mark known recovery-sensitive constructs read-only even when BeautifulSoup accepts them.

- [ ] **Step 9: Run focused lexical/recovery suites GREEN and commit**

Run at least one full package Python job after focused GREEN before Task 2.

---

### Task 2: Deterministic HTML IR and capability boundaries

**Files:**
- Create: `packages/markitdown/src/markitdown/twoways/formats/html/reader.py`
- Modify: `packages/markitdown/src/markitdown/twoways/ir/edits.py`
- Test: `packages/markitdown/tests/twoways/test_html_reader.py`

**Interfaces:**
- Consumes `ParsedHtmlSource` from Task 1.
- Produces `read_html_ir(...) -> DocumentIR`, `HtmlIRReader` and edit types `replace_html_text` / `replace_html_attribute`.

- [ ] **Step 1: Write RED deterministic reader tests**

Assert source descriptor SHA/size, `Canvas(kind="html")`, deterministic node IDs, native locators/provenance, normalized/source-name metadata, parent/child ownership and canonical digest stability for recovery-stable input.

- [ ] **Step 2: Write RED capability tests**

Assert only normal text and quoted non-duplicate attributes become writable. Assert exact read-only reason codes for elements, unquoted/boolean/duplicate attrs, rawtext, RCDATA, template/foreign/table-sensitive cases, unstable recovery and non-roundtrippable encoding.

- [ ] **Step 3: Write RED read-only fallback tests**

Recovery-unstable but deterministically readable HTML must return a single document-level `unknown_native` root with `html.recovery_stable=False`, the disabling reason and no writable H5 capability. It must not publish forged fine-grained native locators.

- [ ] **Step 4: Write RED accepts tests**

`HtmlIRReader.accepts` accepts `.html`, `.htm`, `text/html`; rejects XHTML/XML/SVG/RSS/generic `+xml` surfaces.

- [ ] **Step 5: Observe RED before reader/edit registration**

Expected failure is missing `formats.html.reader` / missing H5 edit-type registration.

- [ ] **Step 6: Implement stable fine-grained IR plus read-only fallback**

For stable input map lexical owners to `unknown_native` nodes. For unstable input emit only a document-level read-only root. Node IDs use source SHA + lexical kind + path; candidate verification later compares by path.

- [ ] **Step 7: Register exactly two H5 edit names**

Add `replace_html_text` and `replace_html_attribute` to `INITIAL_EDIT_TYPES` only after the RED tests exist.

- [ ] **Step 8: Run reader suite GREEN and commit**

---

### Task 3: Writer source authority, native evidence and complete edit preflight

**Files:**
- Create: `packages/markitdown/src/markitdown/twoways/formats/html/writer.py`
- Test: `packages/markitdown/tests/twoways/test_html_writer.py`

**Interfaces:**
- Produces `patch_html(document, source_stream, output, *, edits=()) -> WriterResult` and internal source/native/preflight helpers.

- [ ] **Step 1: Write RED zero-edit/source-authority tests**

Assert zero edits are byte-identical and source SHA/size mismatch fails before destination write.

- [ ] **Step 2: Write RED native-evidence forgery tests**

Forge path, kind, normalized/source name, source span, value span, quote, raw digest, parent/children, recovery signature metadata and native locator independently; each must fail before candidate construction.

- [ ] **Step 3: Write RED edit contract tests**

Reject wrong operation/kind pairs, read-only owners, missing/extra payload fields, non-string value, duplicate targets, stale semantic/native/old-value preconditions and semantic no-ops.

- [ ] **Step 4: Observe RED because writer is missing**

- [ ] **Step 5: Implement source authority and source-model revalidation**

Re-read the actual supplied bytes under recorded representation. Compare IR evidence against a freshly built H5 source model and require recovery-stable fine-grained ownership before any edit is accepted.

- [ ] **Step 6: Implement all-edit preflight**

Resolve every target by `html.path`, validate capability state, exact payload shape, operation/kind pair, typed preconditions, unique targets and requested semantic value before rendering any candidate.

- [ ] **Step 7: Run focused preflight suite GREEN and commit**

---

### Task 4: Exact scalar rendering and target-only span patching

**Files:**
- Create: `packages/markitdown/src/markitdown/twoways/formats/html/render.py`
- Modify: `packages/markitdown/src/markitdown/twoways/formats/html/writer.py`
- Test: `packages/markitdown/tests/twoways/test_html_writer.py`

**Interfaces:**
- Produces `render_html_text(value: str) -> str`, `render_html_attribute(value: str, quote: str) -> str` and exact replacement-span candidate construction.

- [ ] **Step 1: Write RED text renderer tests**

Verify `&`, `<`, `>`, Unicode and CR semantics. Rendered fragments must parse back to exactly the requested semantic text without creating markup owners.

- [ ] **Step 2: Write RED quoted-attribute renderer tests**

Preserve original `'`/`"` style and safely encode active quote, `&`, `<`, `>`, tab/LF/CR. Boolean/unquoted attributes remain outside renderer write support.

- [ ] **Step 3: Write RED multi-target offset tests**

Replace several text/attribute values with longer and shorter tokens in one transaction. Assert source characters outside target spans remain identical before encoding.

- [ ] **Step 4: Implement independent safe-wrapper semantic checks**

Validate each rendered fragment through the H5 parser in a synthetic stable wrapper and require recovered semantic equality before candidate insertion.

- [ ] **Step 5: Implement sorted exact-span replacement**

Patch only normal text owner spans or quoted attribute value spans; reject overlapping target spans.

- [ ] **Step 6: Run rendering suite GREEN and commit**

---

### Task 5: Encoded untouched-byte preservation proof

**Files:**
- Create: `packages/markitdown/src/markitdown/twoways/formats/html/preservation.py`
- Modify: `packages/markitdown/src/markitdown/twoways/formats/html/writer.py`
- Test: `packages/markitdown/tests/twoways/test_html_preservation.py`

**Interfaces:**
- Produces character-to-byte boundary helpers and `verify_html_untouched_bytes(...)`.

- [ ] **Step 1: Write RED representation preservation tests**

Cover UTF-8 BOM, UTF-16LE/BE where accepted by H5 decoding authority, and one reversible legacy encoding with compatible meta declaration.

- [ ] **Step 2: Write RED unencodable replacement test**

A replacement outside a legacy codec repertoire must fail before any destination bytes are written.

- [ ] **Step 3: Write RED byte-drift fault-injection test**

Fault-inject a candidate byte outside an authorized target span and require `RoundTripVerificationError`.

- [ ] **Step 4: Implement incremental encoder boundary proof**

Require incremental encoding to equal strict whole-text encoding; preserve BOM/signature and compare every untouched source/candidate byte segment exactly.

- [ ] **Step 5: Run preservation suite GREEN and commit**

---

### Task 6: Strict lexical + recovery candidate verifier

**Files:**
- Create: `packages/markitdown/src/markitdown/twoways/formats/html/verification.py`
- Modify: `packages/markitdown/src/markitdown/twoways/formats/html/writer.py`
- Test: `packages/markitdown/tests/twoways/test_html_verification.py`

**Interfaces:**
- Produces `verify_html_candidate(document, candidate, representation, requested)` and runs it immediately before destination write.

- [ ] **Step 1: Write RED candidate drift tests**

Fault-inject added/removed lexical paths, tag-name drift, parent/child reorder, quote-style drift, recovery-signature drift, requested semantic mismatch, unrequested raw/reference drift and encoding/meta declaration drift.

- [ ] **Step 2: Observe RED because candidate verifier is absent**

- [ ] **Step 3: Implement path-based lexical topology comparison**

Re-read the candidate using recorded encoding. Require stable fine-grained ownership, identical path/kind/name/topology sets and unchanged quoted attribute shapes.

- [ ] **Step 4: Compare recovery signatures**

Require the independent BeautifulSoup structural signature to match source structure after excluding requested scalar values. Any recovered structure drift is fatal.

- [ ] **Step 5: Verify requested semantics and unrequested raw evidence**

Requested owners must equal typed values. Every unrequested scalar/comment/doctype/rawtext/rcdata owner keeps raw digest and semantic payload. Do not require ancestor element raw digest equality across legitimate descendant edits.

- [ ] **Step 6: Integrate verifier before `output.write` and run full package regression GREEN**

Commit only after verifier-focused tests and at least one complete package job pass.

---

### Task 7: Public adapter, identity-Markdown boundary and one-way regression

**Files:**
- Create: `packages/markitdown/src/markitdown/twoways/formats/html/writer_adapter.py`
- Modify: `packages/markitdown/src/markitdown/twoways/formats/html/__init__.py`
- Test: `packages/markitdown/tests/twoways/test_html_public_imports.py`
- Test: `packages/markitdown/tests/twoways/test_html_markdown_bridge.py`
- Test: `packages/markitdown/tests/twoways/test_html_oneway_regression.py`

**Interfaces:**
- Produces stable public `HtmlIRReader`, `HtmlPatchWriter`, `read_html_ir`, `patch_html` surface.

- [ ] **Step 1: Write RED public import/writer-adapter tests**

Verify stable names; adapter accepts only HTML-backed documents plus target `html` or `.html`/`.htm`; `write` requires `source_stream=` and `edits=` and rejects unknown options.

- [ ] **Step 2: Write identity-Markdown inspection-only tests**

Project HTML IR with unknown placeholders and assert every manifest block has `editable_capabilities == ()`; unchanged identity import emits no edits.

- [ ] **Step 3: Write current one-way regression tests**

Instantiate the existing `HtmlConverter` for `.html`/`text/html`; assert current accepts/convert behavior for a stable document and confirm no H5 code is registered into one-way converter machinery.

- [ ] **Step 4: Observe RED public adapter boundary**

Expected failure: public H5 exports/adapter absent.

- [ ] **Step 5: Implement minimal adapter and exports only**

Do not modify `_html_converter.py`, converter registry, CLI or one-way API.

- [ ] **Step 6: Run public/Markdown/one-way tests and full package/OCR regression GREEN; commit**

---

### Task 8: Documentation, scope audit, formatter cleanup and exact-head completion gate

**Files:**
- Modify: `TWOWAYS.md`
- Modify only before the final gate: H5 implementation/test files if formatter evidence requires it.

**Interfaces:**
- Produces the final H5/v0.5 structured-text tranche ready for the next release-program phase.

- [ ] **Step 1: Update `TWOWAYS.md` with the proven H5 boundary**

Document direct typed HTML text/quoted-attribute edits, lexical/recovery safety model, preservation proof, recovery-sensitive read-only cases, identity-Markdown inspection-only status and unchanged one-way behavior.

- [ ] **Step 2: Audit H4..H5 diff for scope creep**

Confirm no one-way converter/API/CLI edits, no H1-H4 behavioral changes except two shared edit names, no browser/network/subprocess path, no DOM serializer writeback, no XHTML/SVG/MathML mutation and no v0.6 work mixed into H5.

- [ ] **Step 3: Run pre-commit on the exact proposed final head**

If Black modifies files, capture exact formatter output and commit only those changes before the final verification head. Restore any temporary diagnostic workflow changes before final verification.

- [ ] **Step 4: Run package tests Python 3.10-3.13 on the same exact head**

All four package jobs must conclude success.

- [ ] **Step 5: Run OCR tests Python 3.10-3.13 on the same exact head**

All four OCR jobs must conclude success.

- [ ] **Step 6: Record completion only after 9/9 exact-head GREEN**

Required evidence is one successful pre-commit job plus eight successful package/OCR jobs, all associated with the exact same H5 branch head SHA. No docs-only/status-only commit may be added after that observed green head.

## Completion gate

H5 is complete only when the exact final branch head is green across all nine required checks with the standard pre-commit workflow present. That exact head becomes the v0.5 text/structured-parity completion point; subsequent v0.6 notebook/publication/container work must start on a new branch.