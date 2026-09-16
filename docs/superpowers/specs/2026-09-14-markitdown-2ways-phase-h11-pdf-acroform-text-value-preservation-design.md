# Phase H11 — PDF AcroForm Text-Value Preservation Design

## Status

Approved architectural direction for the third v0.7 PDF tranche. H11 starts exactly from frozen H10 completion SHA `9f01da2914409eaa2b87174fd4deb5f6e56988dd`. The H10 branch is immutable and must not receive H11 commits.

## Goal

Add the first native-safe AcroForm mutation to MarkItDown 2Ways: update the value of an **existing, uniquely owned, terminal plain-text form field** while preserving the original PDF bytes as an exact prefix and proving that field/widget/page/AcroForm structure outside the authorized scalar value did not change.

H11 deliberately does not implement general form editing, appearance-stream regeneration, checkbox/radio/list/combo/signature mutation, field creation/deletion/reparenting, JavaScript/calculation actions, XFA, page-content edits, annotation geometry edits, or arbitrary PDF object replacement.

The tranche is intentionally narrower than pypdf's generic form-update surface. Production H11 must not call `PdfWriter.update_page_form_field_values()` because that API may update `/NeedAppearances`, regenerate widget appearance streams, and touch additional native objects. H11 keeps the existing H9/H10 exact-owner incremental mutation discipline.

## Why this tranche comes next

The approved v0.7 order is metadata, then annotations/forms/links, then selected page text/image operations. H9 established incremental metadata authority and H10 established annotation topology plus exact native-owner mutation for URI links. The next useful step is AcroForm field authority.

Text fields are chosen first because their semantic payload can be represented as one existing `/V` text string. However, PDF form value semantics and widget appearance semantics are separate. H11 therefore supports only a strict profile where the source itself already delegates appearance generation to the viewer and no embedded normal appearance is present that could become stale.

## Public operation

Add exactly one typed operation:

```text
update_pdf_text_field_value
```

Payload:

```json
{
  "field_name": "customer.name",
  "old_value": "Alice",
  "value": "Bob"
}
```

Rules:

- `field_name`, `old_value`, and `value` must be strings;
- `field_name` must be non-empty and must exactly equal the field's deterministic fully qualified name;
- `value == old_value` is rejected for a non-empty transaction;
- the new value must satisfy configured per-field and total field-value limits;
- if `/MaxLen` exists, the new value must not exceed it;
- duplicate operation IDs and duplicate logical field targets fail before candidate construction.

## H11 writable field profile

A field is writable only when a fresh strict parse proves every condition below.

### Source policy

The source inherits the complete H10 mutation policy:

- unencrypted;
- unsigned and uncertified;
- non-linearized;
- no XMP authority conflict;
- strict root/xref authority accepted by the existing PDF parser;
- source, page, annotation, increment and text resource limits remain within bounds.

### AcroForm authority

The catalog must contain one indirect `/AcroForm` dictionary with:

- an existing `/Fields` array;
- existing boolean `/NeedAppearances true`;
- no `/XFA`;
- no `/CO` calculation order;
- no AcroForm-level additional actions or JavaScript-bearing structures accepted for writable fields;
- no malformed/cyclic/aliased field tree that prevents unique field ownership.

H11 never creates `/AcroForm`, `/Fields`, `/NeedAppearances`, resources, or field dictionaries.

### Field authority

The target must be one existing indirect terminal field/widget dictionary satisfying all of the following:

1. `/FT /Tx` is explicit on the object; H11 does not rely on inherited field type.
2. `/T` is an existing text string and produces a unique fully qualified field name.
3. `/V` is an existing text string; H11 does not create a previously absent value owner.
4. The object is also the widget annotation: `/Subtype /Widget`.
5. It has no `/Parent` and no `/Kids`; hierarchical and split field/widget ownership remains read-only in H11.
6. The exact indirect object occurs in exactly one page `/Annots` slot.
7. It has no `/AP` normal appearance that could become stale. Any existing `/AP` causes H11 text-value capability to remain read-only.
8. It has no annotation/field additional actions (`/AA`) and no action dictionary (`/A`).
9. It is not read-only according to `/Ff`.
10. Password, file-select, comb, rich-text and other text-field modes that change representation/security semantics are read-only. H11 supports plain single-line text only.
11. Any `/MaxLen` is a valid non-negative integer and is enforced.
12. Any effective default appearance information needed by a viewer is already present in the source; H11 preserves it byte/semantically and does not synthesize fonts or resources.
13. The field's mutation owner is uniquely the field/widget object's object-generation tuple.

Multiline fields are intentionally deferred because newline representation and appearance behavior need a dedicated proof. H11 also does not mutate `/DV`, `/DA`, `/Q`, `/TU`, `/TM`, `/Ff`, geometry, resources or appearance entries.

## Viewer-regenerated appearance contract

H11 changes form semantics without generating appearance streams. This is safe only for the strict profile above:

- `/NeedAppearances` is already `true` and is preserved unchanged;
- the target widget has no `/AP` normal appearance to become stale;
- H11 changes only the existing `/V` scalar on the field/widget owner;
- the fidelity report must describe the result as a verified AcroForm semantic mutation with viewer-regenerated appearance, not as a byte-identical or engine-independent visual rendering guarantee.

A PDF with an embedded `/AP` is read-only for H11 even if pypdf could regenerate it. Appearance-backed text fields belong to a later tranche with explicit font/resource/stream proof.

## Native evidence model

Add `PdfTextFieldEvidence` containing at minimum:

- fully qualified field name;
- field object-generation tuple;
- page index and annotation index;
- current value;
- `/FT` and relevant `/Ff` evidence;
- `/MaxLen` when present;
- AcroForm object-generation tuple;
- `NeedAppearances` evidence;
- deterministic field/widget native locator digest;
- immutable semantic digest that masks only `/V`;
- writable flag and stable read-only reason code.

Extend `PdfSourceSnapshot` with AcroForm/field topology evidence sufficient to prove:

- AcroForm identity;
- root field array order/identities;
- supported field/widget page binding;
- complete writable-field object identity set;
- fingerprints for untouched form objects needed by H11 verification.

## Stable reason codes

H11 introduces deterministic reason codes, including:

- `pdf.form.no_acroform`
- `pdf.form.need_appearances_required`
- `pdf.form.xfa`
- `pdf.form.calculation_order`
- `pdf.form.tree_ambiguous`
- `pdf.form.field_type`
- `pdf.form.field_hierarchy`
- `pdf.form.widget_binding`
- `pdf.form.read_only`
- `pdf.form.unsupported_text_mode`
- `pdf.form.appearance_present`
- `pdf.form.additional_actions`
- `pdf.form.non_text_value`
- `pdf.form.max_length`
- `pdf.form.value_too_large`
- `pdf.form.total_value_too_large`
- `pdf.form.source_policy`

Unsupported fields should remain readable when deterministic evidence can be collected. One unsupported field must not make unrelated H9/H10 parsing fail unless its malformed object graph prevents proving AcroForm/page annotation topology safely.

## IR mapping

H11 extends the PDF `DocumentIR` with form-field scalar nodes while leaving H9 metadata and H10 URI-link nodes unchanged.

Recommended node shape:

- role: `pdf-form-text-value`;
- payload: current `/V` text;
- metadata: field name, field object-generation tuple, page/annotation coordinates, AcroForm object-generation tuple, field flags, `/MaxLen`, locator digest and `pdf.identity_markdown=False`;
- capability `update_pdf_text_field_value` is writable only for the exact H11 profile.

Identity Markdown remains inspection-only. Direct typed edits are authoritative.

## Parser and graph rules

The parser must traverse AcroForm and page annotation authority without using `PdfReader.get_fields()` as the sole source of truth. Native ownership must come from explicit object-graph traversal so object-generation identities, root field ordering and page widget bindings are retained.

The traversal must be iterative or cycle-bounded and enforce configured limits. It must detect and fail closed for mutation when encountering:

- cyclic field parent/kid graphs;
- duplicate/aliased roots that make ownership ambiguous;
- malformed `/Fields` or `/Kids` containers;
- direct field objects without stable indirect ownership;
- duplicate fully qualified names among writable candidates;
- widgets bound to zero or multiple page annotation slots;
- shared field/widget mutation owners;
- malformed field flags, `/MaxLen`, value types or AcroForm authority.

## Resource limits

Extend `PdfNativeLimits` with at least:

- `max_total_form_fields`;
- `max_field_tree_depth`;
- `max_field_name_chars`;
- `max_form_value_chars`;
- `max_total_form_value_chars`.

All must be positive integers and participate in parser and transaction-level enforcement. H11 must not introduce unbounded recursion or unbounded string aggregation.

## Routing and preconditions

Add `resolve_pdf_text_field_value_edit(document, source, edit, limits=...)`.

Routing must:

1. validate source SHA-256, byte size and format;
2. fresh-parse the source under the same limits;
3. resolve the target IR node and writable capability;
4. require field name, field object-generation, page/annotation coordinates, AcroForm identity, locator digest and immutable digest to match fresh evidence;
5. require `old_value` to match both DocumentIR and fresh source;
6. validate new value limits and `/MaxLen`;
7. reject duplicate logical targets and mutation-owner collisions before construction.

H11 field edits may coexist in one transaction with H9 metadata and H10 URI-link edits only when all edits preflight successfully and their native mutation owners are disjoint.

## Transactional writer

Reuse `patch_pdf()` and the incremental `PdfWriter(BytesIO(source), incremental=True, strict=True)` path.

Add a narrow field mutation helper that:

1. resolves the exact routed field/widget owner by object-generation tuple in the writer clone;
2. rechecks that it is a dictionary with the expected immutable field/widget shape;
3. replaces only the existing `/V` value with a `TextStringObject`;
4. never calls `update_page_form_field_values()`;
5. never creates or rewrites `/AP`, `/DA`, `/DR`, `/NeedAppearances`, field trees, page contents or annotation arrays.

The writer then calls `list_objects_in_increment()` and records the exact changed object-generation set before serializing to an internal buffer.

No candidate bytes are written to caller output until full verification succeeds.

## Preservation contract

For every non-empty H11 transaction:

- the complete original source PDF is the exact candidate prefix;
- root/catalog identity remains stable;
- page count and page object identities remain stable;
- H10 page annotation topology remains stable;
- AcroForm object identity remains stable;
- `/Fields` root ordering and identities remain stable;
- field/widget page binding remains stable;
- `/NeedAppearances` remains boolean `true`;
- no `/AP` is introduced;
- every target field changes only `/V` semantically;
- every non-target form field retains value and immutable fingerprint;
- H9 metadata changes only when authorized by H9 edits in the same transaction;
- H10 URI links change only when authorized by H10 edits in the same transaction;
- the changed-object set equals the exact union of authorized H9 Info owner, H10 URI mutation owners and H11 field/widget owners, with no extras.

## Independent verification

Native verification uses strict pypdf re-read plus the existing source-prefix and incremental changed-object audit.

H11 also adds an independent semantic oracle using `pdfminer.six`, already present in the PDF optional dependency set. The verifier should resolve catalog `/AcroForm`, traverse the bounded target field authority independently, and confirm the expected field name and `/V` text value when the source shape is representable through pdfminer.

If the target was expected to be independently representable but the oracle cannot map it deterministically, verification fails closed.

The final verifier must additionally confirm:

- field topology and object identities are unchanged;
- target immutable digest is unchanged when masking `/V`;
- untouched field fingerprints are unchanged;
- page annotation topology is unchanged;
- no appearance stream was introduced;
- H9/H10 verification requirements continue to pass for mixed transactions.

## One-way regression boundary

`packages/markitdown/src/markitdown/converters/_pdf_converter.py` remains unchanged from protected blob `ffbcbd990cfc40a577404c453ebe47bf477c4929`.

H11 is entirely a two-way PDF adapter extension. Dedicated regression evidence must lock the one-way converter boundary exactly as H9/H10 do.

## Security and fail-closed policy

H11 rejects writable capability for:

- encrypted, signed, certified, linearized or XMP-conflicted sources;
- XFA forms;
- AcroForm calculation order or JavaScript/additional-action authority;
- hierarchical/split field-widget ownership;
- direct or multiply referenced field owners;
- non-text `/V` values;
- read-only fields;
- unsupported text modes;
- existing appearance streams;
- malformed field flags, names, tree containers or page bindings;
- duplicate logical field names/owners;
- configured form-resource-limit violations.

Unsupported structures are not repaired, normalized or guessed.

## Required test-first evidence

H11 implementation requires RED before production changes and must cover at minimum:

- one plain text terminal field read/write;
- multiple independent text fields in one transaction;
- mixed H9 metadata + H10 URI + H11 form transaction;
- zero-edit exact identity;
- stale source SHA/size;
- stale old value;
- forged field name, field object-generation, page index, annotation index, AcroForm object-generation and locator/immutable digests;
- duplicate operation ID, duplicate logical target and owner collision;
- `/NeedAppearances` absent/false;
- existing `/AP` rejection;
- XFA and `/CO` rejection;
- field/widget `/AA` or `/A` rejection;
- parent/kids hierarchy rejection;
- duplicate field name rejection;
- direct field object rejection;
- widget page-binding ambiguity;
- read-only flag and unsupported text-mode rejection;
- non-text `/V` rejection;
- `/MaxLen` enforcement;
- per-value, total-value, field-count and tree-depth limits;
- unexpected changed-object rejection;
- AcroForm/field topology drift rejection;
- unauthorized sibling field drift rejection;
- appearance introduction rejection;
- caller output remains empty on every failure;
- independent pdfminer semantic agreement;
- public import/writer adapter behavior;
- inspection-only identity Markdown;
- protected one-way converter regression lock;
- exact-head pre-commit plus package/OCR Python 3.10–3.13 CI.

## Public API

The PDF package keeps the existing primary entry points:

- `read_pdf_ir`
- `patch_pdf`
- `PdfPatchWriter`

No new top-level writer class is introduced. H11 adds the new typed operation and internal evidence/routing/verifier helpers only as needed.

## Documentation

`TWOWAYS.md` is updated only after H11 hardening is GREEN. It must state precisely that H11 writes existing terminal plain-text AcroForm values only under the viewer-regenerated-appearance profile. General form controls, appearance-backed fields, hierarchical fields and form structure remain read-only.

## Completion and freeze rule

H11 is complete only when:

1. implementation/hardening diff is bounded from frozen H10 SHA;
2. the one-way PDF converter remains unchanged;
3. temporary diagnostics/development artifacts are removed;
4. exact final H11 head passes pre-commit plus package/OCR Python 3.10–3.13 — exact 9/9 GREEN;
5. the PR records exact SHA/run/job evidence;
6. the PR is Ready for review and remains unmerged unless explicitly authorized;
7. no source/docs commit is added after the exact-head completion proof.

The next PDF tranche must branch from the frozen H11 completion SHA rather than expanding H11 after freeze.
