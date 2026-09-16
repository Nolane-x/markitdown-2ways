# Phase H10 PDF URI Link Preservation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add source-preserving updates for existing PDF URI link annotations without changing unrelated PDF objects or weakening the H9 metadata contract.

**Architecture:** Extend the H9 strict PDF parser/IR/router/writer/verifier with deterministic link evidence. Keep pypdf incremental append-only writes as the only mutation path, and require the changed-object inventory to equal the exact union of authorized H9 Info and H10 link mutation owners. Use pdfplumber as an independent hyperlink semantic oracle.

**Tech Stack:** Python 3.10–3.13, pypdf `>=6.18.1,<7`, pdfplumber `>=0.11.9`, existing DocumentIR/capability kernel, pytest, pre-commit/Black.

**Spec:** `docs/superpowers/specs/2026-09-14-markitdown-2ways-phase-h10-pdf-uri-link-preservation-design.md`

## Global Constraints

- Base exactly from H9 frozen SHA `c3370b9607057cc419d3bd27395780df8f328fb1`.
- Do not modify or merge H9 PR #21.
- Writable H10 scope is existing `/Subtype /Link` + existing `/A` + `/S /URI` + existing text `/URI` only.
- No annotation creation/deletion/reordering, forms, page text/image/content mutation, outlines, arbitrary object replacement, or appearance regeneration.
- Zero edits return exact source bytes.
- Non-empty writes retain exact source PDF bytes as prefix and use pypdf incremental mode only.
- Caller output remains empty on every failed transaction.
- Identity Markdown remains inspection-only for PDF-native nodes.
- One-way `packages/markitdown/src/markitdown/converters/_pdf_converter.py` must remain unchanged.
- Completion requires exact final head pre-commit + package/OCR Python 3.10–3.13 = 9/9 GREEN.

---

### Task 1: URI-link fixtures and parser RED

**Files:**
- Modify: `packages/markitdown/tests/twoways/_pdf_fixtures.py`
- Create: `packages/markitdown/tests/twoways/test_pdf_links_parser.py`

**Interfaces:**
- Consumes: `parse_pdf_source(source: bytes, *, limits: PdfNativeLimits | None = None)`.
- Produces test expectations for `ParsedPdfSource.links`, `PdfLinkEvidence`, and new link limits.

- [ ] **Step 1: Extend synthetic PDF fixtures**

Add deterministic helpers that create strict PDFs with: direct `/A` URI action, indirect `/A` URI action, two independent links, shared indirect action object, unsupported action type, `/Dest` conflict, `/AA`, direct annotation dictionary, non-text `/URI`, malformed `/Annots`, and configurable link counts/URI lengths. Use pypdf only to construct test bytes; tests must not depend on one-way conversion.

- [ ] **Step 2: Write parser RED tests**

Representative contract:

```python
parsed = parse_pdf_source(pdf_with_direct_uri_link())
link = parsed.links[0]
assert link.page_index == 0
assert link.annotation_index == 0
assert link.uri == "https://example.com/old"
assert link.owner_kind == "annotation"
assert link.annotation_objgen is not None
assert link.mutation_owner_objgen == link.annotation_objgen
```

Also assert indirect actions use `owner_kind == "action"`, shared owners are not writable, unsupported actions are represented read-only or diagnosed, and resource limits fail closed.

- [ ] **Step 3: Run RED**

Run focused PDF parser tests. Expected failure: missing `links`/`PdfLinkEvidence`/limit fields, not fixture syntax failure.

- [ ] **Step 4: Commit test-only RED**

Commit only fixtures/tests.

### Task 2: Parser/evidence GREEN

**Files:**
- Modify: `packages/markitdown/src/markitdown/twoways/formats/pdf/limits.py`
- Modify: `packages/markitdown/src/markitdown/twoways/formats/pdf/model.py`
- Modify: `packages/markitdown/src/markitdown/twoways/formats/pdf/parser.py`

**Interfaces:**
- Produces `PdfLinkEvidence` with page/annotation indices, annotation/action/mutation-owner objgen, owner kind, URI, writable decision/reason, rectangle evidence, and locator digest.
- Extends `ParsedPdfSource.links: tuple[PdfLinkEvidence, ...]`.

- [ ] **Step 1: Add limits**

Add conservative defaults such as `max_total_annotations`, `max_annotations_per_page`, `max_uri_chars`, `max_total_uri_chars`; validate positive integer values consistently with existing limits.

- [ ] **Step 2: Add evidence model**

Define immutable/deterministic link evidence. Locator digest input must include page index, annotation index, annotation objgen, action objgen/owner kind, mutation owner objgen, subtype `/Link`, action `/URI`, and source URI.

- [ ] **Step 3: Enumerate strict annotations**

For each page, inspect raw `/Annots` entries without normalizing direct entries into writable authority. Require indirect annotation ownership for writable candidates. Inspect raw `/A`; support direct dictionary action or indirect action dictionary. Reject writable status for `/Dest`, `/AA`, non-URI actions, missing/non-text URI, shared owner ambiguity, and configured limits.

- [ ] **Step 4: Preserve H9 policy semantics**

Do not change H9 metadata fields/writable decisions. Link writability is additionally gated by the same source-level security blockers.

- [ ] **Step 5: Run focused tests then full CI checkpoint**

Focused parser tests must pass. Push and require pre-commit + full package/OCR matrix to prove no H9 regression before Task 3.

### Task 3: Reader/capability RED→GREEN

**Files:**
- Create: `packages/markitdown/tests/twoways/test_pdf_links_reader.py`
- Modify: `packages/markitdown/src/markitdown/twoways/formats/pdf/reader.py`

**Interfaces:**
- Produces PDF link nodes with role `pdf-link-uri` and operation `update_pdf_link_uri`.

- [ ] **Step 1: Write RED tests**

Assert deterministic node IDs, payload URI, metadata page/annotation indices and owner objgens, capability writable/read-only states, and `pdf.identity_markdown=False`.

- [ ] **Step 2: Observe RED**

Expected failure: link node absent, while existing H9 metadata nodes remain unchanged.

- [ ] **Step 3: Implement minimal reader import**

Materialize one scalar node per deterministic link evidence record. Reuse existing capability encoding helpers; writable only when parser evidence says H10-safe.

- [ ] **Step 4: GREEN + regression checkpoint**

Run focused reader tests plus H9 reader/Markdown tests.

### Task 4: Routing/precondition RED→GREEN

**Files:**
- Create: `packages/markitdown/tests/twoways/test_pdf_links_routing.py`
- Modify: `packages/markitdown/src/markitdown/twoways/formats/pdf/routing.py`

**Interfaces:**
- Produces `PdfRoutedLinkEdit` and `resolve_pdf_link_uri_edit(document, source, edit, *, limits=None)`.

- [ ] **Step 1: Write routing RED tests**

Cover success plus forged page index, forged annotation index, stale old URI, forged annotation/action/mutation-owner objgen, forged locator digest, unadvertised capability, stale source, semantic no-op, invalid booleans/coordinates, URI limits, duplicate logical target.

- [ ] **Step 2: Observe RED**

Expected failure: resolver/type absent.

- [ ] **Step 3: Implement resolver**

Fresh-parse source, validate root source authority, resolve target node, require operation capability, validate all native evidence and payload coordinates, and return immutable routed edit with mutation-owner objgen and requested URI.

- [ ] **Step 4: GREEN**

Run focused routing tests and existing H9 metadata routing tests.

### Task 5: Incremental writer and mixed H9/H10 transactions

**Files:**
- Create: `packages/markitdown/tests/twoways/test_pdf_links_writer.py`
- Modify: `packages/markitdown/src/markitdown/twoways/formats/pdf/writer.py`

**Interfaces:**
- `patch_pdf(...)` accepts H9 `update_pdf_metadata` and H10 `update_pdf_link_uri` in one preflighted transaction.

- [ ] **Step 1: Write writer RED tests**

Cover direct action, indirect action, two independent links, mixed metadata+link transaction, duplicate operation ID, duplicate link target, owner collision, zero-edit exact bytes, and output-empty rollback on any route/write failure.

- [ ] **Step 2: Observe RED**

Expected failure: unsupported H10 operation.

- [ ] **Step 3: Generalize edit routing**

Dispatch by operation type to H9 metadata resolver or H10 link resolver. Preflight all edits before creating the writer. Build exact authorized changed-object set from Info owner plus link mutation owners.

- [ ] **Step 4: Apply H10 mutation in writer clone**

Resolve writer-side mutation owner by object number/generation. For indirect action owner, replace only action `/URI`. For direct action owner, replace nested `/A` `/URI` inside annotation object. Use pypdf `NameObject`/`TextStringObject`; do not add missing keys or objects.

- [ ] **Step 5: Audit increment object set before output**

Capture `writer.list_objects_in_increment()`; candidate must later verify exact equality to authorized owner set.

- [ ] **Step 6: GREEN**

Focused writer tests pass without weakening H9 mixed transaction semantics.

### Task 6: Verifier, independent oracle, public/Markdown regression

**Files:**
- Create: `packages/markitdown/tests/twoways/test_pdf_links_verification.py`
- Create: `packages/markitdown/tests/twoways/test_pdf_links_markdown.py`
- Create: `packages/markitdown/tests/twoways/test_pdf_links_public.py`
- Modify: `packages/markitdown/src/markitdown/twoways/formats/pdf/verification.py`
- Modify only if required: `packages/markitdown/src/markitdown/twoways/markdown/projection.py`
- Verify unchanged: `packages/markitdown/src/markitdown/twoways/formats/pdf/__init__.py`, `writer_adapter.py`, one-way `_pdf_converter.py` unless public exports actually require a new internal type (prefer no new public API).

**Interfaces:**
- Final verifier accepts routed metadata/link edits and exact changed-object inventory.

- [ ] **Step 1: Write verifier RED tests**

Reject unexpected changed objects, sibling annotation URI drift, annotation topology drift, page count/object drift, action-type drift, rectangle drift, owner identity drift, metadata drift in link-only transaction, and semantic mismatch.

- [ ] **Step 2: Add pdfplumber oracle**

For representable URI links, map by page + rectangle/native slot evidence and require independent URI agreement. Ambiguous/no-match when expected must fail closed.

- [ ] **Step 3: Preserve H9 verifier**

Mixed transaction verification must still enforce H9 metadata semantics and untouched metadata values.

- [ ] **Step 4: Lock Markdown inspection-only**

Assert H10 link blocks expose no reversible Markdown capabilities and importer cannot produce H10 edits through identity Markdown.

- [ ] **Step 5: Lock public/one-way boundary**

`read_pdf_ir`, `patch_pdf`, `PdfPatchWriter` continue to work; no new top-level writer needed. Reassert one-way converter blob/behavior unchanged.

- [ ] **Step 6: Exact checkpoint**

Require pre-commit + package/OCR 3.10–3.13 GREEN before hardening/docs.

### Task 7: Security hardening, docs, scope audit, final freeze

**Files:**
- Create/extend: H10 adversarial PDF tests under `packages/markitdown/tests/twoways/`
- Modify after hardening GREEN: `TWOWAYS.md`

- [ ] **Step 1: Add adversarial proof**

Cover encryption, signatures/certification, XMP, linearization, malformed annotations/actions, `/Dest`, `/AA`, unsupported action types, direct annotations, shared action owners, URI length/count limits, stale source/URI, and rollback.

- [ ] **Step 2: Run hardening tests**

If tests pass without production changes, keep production unchanged. If any fail, use systematic-debugging and make the smallest production fix with a reproducing RED.

- [ ] **Step 3: Update `TWOWAYS.md`**

Document H10 existing URI-link mutation, preservation rules, matrix/fidelity entry, and keep forms/broader annotations/text/image explicitly future work.

- [ ] **Step 4: Scope audit H9→H10**

Allowed final changes: H10 spec/plan/docs, PDF two-way package/tests, and a minimal shared Markdown guard only if proven necessary. No development helpers/markers/workflows. One-way PDF converter blob must equal H9 blob `ffbcbd990cfc40a577404c453ebe47bf477c4929`.

- [ ] **Step 5: Fresh final exact-head CI**

Run/observe exact final SHA:

- pre-commit: 1/1 SUCCESS;
- package tests Python 3.10–3.13: 4/4 SUCCESS;
- OCR tests Python 3.10–3.13: 4/4 SUCCESS.

Total: exact 9/9 GREEN.

- [ ] **Step 6: Freeze and PR closure**

Update PR body with exact SHA/run/job evidence, add provenance comment, mark Ready for review, keep unmerged, and forbid commits after frozen SHA.
