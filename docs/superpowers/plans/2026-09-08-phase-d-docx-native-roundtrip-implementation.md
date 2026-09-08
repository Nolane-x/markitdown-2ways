# Phase D DOCX Native Round-Trip Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a production-oriented DOCX reader and fail-closed minimal WordprocessingML patch writer that round-trips identity Markdown edits while preserving unrelated package members and native XML structures.

**Architecture:** Reuse the shared `twoways.ooxml` package as the ZIP/OPC preservation authority. Read DOCX semantics into `DocumentIR` using raw WordprocessingML plus `python-docx` only as an optional semantic/readback helper; apply typed edits by mutating only explicitly targeted XML parts and verify untouched members, unrelated native subtrees, native locators, and semantic readback.

**Tech Stack:** Python 3.10+, `python-docx`, `lxml`, `zipfile`, existing MarkItDown 2Ways Core IR/Markdown/OOXML modules, pytest.

**Spec:** `docs/superpowers/specs/2026-09-08-markitdown-2ways-phase-d-docx-native-roundtrip-design.md`

## Global Constraints

- Patch mode always starts from the exact original DOCX source bytes and validates the authoritative source SHA-256.
- No-op output must be byte-for-byte identical to input.
- Node identity must not depend on source SHA or editable text content.
- Body paragraph/run text, header/footer text, hyperlink text, and picture alt text are patchable in v1.
- Tables are semantic read-only in v1.
- Hyperlink URL/relationship targets are never changed by `replace_text`.
- Paragraph/run/hyperlink native wrappers and run properties are preserved; patching mutates compatible existing `w:t` nodes only.
- Unsupported fields, content controls, tracked revisions, equations, comments, footnotes/endnotes, section/style/numbering mutations, and ambiguous native structures fail closed.
- Untouched ZIP member uncompressed content must remain byte-identical after an edit.
- Unrelated native subtrees inside a touched XML part must remain canonically identical.
- Root `import markitdown.twoways` must not eagerly import `docx` or `lxml`.
- Tests use real in-memory DOCX packages, not mocks of the package format.

---

## File map

Production files:

- `packages/markitdown/src/markitdown/twoways/formats/docx/__init__.py` — lazy public format surface.
- `packages/markitdown/src/markitdown/twoways/formats/docx/model.py` — read/patch options.
- `packages/markitdown/src/markitdown/twoways/formats/docx/relationships.py` — safe relationship parsing/target resolution.
- `packages/markitdown/src/markitdown/twoways/formats/docx/locators.py` — stable structural locators and exact native resolution.
- `packages/markitdown/src/markitdown/twoways/formats/docx/text.py` — paragraph/run extraction and context-preserving `w:t` patching.
- `packages/markitdown/src/markitdown/twoways/formats/docx/reader.py` — DOCX package -> `DocumentIR`.
- `packages/markitdown/src/markitdown/twoways/formats/docx/patch.py` — shared edit precondition and picture alt-text mutation helpers.
- `packages/markitdown/src/markitdown/twoways/formats/docx/verify.py` — package/native/semantic verification.
- `packages/markitdown/src/markitdown/twoways/formats/docx/writer.py` — source-locked sparse writer.
- `packages/markitdown/src/markitdown/twoways/formats/docx/structures.py` — table/image/paragraph builders for body/header/footer parts.
- `packages/markitdown/src/markitdown/twoways/formats/__init__.py` — remains dependency-light; no eager DOCX import.

Test files:

- `packages/markitdown/tests/twoways/_docx_fixtures.py`
- `packages/markitdown/tests/twoways/test_docx_relationships_locators.py`
- `packages/markitdown/tests/twoways/test_docx_reader.py`
- `packages/markitdown/tests/twoways/test_docx_text_patch.py`
- `packages/markitdown/tests/twoways/test_docx_roundtrip.py`
- `packages/markitdown/tests/twoways/test_docx_public_imports.py`

---

### Task 1: Real DOCX fixture and format contracts

**Files:**
- Create: `packages/markitdown/src/markitdown/twoways/formats/docx/__init__.py`
- Create: `packages/markitdown/src/markitdown/twoways/formats/docx/model.py`
- Create: `packages/markitdown/tests/twoways/_docx_fixtures.py`
- Create: `packages/markitdown/tests/twoways/test_docx_public_imports.py`

**Interfaces:**
- Produces `DocxReadOptions`, `DocxPatchOptions`, lazy `read_docx_ir()` and `patch_docx()`.
- Fixture `build_docx_fixture()` returns bytes for a document containing formatted body text, an external hyperlink, table, header, footer, and inline picture with alt text.

- [ ] Write failing public-import/fixture tests proving the DOCX package does not yet exist.
- [ ] Run `PYTHONPATH=packages/markitdown/src pytest -q packages/markitdown/tests/twoways/test_docx_public_imports.py` and confirm RED due to missing module/contracts.
- [ ] Implement dependency-light public surface and frozen options using shared `OOXMLPackageLimits`.
- [ ] Build fixture using `python-docx`; construct hyperlink with its relationship and WordprocessingML wrapper; embed a tiny in-memory PNG; set `wp:docPr@descr` in the fixture XML.
- [ ] Re-run test and require GREEN.

### Task 2: Relationship parser and structural native locators

**Files:**
- Create: `packages/markitdown/src/markitdown/twoways/formats/docx/relationships.py`
- Create: `packages/markitdown/src/markitdown/twoways/formats/docx/locators.py`
- Create: `packages/markitdown/tests/twoways/test_docx_relationships_locators.py`

**Interfaces:**
- `relationships_for_part(snapshot, part_uri) -> Mapping[str, DocxRelationship]`.
- `resolve_relationship_target(part_uri, target) -> str` rejects traversal outside the package root.
- `paragraph_locator(part_uri, paragraph_index, path) -> NativeLocator`.
- `picture_locator(part_uri, docpr_id, relationship_id, path) -> NativeLocator`.
- `stable_docx_node_id(locator, kind) -> str` hashes only stable native identity/location.
- `resolve_paragraph_element(root, locator, part_uri)` and `resolve_picture_docpr(root, locator, part_uri)` require exact designated part and unique structural identity.

- [ ] Write RED tests for external hyperlink relationship parsing, relative media target resolution, wrong-part rejection, duplicate/ambiguous locator rejection, and node-id stability under text edits.
- [ ] Implement relationship parsing from the corresponding `.rels` member using XXE-safe `parse_xml_part`.
- [ ] Implement stable structural paths based on paragraph/table position and `wp:docPr@id` for pictures.
- [ ] Re-run locator/relationship tests and require GREEN.

### Task 3: WordprocessingML text extraction and context-safe patch algorithm

**Files:**
- Create: `packages/markitdown/src/markitdown/twoways/formats/docx/text.py`
- Create: `packages/markitdown/tests/twoways/test_docx_text_patch.py`

**Interfaces:**
- `extract_paragraph_payload(paragraph_element, locator) -> TextPayload`.
- Each `TextRun.native_locator.attributes` records `run_index`, `hyperlink_relationship_id`, and a deterministic context index.
- `paragraph_patch_compatible(paragraph_element) -> bool` rejects fields, tracked revisions, unsupported control nodes, breaks, drawings mixed into text, and ambiguous run structures.
- `patch_paragraph_text(paragraph_element, old_text, new_text)` mutates only existing compatible `w:t` nodes.

**Patch rules:**
- Existing `w:r`, `w:rPr`, `w:hyperlink`, and relationship IDs are not added/deleted/reordered.
- Text nodes are grouped into contiguous native contexts: plain text or one specific hyperlink relationship.
- SequenceMatcher edits must fall wholly within one existing context. Insertions exactly on a context boundary are ambiguous and fail closed unless both adjacent contexts are identical.
- Allocation within a context follows existing run ownership so inserted characters inherit the nearest compatible run style.
- Paragraph count is invariant in v1.

- [ ] Write RED tests for formatted multi-run replacement, hyperlink-label replacement preserving `r:id`, boundary-crossing failure, field failure, no-style-context failure, and unchanged `w:rPr` canonical bytes.
- [ ] Implement extraction of direct run styles from `w:rPr` without requiring style resolution.
- [ ] Implement context segmentation and context-safe allocation.
- [ ] Apply `xml:space="preserve"` only when necessary after mutation.
- [ ] Re-run text patch tests and require GREEN.

### Task 4: DOCX reader for body/header/footer/table/picture

**Files:**
- Create: `packages/markitdown/src/markitdown/twoways/formats/docx/structures.py`
- Create: `packages/markitdown/src/markitdown/twoways/formats/docx/reader.py`
- Create: `packages/markitdown/tests/twoways/test_docx_reader.py`

**Interfaces:**
- `read_docx_ir(file_stream, stream_info=None, options=None) -> DocumentIR`.
- `DocxIRReader` implements `DocumentIRReader` lazily.
- Body is canvas `docx-body` kind `document`.
- Header/footer XML parts become additional canvases in deterministic relationship/part order.
- Paragraph nodes are `kind="text"` with `docx:patch_text_compatible` metadata.
- Tables become `TablePayload` and advertise no patch capability.
- Inline pictures become `ImagePayload` with media `Resource`, relationship evidence, and patchable alt text when `wp:docPr` identity is unique.

- [ ] Write RED tests for source SHA authority, body order, formatted runs, hyperlink evidence, table cells, header/footer canvases, picture resource/alt text, and stable paragraph/picture node IDs after editing only text in a regenerated copy.
- [ ] Implement package part discovery from `[Content_Types].xml` and document/header/footer relationships rather than filename guessing alone.
- [ ] Parse body/header/footer with shared safe XML parser.
- [ ] Build deterministic nodes/resources/canvases and validate the `DocumentIR`.
- [ ] Re-run reader tests and require GREEN.

### Task 5: Source/precondition guards and picture alt-text patch

**Files:**
- Create: `packages/markitdown/src/markitdown/twoways/formats/docx/patch.py`
- Extend: `packages/markitdown/tests/twoways/test_docx_relationships_locators.py`

**Interfaces:**
- `validate_edit_preconditions(document, node, edit)` uses shared semantic/native locator digests.
- `patch_picture_alt_text(docpr_element, new_alt_text)` mutates only `descr`.

- [ ] Write RED tests for source semantic/native/old-value preconditions and alt-text mutation isolation.
- [ ] Implement fail-closed precondition checks analogous to PPTX but DOCX-specific messages/codes.
- [ ] Implement `wp:docPr@descr` mutation and reject ambiguous/missing docPr locators.
- [ ] Re-run targeted tests and require GREEN.

### Task 6: Sparse DOCX writer vertical slice

**Files:**
- Create: `packages/markitdown/src/markitdown/twoways/formats/docx/writer.py`
- Create: `packages/markitdown/tests/twoways/test_docx_roundtrip.py`

**Interfaces:**
- `patch_docx(document, source_stream, output_stream, edits, options=None) -> WriterResult`.
- `DocxPatchWriter` implements `DocumentWriter` lazily.

**Flow:**
1. Validate IR and exact source SHA/format.
2. Return source bytes unchanged for empty edit list.
3. Group operations by `native_locator.part_uri`.
4. Parse each touched XML part once.
5. Resolve exact target and apply only supported operation.
6. Serialize only touched parts and call shared sparse `write_package`.
7. Run post-write verifier before returning success.

- [ ] Write RED tests for no-op byte identity, one body text edit changing only `word/document.xml`, header text edit changing only the header part, footer text edit changing only footer part, picture alt text changing only containing XML part, and Markdown identity -> typed edit -> DOCX integration.
- [ ] Implement source authority validation and touched-part grouping.
- [ ] Implement `replace_text` and `set_alt_text`; all other edit types raise `UnsupportedEditError`.
- [ ] Re-run round-trip tests and require GREEN.

### Task 7: Fidelity verifier and unrelated native subtree protection

**Files:**
- Create: `packages/markitdown/src/markitdown/twoways/formats/docx/verify.py`
- Extend: `packages/markitdown/tests/twoways/test_docx_roundtrip.py`

**Interfaces:**
- `verify_docx_output(source_bytes, output_bytes, source_document, edits, touched_parts, options) -> FidelityReport`.

**Required evidence:**
- output reopens with `python-docx` when dependency is present;
- edited targets reread to requested semantic values;
- all untouched package members have identical uncompressed bytes;
- hyperlink relationships remain unchanged for text edits;
- media bytes remain unchanged for text/alt edits;
- all unrelated paragraph/table/picture native subtrees inside touched parts remain canonically identical;
- target paragraph wrappers (`w:r`, `w:rPr`, `w:hyperlink`) preserve their structural signature except text content.

- [ ] Write a RED adversarial test that mutates an unrelated paragraph attribute in the touched part while semantic text remains unchanged; verifier must catch it.
- [ ] Implement canonical subtree fingerprinting that strips only text-node content for the explicitly targeted paragraph when checking its wrapper structure.
- [ ] Add fidelity evidence codes such as `docx.package.untouched_members`, `docx.native.unrelated_subtrees`, `docx.hyperlinks.relationships`, `docx.semantic.readback`.
- [ ] Re-run verifier/integration tests and require GREEN.

### Task 8: Public surface, deterministic regression, and final verification

**Files:**
- Modify only if needed: `packages/markitdown/src/markitdown/twoways/formats/docx/__init__.py`
- Extend: `packages/markitdown/tests/twoways/test_docx_public_imports.py`

- [ ] Verify root import remains dependency-light: after `import markitdown.twoways`, neither `docx` nor `lxml` is present in `sys.modules` unless previously imported.
- [ ] Run full isolated suite: `PYTHONPATH=packages/markitdown/src pytest -q packages/markitdown/tests/twoways`.
- [ ] Run the full isolated suite with `PYTHONHASHSEED=1` and `PYTHONHASHSEED=777`.
- [ ] Run `python -m compileall -q packages/markitdown/src/markitdown/twoways packages/markitdown/tests/twoways`.
- [ ] Parse every Phase A-D Python file with `ast.parse(..., feature_version=(3, 10))`.
- [ ] Scan DOCX modules for network/process side-effect imports and assert none are present.
- [ ] Compare local Git blob SHAs for all Phase D changed files with the blobs staged for the GitHub commit before moving the PR branch ref.
- [ ] After exact-head publish, query PR metadata, commit statuses, and pull-request workflow runs. Do not claim repository-wide CI green if GitHub produces no evidence.
