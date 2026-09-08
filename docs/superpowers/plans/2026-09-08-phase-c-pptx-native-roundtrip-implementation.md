# Phase C Native PPTX Round-Trip Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver the first production vertical slice that reads a PPTX into `DocumentIR`, accepts typed `replace_text`/`set_alt_text` edits, patches only the necessary OOXML slide part, and verifies the output without rebuilding the deck.

**Architecture:** Use `python-pptx` only for semantic/object access and post-write reopen checks. Treat the original ZIP/OPC package as preservation authority, mutate narrowly scoped OOXML with safe `lxml`, and write a new package from the original member inventory plus a sparse replacement map. Source SHA locks authority; node IDs are document-local native-location identities and deliberately do **not** include the mutable source SHA.

**Tech Stack:** Python 3.10+, stdlib `zipfile`, `hashlib`, `io`, `difflib`; optional `python-pptx`; optional `lxml`; existing MarkItDown 2Ways IR, Markdown bridge, errors and fidelity contracts; pytest.

**Spec:** `docs/superpowers/specs/2026-09-08-markitdown-2ways-phase-c-pptx-native-roundtrip-design.md`

## Global Constraints

- Existing `MarkItDown.convert()`, converters and CLI remain unchanged.
- `import markitdown.twoways` must not import `pptx` or `lxml`.
- Patch mode always requires the original source PPTX and verifies `DocumentIR.source.sha256` before trusting locators.
- Patch mode never silently falls back to a rebuild.
- Empty edit sets copy the original source bytes exactly.
- Edited output preserves every untouched ZIP member's uncompressed bytes exactly.
- Phase C v1 mutates only `replace_text` and `set_alt_text` on patch-compatible nodes.
- Adding/removing paragraphs, editing tables/charts/media, changing relationships, masters/layouts/themes or animations is unsupported in v1.
- Shape identity is scoped by `part_uri`; strict mode never authorizes a patch by name alone.
- If both `creation_id` and `object_id` are present, both must resolve to the same shape.
- XML parsing disables entity resolution, DTD loading and network access.
- ZIP member paths are never extracted to filesystem paths and traversal/duplicates/encryption/limit violations fail closed.
- Node IDs are derived from stable native evidence (`part_uri + creationId/shape_id + kind`) and **must not** depend on the source archive digest; source digest is authority evidence only.

---

### Task 1: Move format-agnostic semantic digest helpers into Core IR

**Files:**
- Create: `packages/markitdown/src/markitdown/twoways/ir/semantics.py`
- Modify: `packages/markitdown/src/markitdown/twoways/markdown/semantics.py`
- Test: `packages/markitdown/tests/twoways/test_ir_semantics.py`

**Interfaces:**
- Produces `stable_digest(value)`, `node_semantic_text(node)`, `node_semantic_digest(node)`, `native_locator_digest(node)`.
- Keeps Phase B compatibility aliases `semantic_text_for_node` and `source_semantic_digest` with identical digest bytes.

- [ ] **Step 1: Write failing regression tests** that import the helpers from `markitdown.twoways.ir.semantics` and assert the known representative fixture digest equals the current Phase B digest.
- [ ] **Step 2: Run the test** with `PYTHONPATH=packages/markitdown/src pytest -q packages/markitdown/tests/twoways/test_ir_semantics.py` and verify RED because the module does not exist.
- [ ] **Step 3: Implement Core IR helpers** by moving only format-agnostic logic. Keep `normalize_markdown_block()` in the Markdown module and re-export compatibility names there.
- [ ] **Step 4: Run Phase A+B tests** and verify no projection/import digest changes.
- [ ] **Step 5: Commit** `refactor(twoways): share semantic digest helpers`.

---

### Task 2: Safe OOXML package snapshot and sparse writer

**Files:**
- Create: `packages/markitdown/src/markitdown/twoways/ooxml/__init__.py`
- Create: `packages/markitdown/src/markitdown/twoways/ooxml/limits.py`
- Create: `packages/markitdown/src/markitdown/twoways/ooxml/package.py`
- Create: `packages/markitdown/src/markitdown/twoways/ooxml/xml.py`
- Modify: `packages/markitdown/src/markitdown/twoways/_errors.py`
- Test: `packages/markitdown/tests/twoways/test_ooxml_package.py`

**Interfaces:**
- Produces immutable `OOXMLPackageLimits`, `OOXMLPackageEntry`, `OOXMLPackageSnapshot`.
- Produces `snapshot_package(source_bytes, *, limits=None)` and `write_package(snapshot, source_bytes, output, *, replacements)`.
- Produces `parse_xml_part(data)` and `serialize_xml_part(root)`.

- [ ] **Step 1: Write RED tests** for valid inventory order/digests, duplicate names, traversal names, encrypted members, package/member size limits, exact no-op copy, and a one-part sparse replacement preserving untouched uncompressed bytes.
- [ ] **Step 2: Verify RED** because `twoways.ooxml` does not exist.
- [ ] **Step 3: Implement package validation** without extraction. Reject absolute paths, `..`, duplicate normalized names, encrypted members and configured limits before XML mutation.
- [ ] **Step 4: Implement sparse writing** by cloning `ZipInfo` metadata and using source member bytes for untouched entries. If replacements is empty, write `source_bytes` unchanged.
- [ ] **Step 5: Implement safe XML parser** with `resolve_entities=False`, `load_dtd=False`, `no_network=True`, `huge_tree=False`.
- [ ] **Step 6: Verify GREEN** and commit `feat(twoways): add safe OOXML package substrate`.

---

### Task 3: PPTX format contracts and optional-dependency boundary

**Files:**
- Create: `packages/markitdown/src/markitdown/twoways/formats/__init__.py`
- Create: `packages/markitdown/src/markitdown/twoways/formats/pptx/__init__.py`
- Create: `packages/markitdown/src/markitdown/twoways/formats/pptx/model.py`
- Modify: `packages/markitdown/src/markitdown/twoways/_errors.py`
- Modify: `packages/markitdown/pyproject.toml`
- Test: `packages/markitdown/tests/twoways/test_pptx_public_imports.py`

**Interfaces:**
- Produces `PptxReadOptions`, `PptxPatchOptions`, `read_pptx_ir`, `patch_pptx`, `PptxIRReader`, `PptxPatchWriter`.
- PPTX dependencies load lazily at operation boundaries.

- [ ] **Step 1: Write RED import-boundary tests** asserting root import does not add `pptx`/`lxml` to `sys.modules`, while `markitdown.twoways.formats.pptx` exposes only format-specific public symbols.
- [ ] **Step 2: Verify RED** because package/contracts do not exist.
- [ ] **Step 3: Implement frozen option dataclasses** and lazy dependency guards.
- [ ] **Step 4: Change the optional feature** from `pptx = ["python-pptx"]` to `pptx = ["python-pptx", "lxml"]`.
- [ ] **Step 5: Verify GREEN** and commit `feat(twoways): add PPTX format contracts`.

---

### Task 4: Deterministic PPTX reader for slides, text, images and conservative unknown shapes

**Files:**
- Create: `packages/markitdown/src/markitdown/twoways/formats/pptx/locators.py`
- Create: `packages/markitdown/src/markitdown/twoways/formats/pptx/text.py`
- Create: `packages/markitdown/src/markitdown/twoways/formats/pptx/shapes.py`
- Create: `packages/markitdown/src/markitdown/twoways/formats/pptx/resources.py`
- Create: `packages/markitdown/src/markitdown/twoways/formats/pptx/reader.py`
- Test: `packages/markitdown/tests/twoways/test_pptx_reader.py`
- Test helper: `packages/markitdown/tests/twoways/_pptx_fixtures.py`

**Interfaces:**
- `read_pptx_ir(file_stream, stream_info=None, *, options=None) -> DocumentIR`.
- Native locator backend is exactly `pptx-ooxml`.
- Node IDs use `sha256(part_uri + NUL + stable shape key + NUL + kind)[:24]`; source digest is excluded.

- [ ] **Step 1: Build a synthetic PPTX test fixture** with two slides, a title, a two-run text box with distinct direct formatting, one picture with alt text, and one ordinary shape that is read but not patch-authorized.
- [ ] **Step 2: Write RED reader tests** for source SHA/size, two canvases, EMU geometry, deterministic IDs across repeated reads, stable IDs after changing text in a second generated deck, paragraph/run order, image resource SHA and shape locators.
- [ ] **Step 3: Verify RED** because reader is missing.
- [ ] **Step 4: Implement locator extraction** from slide part URI, `a16:creationId` when present, `cNvPr@id`, name and diagnostic path evidence.
- [ ] **Step 5: Implement text/image reading** without materializing inherited styles as direct style. Preserve direct bold/italic/font-size/font-family/color when explicitly set.
- [ ] **Step 6: Implement conservative unknown-native nodes** with `NativePayload` references to the source slide/shape XML identity rather than flattening them.
- [ ] **Step 7: Validate resulting DocumentIR** and verify GREEN. Commit `feat(twoways): read PPTX into native DocumentIR`.

---

### Task 5: Strict locator resolver and edit preconditions

**Files:**
- Modify: `packages/markitdown/src/markitdown/twoways/formats/pptx/locators.py`
- Create: `packages/markitdown/src/markitdown/twoways/formats/pptx/patch.py`
- Test: `packages/markitdown/tests/twoways/test_pptx_locator_patch.py`

**Interfaces:**
- Produces `resolve_shape_element(slide_root, locator, *, strict=True)`.
- Produces `validate_edit_preconditions(document, node, edit)`.

- [ ] **Step 1: Write RED tests** for exact object-id resolution, creation-id + object-id agreement, wrong slide part, name-only rejection, ambiguity, stale semantic digest, stale locator digest and stale expected old value.
- [ ] **Step 2: Verify RED**.
- [ ] **Step 3: Implement resolver** by enumerating shape-level `cNvPr` records in the designated slide part and requiring exact identity evidence.
- [ ] **Step 4: Implement shared precondition validation** with Core IR semantic helpers and typed errors.
- [ ] **Step 5: Verify GREEN** and commit `feat(twoways): enforce PPTX native patch preconditions`.

---

### Task 6: Run-preserving `replace_text` and picture alt-text XML mutations

**Files:**
- Modify: `packages/markitdown/src/markitdown/twoways/formats/pptx/text.py`
- Modify: `packages/markitdown/src/markitdown/twoways/formats/pptx/patch.py`
- Test: `packages/markitdown/tests/twoways/test_pptx_text_patch.py`

**Interfaces:**
- Produces `patch_text_shape(shape_element, *, old_text, new_text)`.
- Produces `patch_picture_alt_text(shape_element, *, new_alt_text)`.

- [ ] **Step 1: Write RED tests** proving that a two-run paragraph changed from `Revenue 38%` to `Revenue 42%` preserves the same run elements and run-property XML while changing only `<a:t>` content.
- [ ] **Step 2: Add RED unsupported tests** for paragraph-count changes, line-break/field structures and unsupported edit types.
- [ ] **Step 3: Verify RED**.
- [ ] **Step 4: Implement deterministic run allocation** with `difflib.SequenceMatcher(..., autojunk=False)`: equal characters remain in owner runs; inserted/replacement text uses deterministic nearest style context; no run or paragraph elements are created/deleted.
- [ ] **Step 5: Maintain `xml:space="preserve"`** when a patched run begins/ends with whitespace.
- [ ] **Step 6: Implement alt-text mutation** by changing only the resolved picture `cNvPr@descr` attribute.
- [ ] **Step 7: Verify GREEN** and commit `feat(twoways): patch PPTX text without rebuilding runs`.

---

### Task 7: Public minimal patch writer and round-trip verification

**Files:**
- Create: `packages/markitdown/src/markitdown/twoways/formats/pptx/verify.py`
- Create: `packages/markitdown/src/markitdown/twoways/formats/pptx/writer.py`
- Modify: `packages/markitdown/src/markitdown/twoways/formats/pptx/__init__.py`
- Test: `packages/markitdown/tests/twoways/test_pptx_roundtrip.py`

**Interfaces:**
- `patch_pptx(document, source_stream, output, *, edits, options=None) -> WriterResult`.
- `PptxPatchWriter.write(..., source_stream=..., edits=...) -> WriterResult`.

- [ ] **Step 1: Write RED no-op test** requiring `output_bytes == source_bytes` and `exact-preserve` fidelity.
- [ ] **Step 2: Write RED end-to-end text test**: read synthetic deck → create edit with Phase B-compatible preconditions → patch → reopen with `python-pptx` → verify new text, unchanged run formatting, unchanged package inventory and unchanged uncompressed bytes for every member except one slide XML part.
- [ ] **Step 3: Write RED alt-text end-to-end test** with the same untouched-member guarantees.
- [ ] **Step 4: Write RED source mismatch test** that fails before output mutation.
- [ ] **Step 5: Implement writer orchestration**: hash source, snapshot package, group edits by part, parse each touched slide once, apply validated mutations, serialize touched roots, sparse-write package, then verify.
- [ ] **Step 6: Implement verifier** for package inventory, untouched-member digests, reopen/readback and affected semantic value checks.
- [ ] **Step 7: Verify GREEN** and commit `feat(twoways): add minimal PPTX patch writer`.

---

### Task 8: Regression, determinism, security and exact-head publication

**Files:**
- Modify tests only as required for regressions discovered during verification.
- Update PR description/status evidence after publication.

**Interfaces:** None new.

- [ ] **Step 1: Run full 2Ways tests**: `PYTHONPATH=packages/markitdown/src pytest -q packages/markitdown/tests/twoways`.
- [ ] **Step 2: Run hash-seed determinism suites** with `PYTHONHASHSEED=1` and `777`.
- [ ] **Step 3: Run `compileall` and Python 3.10 grammar parse** over all changed Python files.
- [ ] **Step 4: Scan root import boundary** to prove `import markitdown.twoways` does not import PPTX/lxml.
- [ ] **Step 5: Run ZIP/XML adversarial tests** for traversal, duplicates, encryption and configured limits.
- [ ] **Step 6: Publish Phase C implementation as an atomic tree commit** after every changed Git blob SHA equals the local source blob SHA.
- [ ] **Step 7: Fetch exact-head PR metadata, compare against `main`, and inspect Actions/status for that SHA. Do not claim CI green when no run exists.**
