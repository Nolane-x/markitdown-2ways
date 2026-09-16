# Phase H10 — PDF URI Link Preservation Design

## Status

Approved architectural design for the second v0.7 PDF tranche. H10 starts exactly from frozen H9 completion SHA `c3370b9607057cc419d3bd27395780df8f328fb1` and must not modify or merge the frozen H9 branch.

## Goal

Add one narrow native-safe PDF mutation: update the URI string of an **existing URI link annotation** while preserving the original PDF bytes as an exact prefix and proving that no unauthorized PDF objects or annotation semantics changed.

H10 deliberately does not implement general annotation editing, AcroForm mutation, page-content editing, text editing, image editing, outline editing, annotation creation/deletion/reordering, or arbitrary object replacement.

## Why URI links first

The approved parity roadmap orders v0.7 as metadata, then annotations/forms/links, then selected text/image operations. URI links are the smallest useful member of the annotation/form/link tranche because they have a scalar semantic payload (`/URI`) that can be bound to a concrete annotation/action owner without appearance-stream regeneration or field/widget state machinery.

H10 therefore extends the H9 incremental-writer model instead of introducing a new PDF serializer.

## Public operation

Add exactly one typed operation:

```text
update_pdf_link_uri
```

Payload:

```json
{
  "page_index": 0,
  "annotation_index": 2,
  "old_uri": "https://example.com/old",
  "uri": "https://example.com/new"
}
```

Rules:

- `page_index` and `annotation_index` are zero-based integers; booleans are rejected.
- `old_uri` and `uri` must be strings.
- `uri` must be non-empty and within configured length limits.
- a semantic no-op (`uri == old_uri`) is rejected for non-empty edit transactions;
- duplicate operation IDs and duplicate logical annotation targets fail before candidate construction.

## Writable source shape

A link is writable only when a fresh strict parse proves all of the following:

1. the source is H10-policy eligible under the existing H9 security boundary: unencrypted, unsigned, uncertified, non-linearized, no XMP authority conflict, strict root authority, and within configured limits;
2. `page_index` resolves uniquely to one page;
3. the page has an `/Annots` array and `annotation_index` resolves uniquely;
4. the annotation entry is an indirect object;
5. the annotation dictionary has `/Subtype /Link`;
6. it has an existing `/A` action dictionary with `/S /URI`;
7. the action has an existing `/URI` text string;
8. there is no `/Dest` competing with the URI action;
9. there are no annotation-level or action-level additional actions (`/AA`);
10. the native owner used for mutation has unique authority and is not shared by another supported link target;
11. the requested old URI exactly matches the fresh source semantic value.

Unsupported action types (`/GoTo`, `/GoToR`, `/Launch`, `/JavaScript`, named actions, malformed actions, missing `/A`, non-text `/URI`) remain read-only.

## Native ownership model

Each writable link record carries:

- `page_index`;
- `annotation_index`;
- annotation object number/generation;
- action owner kind: `annotation` or `action`;
- action object number/generation when `/A` is indirect;
- mutation owner object number/generation;
- current URI;
- annotation subtype/action type evidence;
- a deterministic native locator digest.

Two ownership cases are supported:

### Indirect action owner

If `/A` is an indirect dictionary, the action object itself is the mutation owner. The changed-object audit must contain exactly that action object for this edit, unless multiple authorized H10 edits intentionally target distinct objects in one transaction.

### Direct action owner

If `/A` is a direct dictionary inside an indirect link annotation, the annotation object is the mutation owner. H10 permits this shape only when the annotation object is uniquely referenced by the target page annotation slot and no supported target shares the same mutation owner.

H10 never promotes a direct action to a new indirect object merely to make editing easier.

## IR mapping

H10 extends the existing PDF `DocumentIR` reader with link nodes while preserving H9 metadata nodes unchanged.

Recommended shape:

- PDF root canvas remains the document canvas;
- each materialized URI link is a scalar semantic node with role `pdf-link-uri`;
- payload exposes the URI string;
- metadata records page/annotation indices, annotation/action/mutation-owner object-generation tuples, action owner kind, native locator digest, and `pdf.identity_markdown=False`;
- capability `update_pdf_link_uri` is writable only for policy-eligible records; unsupported annotations may be represented read-only when deterministic evidence is available.

Identity Markdown for H10 link nodes is inspection-only. Direct typed operations are authoritative.

## Parser and evidence changes

Extend the PDF parser without weakening H9 metadata evidence.

The parser must enumerate page annotations under strict resource limits and collect deterministic link evidence. It must detect and fail closed on:

- malformed `/Annots` arrays;
- direct annotation entries without stable indirect ownership;
- duplicate or aliased annotation references that make target ownership ambiguous;
- shared indirect action dictionaries across writable link candidates;
- malformed action dictionaries;
- competing `/Dest` + `/A` URI semantics;
- additional actions;
- non-text URI values;
- annotation/action counts above configured limits.

The parser must not mark the whole PDF unreadable merely because an unrelated unsupported annotation exists. Unsupported annotations remain read-only unless their malformed ownership prevents proving page annotation topology safely.

## Resource limits

Extend `PdfNativeLimits` with bounded annotation/link limits. At minimum:

- maximum total annotations;
- maximum annotations per page;
- maximum URI characters;
- maximum total URI characters represented in IR.

Existing source-byte/page/metadata/increment limits remain in force.

## Routing and preconditions

`resolve_pdf_link_uri_edit(document, source, edit, limits=...)` must:

1. validate the root source descriptor SHA-256, byte size, and format;
2. fresh-parse the source using the same limits;
3. resolve the target node in the supplied `DocumentIR`;
4. require advertised `update_pdf_link_uri` capability;
5. require page index, annotation index, owner kind, annotation/action/mutation-owner object-generation evidence and locator digest to match the fresh source;
6. validate payload coordinates against the node evidence;
7. require `old_uri` to match both the document node and fresh source;
8. reject duplicate logical targets before mutation.

No edit may route from visible Markdown identity alone.

## Transactional writer

Reuse H9's `patch_pdf` transaction and incremental pypdf writer. H10 should generalize PDF routing/writing so a transaction may contain H9 metadata edits and H10 URI-link edits **only if the authorized changed-object set remains unambiguous and all edits preflight before mutation**.

Candidate construction:

1. validate complete edit set;
2. route every edit against fresh source evidence;
3. construct `PdfWriter(BytesIO(source), incremental=True, strict=True)`;
4. apply metadata edits using the existing H9 path;
5. resolve each H10 mutation owner in the writer clone and replace only the existing `/URI` text value;
6. call `list_objects_in_increment()` before write and record the exact changed object-generation set;
7. write to an internal buffer;
8. run the complete verifier;
9. only then write candidate bytes to caller output.

Any failure leaves caller output empty.

Zero edits still return the exact source bytes.

## Preservation contract

For every non-empty H10 transaction:

- the complete original source PDF must be the exact candidate prefix;
- root/catalog identity must remain stable;
- page count and page object identities must remain stable;
- complete page annotation topology (page order, annotation count/order, annotation object identities) must remain stable;
- annotation dictionaries outside authorized mutation owners must retain their semantic evidence;
- for a direct-action target, all annotation keys except the requested nested `/URI` semantic must remain equivalent;
- for an indirect-action target, the annotation object must remain unchanged and only the authorized action object's `/URI` semantic may differ;
- every unrequested URI link must retain its URI and native evidence;
- H9 Document Information metadata must remain unchanged unless the same transaction contains authorized H9 metadata edits;
- the changed-object set must equal the exact set of authorized H9 `/Info` and H10 mutation-owner objects, with no extras.

Compressed byte identity of rewritten incremental objects is not claimed; preservation authority is the exact source prefix plus changed-object and semantic audits.

## Independent verification

The final verifier must use strict pypdf re-read as native authority and an independent pdfplumber read for hyperlink semantics where pdfplumber exposes the target.

For each requested H10 link:

- pypdf must report the expected URI at the same page/annotation slot;
- page/annotation topology and owner identities must remain stable;
- pdfplumber hyperlink extraction must agree on the requested URI and rectangle when that source link is represented by pdfplumber;
- if pdfplumber cannot deterministically map a source link that was expected to be representable, verification fails closed rather than silently skipping the oracle.

The verifier must also retain all H9 metadata verification requirements.

## One-way regression boundary

`packages/markitdown/src/markitdown/converters/_pdf_converter.py` remains unchanged. H10 is a two-way native adapter extension only. A regression test must lock the one-way converter blob/behavior boundary exactly as H9 does.

## Security and fail-closed policy

H10 inherits H9 policy rejections for:

- encryption;
- signatures;
- certification policy;
- XMP metadata authority conflicts;
- linearization;
- ambiguous strict PDF authority;
- configured source/page/increment limits.

H10 additionally rejects writable capability for:

- JavaScript/Launch/GoTo/GoToR or unknown actions;
- additional actions;
- competing destinations;
- shared mutation owners;
- direct annotation entries;
- non-text or missing URI values;
- malformed annotation arrays/action dictionaries;
- URI/resource-limit violations.

## Tests

H10 requires test-first evidence for:

- direct-action URI link read/write;
- indirect-action URI link read/write;
- multiple independent links in one transaction;
- mixed H9 metadata + H10 URI transaction;
- zero-edit exact identity;
- stale source SHA/size;
- stale URI / forged page index / forged annotation index;
- forged annotation/action/mutation-owner object-generation evidence;
- duplicate operation ID and duplicate logical target;
- shared action-owner ambiguity;
- unsupported action types;
- `/Dest` conflicts and `/AA` additional actions;
- direct annotation object rejection;
- malformed annotation/action structures;
- encrypted/signed/certified/XMP/linearized sources;
- annotation/URI resource limits;
- unexpected changed-object rejection;
- unauthorized sibling annotation drift rejection;
- caller output remains empty on every failure;
- public import/writer adapter behavior;
- inspection-only identity Markdown;
- one-way converter regression lock;
- full package/OCR Python 3.10–3.13 matrix and pre-commit at the exact final SHA.

## Public API

The PDF package keeps the H9 public API and adds no new top-level writer class. `read_pdf_ir` and `patch_pdf` remain the primary entry points. `PdfPatchWriter` continues to delegate to `patch_pdf` and gains H10 capability automatically through the document/edit contracts.

Internal additions may include:

- `PdfLinkEvidence`;
- `PdfRoutedLinkEdit`;
- `resolve_pdf_link_uri_edit`;
- verifier helpers for annotation topology and hyperlink semantics.

## Documentation

`TWOWAYS.md` must document H10 only after hardening is GREEN. The support matrix must state that PDF H10 can mutate existing URI actions only; general annotations/forms/links remain read-only. The roadmap must still show forms and broader annotations as future v0.7 work.

## Completion and freeze rule

H10 is complete only when:

1. implementation and hardening scope audits are clean from H9 exact SHA;
2. the one-way PDF converter remains unchanged;
3. temporary development artifacts are removed;
4. the exact final H10 branch SHA passes pre-commit plus package and OCR matrices on Python 3.10–3.13 — exact 9/9 GREEN;
5. the PR body records exact SHA/run/job evidence;
6. the PR is Ready for review and remains unmerged unless the user explicitly asks to merge.

After completion, no commits may be added to the frozen H10 branch if preserving exact-head provenance. The next PDF tranche must branch directly from the frozen H10 SHA.