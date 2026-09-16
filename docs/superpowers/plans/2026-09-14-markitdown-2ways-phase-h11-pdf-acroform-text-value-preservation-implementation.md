# Phase H11 PDF AcroForm Text-Value Preservation Implementation Plan

> **For Codex:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add one native-safe PDF mutation, `update_pdf_text_field_value`, for existing uniquely owned terminal plain-text AcroForm field/widgets under the H11 viewer-regenerated-appearance profile, preserving the exact source PDF prefix and rejecting any unproven ownership, appearance, script, structural, or security case.

**Architecture:** Extend the existing H9/H10 PDF adapter rather than adding a second form stack. The strict parser gains bounded AcroForm/field-tree evidence; the reader projects eligible fields into `DocumentIR`; routing binds typed edits to fresh object-generation and immutable evidence; `patch_pdf()` mutates only the existing field/widget `/V` scalar through the existing incremental writer; verification proves exact changed-object authority, immutable field/form topology, and independent pdfminer agreement. No generic pypdf form-update API, form serializer, appearance regeneration, or shared-core edit registry is introduced.

**Tech Stack:** Python 3.10–3.13, pypdf `>=6.18.1,<7`, pdfminer.six, existing `markitdown.twoways` IR/capability/error/fidelity contracts, pytest/Hatch, Black 23.7.0/pre-commit, GitHub Actions.

---

## Frozen authority and non-negotiable boundaries

- Base exactly: H10 `9f01da2914409eaa2b87174fd4deb5f6e56988dd`.
- H11 branch: `phase-h11-pdf-acroform-text-value-preservation`.
- Approved design: `docs/superpowers/specs/2026-09-14-markitdown-2ways-phase-h11-pdf-acroform-text-value-preservation-design.md`.
- Protected one-way converter must remain blob `ffbcbd990cfc40a577404c453ebe47bf477c4929`.
- Do not use `PdfWriter.update_page_form_field_values()`.
- Do not add a new global `EditOperation` type registry: `EditOperation.type` is already an open validated string and H11 belongs to PDF routing/capability authority.
- Do not mutate or synthesize `/AP`, `/DA`, `/DR`, `/NeedAppearances`, field tree structure, page `/Annots`, page content, geometry, resources, or non-text controls.
- Exact no-edit byte identity remains unchanged.
- Caller output remains empty until candidate verification completes.
- `TWOWAYS.md` is updated only after implementation + hardening tests are GREEN.

## Task 1: Build deterministic H11 PDF fixtures and RED parser contracts

**Files:**
- Modify: `packages/markitdown/tests/twoways/_pdf_fixtures.py`
- Create: `packages/markitdown/tests/twoways/test_pdf_forms_parser.py`
- Create: `packages/markitdown/tests/twoways/test_pdf_forms_topology.py`

**Step 1: Add a raw-PDF AcroForm fixture builder.**

Add `make_text_form_pdf(...)` using the same deterministic hand-built classic-xref style as `make_metadata_pdf()`. Default source shape must contain:

- Catalog `1 0 R` with `/Pages 2 0 R` and indirect `/AcroForm 5 0 R`.
- Page `3 0 R` with `/Annots [6 0 R]`.
- Optional Info dictionary `4 0 R` so mixed H9+H11 fixtures remain possible.
- AcroForm `5 0 R`: `<< /Fields [6 0 R] /NeedAppearances true /DA (/Helv 0 Tf 0 g) >>` plus a minimal `/DR` font resource only if strict consumers require it; it must remain untouched by H11.
- Terminal combined field/widget `6 0 R`: `<< /FT /Tx /Subtype /Widget /T (customer.name) /V (Alice) /Rect [72 700 240 724] ... >>` with explicit single-line-safe `/Ff 0` and no `/AP`, `/Parent`, `/Kids`, `/A`, or `/AA`.

The helper accepts bounded switches needed by negative tests rather than introducing one fixture per test: `need_appearances`, `value`, `field_name`, `field_flags`, `max_len`, `with_ap`, `with_xfa`, `with_co`, `with_aa`, `with_action`, `with_parent`, `with_kids`, `direct_field`, `duplicate_field_name`, `duplicate_page_binding`, `non_text_value`, and optional second independent field.

Do not use pypdf to generate fixture bytes: native object ownership must be explicit and deterministic.

**Step 2: Write parser RED tests.**

`test_pdf_forms_parser.py` must assert the future `ParsedPdfSource.form_fields` evidence for the default fixture:

- exactly one `PdfTextFieldEvidence`;
- `field_name == "customer.name"`;
- expected field/widget object-generation tuple;
- page/annotation coordinates resolve exactly;
- `value == "Alice"`;
- `field_type == "/Tx"`;
- `field_flags == 0`;
- AcroForm object-generation identity recorded;
- `need_appearances is True`;
- locator and immutable digests are non-empty deterministic hex digests;
- `writable is True`, `reason_code is None`.

Add RED cases for all policy boundaries: missing/false NeedAppearances, `/AP`, XFA, `/CO`, `/AA`, `/A`, parent/kids hierarchy, duplicate names, direct field root, zero/multiple page binding, read-only bit, multiline/password/file-select/comb/rich-text modes, non-text `/V`, malformed `/MaxLen`, and H10 source-policy inheritance.

**Step 3: Write resource-limit/topology RED tests.**

Assert future `PdfNativeLimits` fields and parser errors/read-only decisions for:

- `max_total_form_fields`;
- `max_field_tree_depth`;
- `max_field_name_chars`;
- `max_form_value_chars`;
- `max_total_form_value_chars`.

Topology tests must prove exact root `/Fields` order/identities and field/page binding evidence are captured. Include a cycle/alias malformed graph that fails closed with `pdf.form.tree_ambiguous` instead of recursion overflow.

**Step 4: Run focused tests and preserve RED evidence.**

Run:

```bash
cd packages/markitdown
hatch run test:pytest tests/twoways/test_pdf_forms_parser.py tests/twoways/test_pdf_forms_topology.py -q
```

Expected: failures are caused by missing H11 limits/model/parser contracts, not malformed fixtures or unrelated H10 regressions.

**Step 5: Commit RED only.**

```bash
git add packages/markitdown/tests/twoways/_pdf_fixtures.py packages/markitdown/tests/twoways/test_pdf_forms_parser.py packages/markitdown/tests/twoways/test_pdf_forms_topology.py
git commit -m "H11 RED AcroForm parser authority"
```

## Task 2: Implement H11 limits, evidence model, and strict AcroForm parser

**Files:**
- Modify: `packages/markitdown/src/markitdown/twoways/formats/pdf/limits.py`
- Modify: `packages/markitdown/src/markitdown/twoways/formats/pdf/model.py`
- Modify: `packages/markitdown/src/markitdown/twoways/formats/pdf/parser.py`

**Step 1: Extend `PdfNativeLimits`.**

Add conservative defaults:

```python
max_total_form_fields: int = 10_000
max_field_tree_depth: int = 64
max_field_name_chars: int = 4 * 1024
max_form_value_chars: int = 64 * 1024
max_total_form_value_chars: int = 256 * 1024
```

Add each to the existing positive-integer `__post_init__` validation loop. Do not add nullable/zero special cases.

**Step 2: Add immutable evidence types.**

In `model.py`, add frozen `PdfTextFieldEvidence` with exactly the evidence needed by routing/verifier:

```python
@dataclass(frozen=True)
class PdfTextFieldEvidence:
    field_name: str
    field_objgen: tuple[int, int]
    page_index: int
    annotation_index: int
    value: str
    field_type: str
    field_flags: int
    max_len: int | None
    acroform_objgen: tuple[int, int]
    need_appearances: bool
    locator_digest: str
    immutable_digest: str
    writable: bool
    reason_code: str | None = None
```

Extend `PdfSourceSnapshot` with defaulted H11 evidence so H9/H10 construction stays source-compatible:

```python
acroform_objgen: tuple[int, int] | None = None
acroform_fields_topology: tuple[tuple[int, int] | None, ...] = ()
form_field_bindings: tuple[tuple[tuple[int, int], int, int], ...] = ()
form_field_fingerprints: tuple[tuple[tuple[int, int], str], ...] = ()
need_appearances: bool | None = None
```

Extend `ParsedPdfSource` with `form_fields: tuple[PdfTextFieldEvidence, ...] = ()`.

**Step 3: Implement canonical masked field evidence.**

Reuse `_canonical_pdf_value()`; add `_masked_text_field_semantic(field)` that substitutes exactly `/V` with a fixed `("editable-form-value",)` token. `_text_field_immutable_digest()` hashes that masked semantic plus AcroForm/page-slot authority. Do not mask `/DV`, `/DA`, `/Ff`, `/MaxLen`, `/Rect`, `/T`, or any other key.

Add `_text_field_locator_digest(...)` binding field name, object-generation, AcroForm object-generation, page/annotation coordinates, `/Tx`, and current value. Locator changes when the source value changes; immutable digest does not change for an authorized `/V` edit.

**Step 4: Implement bounded field-tree/page-binding collection.**

Add one parser helper, e.g. `_collect_text_fields(reader, *, limits, source_policy_blocked, annotation_topology)`, with explicit iterative traversal. Requirements:

- Resolve catalog `/AcroForm` only when it is an indirect dictionary.
- Record root `/Fields` identities in order.
- Enforce field count, tree depth, name length, value length, total value length while traversing.
- Track visited indirect object-generation tuples and ancestor path to distinguish benign lookup from cycle/alias ambiguity; any ambiguous ownership required for mutation produces deterministic fail-closed evidence/error.
- Build a reverse index from `annotation_topology` so a supported terminal field/widget must map to exactly one `(page_index, annotation_index)`.
- Direct field objects never gain write authority.
- Unsupported deterministic fields may be omitted from writable field nodes or represented read-only, but malformed authority that prevents topology proof must fail closed.
- Explicit `/FT /Tx`, text `/T`, text `/V`, no parent/kids, `/Subtype /Widget`, no AP/A/AA, allowed `/Ff`, valid `/MaxLen`, existing `NeedAppearances true`, no XFA/CO, unique page binding, and source-policy eligibility are all required for `writable=True`.

Use stable reason precedence so one input yields one deterministic reason. Recommended order: source policy → AcroForm authority → hierarchy/ownership → field type/value → actions/appearance → flags/modes → binding/limits.

**Step 5: Integrate with `parse_pdf_source()`.**

Call `_collect_links()` first so page/annotation topology remains H10 authority; then collect H11 fields from the same reader and topology. Populate snapshot form evidence and `ParsedPdfSource.form_fields` without changing H9 metadata or H10 link semantics.

**Step 6: Run focused GREEN tests and H10 parser regression.**

```bash
hatch run test:pytest \
  tests/twoways/test_pdf_forms_parser.py \
  tests/twoways/test_pdf_forms_topology.py \
  tests/twoways/test_pdf_links_parser.py \
  tests/twoways/test_pdf_links_topology.py \
  tests/twoways/test_pdf_native_parser.py -q
```

Expected: all pass.

**Step 7: Commit.**

```bash
git add packages/markitdown/src/markitdown/twoways/formats/pdf/{limits.py,model.py,parser.py}
git commit -m "H11 GREEN AcroForm parser authority"
```

## Task 3: Add H11 DocumentIR capability projection and RED reader/Markdown contracts

**Files:**
- Create: `packages/markitdown/tests/twoways/test_pdf_forms_reader.py`
- Create: `packages/markitdown/tests/twoways/test_pdf_forms_markdown.py`
- Modify: `packages/markitdown/src/markitdown/twoways/formats/pdf/reader.py`

**Step 1: Write RED reader tests.**

Require one scalar node per deterministic H11 field with:

- role `pdf-form-text-value`;
- text/payload equal to current `/V`;
- metadata keys for field name, field objgen, page/annotation, AcroForm objgen, flags, MaxLen, locator digest, immutable digest, writable/reason, and `pdf.identity_markdown=False`;
- capability operation `update_pdf_text_field_value`, state `writable` only when `PdfTextFieldEvidence.writable` is true; otherwise read-only with the exact parser reason.

Root metadata adds bounded H11 inspection facts only, e.g. `pdf.form_h11_supported`, `pdf.form_h11_count`, `pdf.acroform_objgen`, `pdf.need_appearances`. Do not copy arbitrary AcroForm dictionaries into IR metadata.

**Step 2: Write RED identity-Markdown inspection test.**

Follow H10 link precedent: form nodes are visible for inspection but must not be imported into a generic editable identity-Markdown operation. Any attempted Markdown mutation of the field value must not generate `update_pdf_text_field_value`; direct typed edits remain authoritative.

**Step 3: Implement reader projection.**

Add `_form_capability(field)` and `_form_node(field)` beside H10 helpers. Keep all H9/H10 node IDs stable; append H11 nodes deterministically after existing PDF nodes, using a collision-resistant node ID derived from field object identity/name rather than presentation text alone.

**Step 4: Run tests.**

```bash
hatch run test:pytest tests/twoways/test_pdf_forms_reader.py tests/twoways/test_pdf_forms_markdown.py tests/twoways/test_pdf_links_reader.py tests/twoways/test_pdf_links_markdown.py -q
```

Expected: pass without H9/H10 node drift.

**Step 5: Commit.**

```bash
git add packages/markitdown/src/markitdown/twoways/formats/pdf/reader.py packages/markitdown/tests/twoways/test_pdf_forms_reader.py packages/markitdown/tests/twoways/test_pdf_forms_markdown.py
git commit -m "H11 project AcroForm values into DocumentIR"
```

## Task 4: Add RED routing/precondition contracts, then implement exact H11 routing

**Files:**
- Create: `packages/markitdown/tests/twoways/test_pdf_forms_routing.py`
- Modify: `packages/markitdown/src/markitdown/twoways/formats/pdf/routing.py`

**Step 1: Write RED routing tests.**

Construct edits with existing `EditOperation`; do not change `ir/edits.py`. Cover:

- valid `update_pdf_text_field_value` route;
- wrong node role/capability;
- malformed payload, missing/extra keys;
- non-string field/value inputs;
- empty field name;
- semantic no-op;
- stale `old_value`;
- forged field name;
- forged field objgen;
- forged page/annotation coordinates;
- forged AcroForm objgen;
- forged locator digest;
- forged immutable digest;
- new value over per-value or `/MaxLen` limit;
- fresh source policy/capability becoming read-only.

**Step 2: Add routed H11 dataclass.**

```python
@dataclass(frozen=True)
class PdfRoutedTextFieldEdit:
    operation_id: str
    node_id: str
    field_name: str
    field_objgen: tuple[int, int]
    page_index: int
    annotation_index: int
    acroform_objgen: tuple[int, int]
    old_value: str
    value: str
    max_len: int | None
    locator_digest: str
    immutable_digest: str
```

The mutation owner is `field_objgen`; no second owner abstraction is necessary for H11.

**Step 3: Implement `resolve_pdf_text_field_value_edit()`.**

Mirror the defensive H10 resolver: source authority first, DocumentIR node/capability evidence, exact payload shape, fresh strict parse, unique fresh field by deterministic name/object identity, all immutable evidence equality, stale old-value check, limits/MaxLen, then return routed edit.

**Step 4: Run focused tests.**

```bash
hatch run test:pytest tests/twoways/test_pdf_forms_routing.py tests/twoways/test_pdf_links_routing.py tests/twoways/test_pdf_native_routing.py -q
```

Expected: all pass.

**Step 5: Commit.**

```bash
git add packages/markitdown/src/markitdown/twoways/formats/pdf/routing.py packages/markitdown/tests/twoways/test_pdf_forms_routing.py
git commit -m "H11 route exact AcroForm text-value edits"
```

## Task 5: RED writer transactions and exact native-owner mutation

**Files:**
- Create: `packages/markitdown/tests/twoways/test_pdf_forms_writer.py`
- Modify: `packages/markitdown/src/markitdown/twoways/formats/pdf/writer.py`

**Step 1: Write writer RED tests.**

Cover:

- one valid form edit;
- two independent field edits;
- mixed H9 metadata + H10 URI + H11 form transaction;
- duplicate form logical target;
- link/form native-owner collision if a malicious/forged document attempts to bind both to one owner;
- total final form-value character limit after requested edits;
- exact zero-edit source identity;
- caller output remains empty on route, write, and verifier failure;
- generic `update_page_form_field_values` is never called (monkeypatch it to raise if invoked);
- output candidate starts with exact source bytes and target field owner is the only H11 object in the increment for form-only transaction.

**Step 2: Extend writer routed union and transaction preflight.**

`PdfRoutedEdit` becomes metadata | link | text-field. `_route_all()` tracks one shared `mutation_owners` set for H10/H11 native owners so cross-kind collisions fail before writer construction. Keep logical target sets kind-specific.

After routing, calculate final total form value characters from fresh parsed fields plus requested replacements and enforce `max_total_form_value_chars`.

**Step 3: Add `_apply_text_field_edit()`.**

Resolve the exact owner with `_owner_object()`, recheck the owner still exposes `/FT /Tx`, `/Subtype /Widget`, matching `/T`, existing text `/V`, no `/AP`/`/Parent`/`/Kids`/`/A`/`/AA`, and expected immutable shape. Then replace only:

```python
owner[NameObject("/V")] = TextStringObject(item.value)
```

Never call generic form-update methods and never modify AcroForm/page objects.

**Step 4: Integrate in `patch_pdf()`.**

Route all edits before `PdfWriter` construction; apply metadata, links, then text fields. Keep changed-object collection before write and full candidate verification before caller output.

**Step 5: Run focused tests.**

```bash
hatch run test:pytest tests/twoways/test_pdf_forms_writer.py tests/twoways/test_pdf_links_writer.py tests/twoways/test_pdf_native_writer.py tests/twoways/test_pdf_native_rollback.py -q
```

Expected: all pass.

**Step 6: Commit.**

```bash
git add packages/markitdown/src/markitdown/twoways/formats/pdf/writer.py packages/markitdown/tests/twoways/test_pdf_forms_writer.py
git commit -m "H11 patch only authorized AcroForm value owners"
```

## Task 6: RED verifier hardening and independent pdfminer form oracle

**Files:**
- Create: `packages/markitdown/tests/twoways/test_pdf_forms_verification.py`
- Extend: `packages/markitdown/tests/twoways/test_pdf_forms_topology.py`
- Modify: `packages/markitdown/src/markitdown/twoways/formats/pdf/verification.py`

**Step 1: Write verifier RED tests.**

Directly call `verify_pdf_candidate()` with controlled source/candidate evidence or monkeypatched parsed snapshots to prove rejection of:

- unexpected increment object;
- AcroForm object identity drift;
- root `/Fields` order/identity drift;
- field/page binding drift;
- target immutable digest drift outside `/V`;
- sibling field fingerprint/value drift;
- NeedAppearances drift;
- AP introduction;
- page annotation topology drift;
- requested field `/V` not changed to expected value;
- independent pdfminer disagreement/unmappable target.

Retain existing H10 rule: annotation fingerprints may differ only at authorized direct URI targets **or authorized H11 combined field/widget targets**, and their dedicated immutable semantic verifier must then prove that only the permitted scalar changed.

**Step 2: Extend routed union and expected owner audit.**

Add `PdfRoutedTextFieldEdit`; expected changed object set includes each `field_objgen` in addition to H9 Info and H10 link mutation owners.

**Step 3: Generalize annotation authority exemptions safely.**

Replace the H10-only `direct_action_targets` concept with an explicit authorized annotation target set derived from:

- H10 direct-action URI edits (`owner_kind == "annotation"`);
- all H11 field/widget edits because their `/V` lives on the annotation dictionary.

No other annotation may change fingerprint. Exemption from generic fingerprint equality is not permission by itself; H10/H11 dedicated immutable digests must still match.

**Step 4: Implement `_verify_form_fields()`.**

Index source/candidate `form_fields` by stable field identity. Require same form-field topology; for every target require expected `/V`; for untargeted fields require original `/V`; compare field binding/flags/MaxLen/locator components and the immutable digest masking only `/V`. Require source/candidate AcroForm snapshot topology/NeedAppearances evidence equal and true for H11 targets.

**Step 5: Implement independent pdfminer form traversal.**

Using `PDFDocument(PDFParser(BytesIO(data)))`, resolve catalog `AcroForm`, its `Fields`, and the strict H11 terminal shape independently. Decode byte strings with pdfminer `decode_text`; preserve bounded traversal with the same field/depth limits. Return a map keyed by deterministic field name with value plus enough identity/topology evidence to detect ambiguity. For each H11 routed edit, candidate oracle value must equal requested `value`; source oracle must equal `old_value`. If deterministic mapping is absent or duplicated, fail `pdf.candidate.pdfminer_form`.

Do not reuse pypdf parser output inside the pdfminer helper.

**Step 6: Run H11 + H9/H10 verifier regressions.**

```bash
hatch run test:pytest \
  tests/twoways/test_pdf_forms_verification.py \
  tests/twoways/test_pdf_forms_topology.py \
  tests/twoways/test_pdf_links_verification.py \
  tests/twoways/test_pdf_links_topology.py \
  tests/twoways/test_pdf_native_verification.py -q
```

Expected: all pass.

**Step 7: Commit.**

```bash
git add packages/markitdown/src/markitdown/twoways/formats/pdf/verification.py packages/markitdown/tests/twoways/test_pdf_forms_verification.py packages/markitdown/tests/twoways/test_pdf_forms_topology.py
git commit -m "H11 verify AcroForm topology and independent semantics"
```

## Task 7: Public adapter/regression locks and adversarial closure

**Files:**
- Create: `packages/markitdown/tests/twoways/test_pdf_forms_public.py`
- Modify as needed only for bug fixes uncovered by tests: `packages/markitdown/src/markitdown/twoways/formats/pdf/{parser.py,reader.py,routing.py,verification.py,writer.py}`
- Do not alter public exports unless a test demonstrates a required stable contract.

**Step 1: Add public-path tests.**

Prove existing public API is sufficient:

- `read_pdf_ir()` exposes H11 form capability;
- `patch_pdf()` applies a typed H11 edit;
- `PdfPatchWriter` delegates successfully;
- `markitdown.twoways.formats.pdf.__all__` needs no new top-level writer or form helper export.

**Step 2: Add one-way regression lock.**

Reuse the H9/H10 regression mechanism and require `_pdf_converter.py` blob/content boundary to remain unchanged. Do not duplicate a second source-of-truth hash mechanism if the existing test helper can express the H11 lock.

**Step 3: Close adversarial matrix.**

Ensure every approved-design rejection has an executable test: NeedAppearances false/absent, AP, XFA, CO, A/AA, hierarchy, direct root, alias/cycle, binding ambiguity, duplicate names, field flags/modes, non-text V, MaxLen, five new resource limits, source policy, cross-owner collision, candidate topology/sibling drift, caller rollback.

Any discovered bug receives a dedicated failing regression test before the smallest production fix.

**Step 4: Run complete PDF two-way suite.**

```bash
hatch run test:pytest tests/twoways/test_pdf_*.py -q
```

Expected: zero failures.

**Step 5: Commit.**

```bash
git add packages/markitdown/tests/twoways packages/markitdown/src/markitdown/twoways/formats/pdf
git commit -m "H11 harden public AcroForm mutation boundary"
```

## Task 8: H11 documentation only after code/hardening GREEN

**Files:**
- Modify: `TWOWAYS.md`

**Step 1: Update support boundary precisely.**

Document that PDF now supports:

- H9 existing Info metadata scalar mutation;
- H10 existing URI link target mutation;
- H11 existing terminal plain-text AcroForm `/V` mutation only under NeedAppearances=true and no-AP viewer-regenerated-appearance profile.

Explicitly keep read-only/out-of-scope: appearance-backed fields, hierarchical fields, multiline/password/file-select/comb/rich-text fields, checkbox/radio/list/combo/signature, XFA, calculations/scripts, form structure, annotation creation/deletion/order/geometry, page text/images/content, outlines, arbitrary object replacement.

**Step 2: Add one minimal public API example.**

Use the already-public `EditOperation` + `EditPrecondition` + `patch_pdf`/`PdfPatchWriter` pattern. Do not invent an H11 convenience API.

**Step 3: Run documentation-relevant and public tests.**

```bash
hatch run test:pytest tests/twoways/test_pdf_forms_public.py tests/twoways/test_pdf_forms_markdown.py tests/twoways/test_pdf_links_public.py -q
```

Expected: pass.

**Step 4: Commit.**

```bash
git add TWOWAYS.md
git commit -m "H11 document bounded AcroForm text-value support"
```

## Task 9: Scope audit, formatter closure, and exact-head verification

**Files:** no intended production changes unless a failing check has a proven root cause and receives regression coverage.

**Step 1: Audit H10→H11 diff.**

Compare against frozen H10 SHA. Allowed surfaces are:

- H11 design + implementation plan;
- `TWOWAYS.md` H11-only documentation;
- PDF two-way package files required by H11;
- H11 PDF tests/fixture extensions.

Reject incidental edits to one-way converters, unrelated adapters, workflows, formatter config, project dependencies, or shared IR unless a separately proven necessity exists. There should be no new dependency.

**Step 2: Verify protected one-way converter.**

Confirm blob remains exactly:

```text
ffbcbd990cfc40a577404c453ebe47bf477c4929
```

**Step 3: Run local/focused formatting checks if available.**

```bash
pre-commit run --all-files
cd packages/markitdown
hatch run test:pytest tests/twoways/test_pdf_*.py -q
```

Never commit a temporary formatter/workflow diagnostic to the final H11 diff. If GitHub Black disagrees, obtain the exact canonical diff, apply only it, and remove diagnostic artifacts before final verification.

**Step 4: Trigger/fetch exact-head CI.**

The exact final H11 SHA must have:

- pre-commit SUCCESS;
- package tests Python 3.10 SUCCESS;
- package tests Python 3.11 SUCCESS;
- package tests Python 3.12 SUCCESS;
- package tests Python 3.13 SUCCESS;
- OCR tests Python 3.10 SUCCESS;
- OCR tests Python 3.11 SUCCESS;
- OCR tests Python 3.12 SUCCESS;
- OCR tests Python 3.13 SUCCESS.

Completion authority is **9/9 GREEN on one exact H11 source/docs head**. A superseded earlier run does not count.

## Task 10: Freeze provenance and Ready-for-review handoff

**Files:** PR metadata only; no source/docs commit after exact-head 9/9.

**Step 1: Create/update the H11 PR stacked on H10.**

Base branch must be `phase-h10-pdf-uri-link-preservation`; head `phase-h11-pdf-acroform-text-value-preservation`.

PR body records:

- exact H10 base SHA;
- exact frozen H11 head SHA;
- approved capability boundary and explicit exclusions;
- exact changed-file scope audit;
- protected one-way converter blob;
- exact workflow run/job IDs for all 9 GREEN gates;
- statement that no source/docs commit follows the final gate.

**Step 2: Resolve review threads or document none exist.**

Any valid review defect must be fixed with regression coverage and then requires a fresh exact-head 9/9 gate. Do not mark stale evidence as current.

**Step 3: Mark PR Ready for review.**

Leave it open/unmerged unless the user explicitly authorizes merge.

**Step 4: Freeze.**

After the final successful proof, no commits may be added to H11. Any H12 tranche must branch directly from the exact frozen H11 SHA.
