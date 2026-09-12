# Phase H4 XML Source Preservation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add source-preserving XML 1.0 text and existing-attribute mutation with exact lexical ownership, strict security rejection, encoded untouched-byte proof and candidate re-read verification.

**Architecture:** A pure-Python lexical scanner owns exact source spans, namespace-expanded names and deterministic native paths while `defusedxml.ElementTree` independently cross-checks well-formedness with DTD/entity/external processing forbidden. `DocumentIR` exposes writable capabilities only for normal text and non-namespace attribute value spans; the transactional writer patches only those spans, proves untouched encoded bytes, re-reads the candidate and emits destination bytes only after all checks pass.

**Tech Stack:** Python 3.10+, existing MarkItDown 2Ways IR/capability/readers/writers framework, H1 reversible text codec, `defusedxml`, pytest, pre-commit/Black 23.7.0, GitHub Actions Python 3.10-3.13 package/OCR matrices.

**Spec:** `docs/superpowers/specs/2026-09-12-markitdown-2ways-phase-h4-xml-source-preservation-design.md`

## Global Constraints

- H4 starts from exact-head-green H3 JSON `4501f087d0f46072246a9d88bbf05c85d0108fe7` and stays stacked until H3 integration is resolved.
- Runtime XML support must use the base dependency set; `lxml` is optional and forbidden as an H4 runtime requirement.
- No whole-document XML serialization or pretty printing.
- No DTD, entity declaration, external entity, network fetch or subprocess path.
- XML 1.1 is unsupported in H4.
- No element/attribute insertion, deletion, reorder or rename.
- No namespace declaration/prefix mutation.
- Comments, processing instructions and CDATA are preserved but not writable.
- Direct typed XML edits are authoritative; identity Markdown is inspection-only.
- Destination emission occurs only after source authority, native evidence, encoded untouched-byte proof and strict candidate re-read verification.
- Existing one-way converter registry/API/CLI behavior stays unchanged.
- Exact final head must pass pre-commit plus package and OCR tests on Python 3.10, 3.11, 3.12 and 3.13.

---

### Task 1: XML representation and strict lexical/security scanner

**Files:**
- Create: `packages/markitdown/src/markitdown/twoways/formats/xml/model.py`
- Create: `packages/markitdown/src/markitdown/twoways/formats/xml/lexical.py`
- Create: `packages/markitdown/src/markitdown/twoways/formats/xml/__init__.py`
- Test: `packages/markitdown/tests/twoways/test_xml_lexical.py`
- Test: `packages/markitdown/tests/twoways/test_xml_security.py`

**Interfaces:**
- Produces: `XmlLexicalError`, `XmlDeclaration`, `XmlLexicalNode`, `XmlLexicalDocument`, `decode_xml_source(source: bytes, *, encoding: str | None = None)`, `scan_xml_text(text: str)`, and `parse_xml_source(source: bytes, *, encoding: str | None = None)`.
- `parse_xml_source` returns decoded text, reversible `TextRepresentation`, declaration evidence and lexical document after `defusedxml` cross-check.

- [ ] **Step 1: Write RED lexical tests**

Cover nested elements, same-expanded-name sibling indexing, self-closing elements, attributes with both quote styles, normal text, comments, processing instructions, CDATA, predefined/numeric references, default namespace, prefixed namespace and unprefixed attribute namespace behavior. Assert exact raw spans and deterministic ownership paths.

Representative test shape:

```python
def test_scans_namespaced_xml_with_exact_native_paths() -> None:
    text = '<r xmlns="urn:r" xmlns:m="urn:m"><item m:id="A">x&amp;y</item><item/></r>'
    document = scan_xml_text(text)
    nodes = {node.path: node for node in document.nodes}

    assert "/%7Burn%3Ar%7Dr[1]" in nodes
    assert "/%7Burn%3Ar%7Dr[1]/%7Burn%3Ar%7Ditem[2]" in nodes
    attribute = nodes["/%7Burn%3Ar%7Dr[1]/%7Burn%3Ar%7Ditem[1]/@%7Burn%3Am%7Did"]
    assert attribute.value == "A"
    assert text[attribute.value_start:attribute.value_end] == "A"
```

- [ ] **Step 2: Run the test-only commit and prove RED**

Run through the repository CI matrix. Expected focused failure: import/collection failure because `markitdown.twoways.formats.xml.lexical` does not exist. Preserve the run/job evidence before production implementation.

- [ ] **Step 3: Write RED security/encoding tests**

Assert rejection of XML 1.1, malformed nesting, duplicate attributes, undeclared prefixes, `DOCTYPE`, internal entities, external entities, parameter entities and unsupported markup declarations. Add XML declaration/BOM/signature compatibility tests for UTF-8, UTF-16LE/BE and explicit legacy encodings.

Representative cases:

```python
@pytest.mark.parametrize(
    "source",
    [
        b'<!DOCTYPE r [<!ENTITY x "boom">]><r>&x;</r>',
        b'<!DOCTYPE r SYSTEM "https://example.invalid/a.dtd"><r/>',
        b'<?xml version="1.1"?><r/>',
    ],
)
def test_unsafe_or_unsupported_xml_fails_closed(source: bytes) -> None:
    with pytest.raises(XmlLexicalError):
        parse_xml_source(source)
```

- [ ] **Step 4: Implement immutable lexical/representation model**

Implement dataclasses that validate spans, kinds, raw digests, ownership paths, qnames, expanded names, parent/child paths, semantic values, value spans and attribute quote characters. Reject duplicate paths and malformed root ownership in `XmlLexicalDocument.__post_init__`.

- [ ] **Step 5: Implement XML-specific encoding authority**

Inspect BOM/signatures/declaration before delegating byte decoding to H1 `decode_text_source`; prove declaration/codec compatibility and exact re-encoding. Record exact declaration raw source/digest, XML version, declared encoding and standalone.

- [ ] **Step 6: Implement recursive lexical scanner and namespace scope**

Parse XML declaration, prolog/epilog, elements, attributes, namespace declarations, text, comments, PIs and CDATA without normalizing source. Resolve expanded names under namespace scope and build deterministic percent-encoded ownership paths with one-based sibling/kind indices.

- [ ] **Step 7: Add strict reference/XML-character semantics and defusedxml cross-check**

Decode only five predefined entities and numeric references, enforce XML 1.0 character validity, perform XML newline/attribute normalization needed for H4 semantics, and independently parse with `defusedxml.ElementTree` configured to forbid DTD/entities/external access.

- [ ] **Step 8: Run focused lexical/security suites GREEN and commit**

Run XML-focused tests first, then the full package matrix on at least one Python version before proceeding.

---

### Task 2: Deterministic XML IR and capability boundaries

**Files:**
- Create: `packages/markitdown/src/markitdown/twoways/formats/xml/reader.py`
- Modify: `packages/markitdown/src/markitdown/twoways/ir/edits.py`
- Test: `packages/markitdown/tests/twoways/test_xml_reader.py`

**Interfaces:**
- Consumes: `parse_xml_source` and lexical ownership paths from Task 1.
- Produces: `read_xml_ir(...) -> DocumentIR`, `XmlIRReader`, registered edit types `replace_xml_text` and `replace_xml_attribute`.

- [ ] **Step 1: Write RED deterministic reader tests**

Assert source SHA/size, one `Canvas(kind="xml")`, deterministic node IDs, native locators/provenance, semantic roles, parent/child ownership and canonical digest stability.

- [ ] **Step 2: Write RED capability tests**

Assert normal text exposes writable `replace_xml_text`, non-namespace attributes expose writable `replace_xml_attribute`, elements/namespaces/CDATA are read-only with exact reason codes, and non-roundtrippable representations disable XML write capabilities.

- [ ] **Step 3: Write RED accepts tests**

`XmlIRReader.accepts` must accept only `.xml`, `application/xml`, `text/xml` and reject SVG/XHTML/RSS/generic `+xml`/HTML inputs.

- [ ] **Step 4: Observe RED before registering operations or reader**

Expected failure is missing `formats.xml.reader`/public reader behavior.

- [ ] **Step 5: Implement XML IR mapping and capability metadata**

Map every lexical owner to `Node(kind="unknown_native")`; make only the document root element a canvas root. Preserve attribute/namespace ownership separately from element/text topology through metadata. Generate node IDs from source SHA + lexical kind + native path.

- [ ] **Step 6: Register the two typed edit names**

Add only `replace_xml_text` and `replace_xml_attribute` to the edit-type registry after the RED test exists.

- [ ] **Step 7: Run focused reader suite GREEN and commit**

---

### Task 3: Writer source authority, native evidence and edit preflight

**Files:**
- Create: `packages/markitdown/src/markitdown/twoways/formats/xml/writer.py`
- Test: `packages/markitdown/tests/twoways/test_xml_writer.py`

**Interfaces:**
- Consumes: XML lexical model/reader, `validate_edit_preconditions`, H1 representation primitives.
- Produces: `patch_xml(document, source_stream, output, *, edits=()) -> WriterResult` and internal source/evidence/preflight helpers.

- [ ] **Step 1: Write RED zero-edit/source-authority tests**

Assert zero edits are byte-identical and source SHA/size mismatch fails before output.

- [ ] **Step 2: Write RED native-evidence tests**

Forge path, qname/expanded name, source span, raw digest, parent/children and locator metadata independently; each must fail before candidate construction.

- [ ] **Step 3: Write RED edit contract tests**

Reject wrong operation/node kind, namespace/CDATAs/containers, missing/extra payload fields, non-string values, duplicate targets, invalid XML characters, stale semantic/native preconditions and semantic no-ops.

- [ ] **Step 4: Observe RED because writer is missing**

- [ ] **Step 5: Implement source authority and full native-evidence revalidation**

Reparse the actual bound bytes using recorded representation and compare every lexical owner to IR evidence before processing any edit.

- [ ] **Step 6: Implement complete edit-set preflight**

Validate capabilities, payload shape, typed preconditions, unique targets and requested semantic values without writing or mutating destination state.

- [ ] **Step 7: Run focused writer preflight GREEN and commit**

---

### Task 4: Exact text/attribute rendering and target-only span patching

**Files:**
- Modify: `packages/markitdown/src/markitdown/twoways/formats/xml/writer.py`
- Test: `packages/markitdown/tests/twoways/test_xml_writer.py`

**Interfaces:**
- Produces internal `_render_text_value`, `_render_attribute_value`, and candidate span replacement helpers.

- [ ] **Step 1: Write RED text rendering tests**

Verify `&`, `<`, `>`, Unicode and carriage-return semantics; requested CR must render through `&#13;` and re-read as CR.

- [ ] **Step 2: Write RED attribute rendering tests**

Preserve original `'`/`"` quote style; escape active quote, `&`, `<`, `>`; render requested tab/LF/CR as numeric references so attribute normalization does not alter requested semantics.

- [ ] **Step 3: Write RED multi-target offset tests**

Edit values with longer and shorter rendered tokens in one transaction and assert every unrelated source character stays identical.

- [ ] **Step 4: Implement scalar renderers and independent token semantic validation**

Validate rendered fragments by strict XML parsing in a synthetic safe wrapper before insertion so the renderer cannot introduce malformed markup.

- [ ] **Step 5: Implement sorted exact-span replacement**

Patch only text lexical spans or attribute value spans; reject overlapping targets.

- [ ] **Step 6: Run focused rendering suite GREEN and commit**

---

### Task 5: Encoded untouched-byte proof

**Files:**
- Modify: `packages/markitdown/src/markitdown/twoways/formats/xml/writer.py`
- Test: `packages/markitdown/tests/twoways/test_xml_preservation.py`

**Interfaces:**
- Produces local character-to-byte boundary and untouched-segment verification helpers modeled on proven H3 behavior without prematurely creating a shared abstraction.

- [ ] **Step 1: Write RED representation preservation tests**

Cover UTF-8 BOM, UTF-16LE BOM, UTF-16BE BOM and a reversible legacy encoding whose XML declaration agrees with the codec.

- [ ] **Step 2: Write RED unencodable replacement test**

Use a legacy representation and a replacement outside the codec repertoire. Assert exception before any destination byte is written.

- [ ] **Step 3: Write RED stateful-codec leakage test**

Use an explicitly encoded valid XML source with a stateful codec where possible; monkeypatch/fault-inject encoded candidate bytes if required to prove the verifier rejects any byte drift outside target spans.

- [ ] **Step 4: Implement incremental encoder boundary proof**

Require incremental encoding to equal strict whole-text encoding, then compare BOM and every untouched source/candidate byte segment exactly.

- [ ] **Step 5: Run preservation suite GREEN and commit**

---

### Task 6: Strict candidate re-read verifier

**Files:**
- Modify: `packages/markitdown/src/markitdown/twoways/formats/xml/writer.py`
- Test: `packages/markitdown/tests/twoways/test_xml_verification.py`

**Interfaces:**
- Produces `_verify_candidate(document, candidate, representation, requested)` and integrates it immediately before `output.write`.

- [ ] **Step 1: Write RED candidate drift tests**

Inject candidates with an added/removed path, sibling reorder, namespace binding change, attribute expanded-name change, requested semantic mismatch, unrequested text/reference raw drift and BOM/declaration drift.

- [ ] **Step 2: Observe RED due to missing candidate verifier**

- [ ] **Step 3: Implement strict re-read and path-based topology comparison**

Re-read with recorded encoding; compare ownership paths/kinds, expanded identities, namespace declarations, topology and element order without relying on source-hash-derived node IDs.

- [ ] **Step 4: Verify requested semantics and unrequested raw evidence**

Requested text/attributes must equal typed values. Unrequested leaf/native regions keep raw digest + semantic payload. Do not demand ancestor element raw digest equality across legitimate descendant edits.

- [ ] **Step 5: Verify representation/declaration and emit destination last**

Only after all checks pass may `output.write(candidate)` execute.

- [ ] **Step 6: Run verifier suite and full package regression GREEN; commit**

---

### Task 7: Public adapter, Markdown boundary and one-way regression

**Files:**
- Create: `packages/markitdown/src/markitdown/twoways/formats/xml/writer_adapter.py`
- Modify: `packages/markitdown/src/markitdown/twoways/formats/xml/__init__.py`
- Test: `packages/markitdown/tests/twoways/test_xml_public_imports.py`
- Test: `packages/markitdown/tests/twoways/test_xml_markdown_bridge.py`
- Test: `packages/markitdown/tests/twoways/test_xml_oneway_regression.py`

**Interfaces:**
- Produces stable public `XmlIRReader`, `XmlPatchWriter`, `read_xml_ir`, `patch_xml` surface.

- [ ] **Step 1: Write RED public import and writer-adapter tests**

Verify stable names plus `XmlPatchWriter.accepts` only XML-backed documents and `.xml`/`xml` targets. `write` requires `source_stream=` and `edits=` and forwards no unknown options.

- [ ] **Step 2: Write identity-Markdown inspection-only test**

Project with unknown placeholders enabled and assert every XML manifest block has `editable_capabilities == ()`; importer must not synthesize XML edits.

- [ ] **Step 3: Write one-way regression test**

Instantiate existing `PlainTextConverter` with `.xml`, `application/xml`, `charset="utf-8"`; assert accepts/convert behavior returns the exact decoded source and production one-way code is untouched.

- [ ] **Step 4: Observe RED public adapter boundary**

- [ ] **Step 5: Implement minimal public exports/writer adapter only**

Do not add XML registration into unrelated one-way converter machinery.

- [ ] **Step 6: Run focused/public regression GREEN and commit**

---

### Task 8: Documentation, formatter cleanup and exact-head completion gate

**Files:**
- Modify: `TWOWAYS.md`
- Modify: `docs/superpowers/plans/2026-09-12-phase-h4-xml-source-preservation-implementation.md`
- Modify only if formatter evidence requires it: H4 Python/test files.

**Interfaces:**
- Produces the final exact-head H4 tranche, ready for H5 stacking.

- [ ] **Step 1: Update `TWOWAYS.md` with the proven H4 boundary**

Document direct XML typed edits, strict security boundary, source-preservation proof, unsupported structures and inspection-only Markdown.

- [ ] **Step 2: Mark plan tasks complete only where evidence exists**

No status checkbox may claim a gate that was not observed.

- [ ] **Step 3: Review H3..H4 diff for scope creep**

Confirm no one-way converter/API/CLI mutation, no H1/H2/H3 behavior changes except shared edit-name registry additions, no optional `lxml` runtime dependency, no XML structural editing and no HTML implementation mixed into H4.

- [ ] **Step 4: Run pre-commit on the exact proposed final head**

If Black rewrites files, capture exact formatter output/diff, apply only those changes, restore any temporary diagnostic workflow edits, and create no documentation-only commit after the final green gate.

- [ ] **Step 5: Run package tests Python 3.10-3.13 on the same exact head**

All four jobs must conclude success.

- [ ] **Step 6: Run OCR tests Python 3.10-3.13 on the same exact head**

All four jobs must conclude success.

- [ ] **Step 7: Record completion only after 9/9 exact-head GREEN**

Required final evidence is one successful pre-commit job plus eight successful package/OCR matrix jobs, all associated with the exact same H4 branch head SHA.

## Completion gate

H4 is complete only when the exact final branch head is green across all nine required checks and the standard pre-commit workflow is restored. No docs-only or status-only commit may be added after that observed green head.

After H4, proceed to H5 HTML on a new stacked branch from the verified H4 head. HTML must receive a separate parser-recovery-aware design rather than inheriting XML well-formedness assumptions.