# MarkItDown 2Ways Phase H25 — implementation plan

Date: 2026-09-18
Base: `main@68cf686404328158b8e87e8ff00ad0c03734157e`

## Task 1 — RED contract

Add focused courts for the intended public surface:

- `ImageMetadataSnapshot`
- `ImageDescriptionSnapshot`
- `ImageDerivedLimits`
- `read_image_snapshot_ir`

Lock one-way acceptance, metadata ordering, description stripping, content-type
derivation, provenance, identity, budgets, canonical serialization, public exports and
protected converter semantics.

Expected result: RED because production H25 symbols do not yet exist.

## Task 2 — pure local reader

Create `markitdown.twoways.readers.image` using only standard library/internal modules.

Implementation rules:

- accept exact caller source bytes;
- bounded source capture;
- allow only the ten one-way metadata keys;
- deterministic ordered metadata projection;
- optional independently bound description snapshot;
- independently derive one-way LLM content type;
- reconstruct final Markdown exactly;
- one DERIVED root with no native locator;
- no ExifTool/LLM/network/process path.

## Task 3 — read-only public exports

Export H25 symbols from `markitdown.twoways.readers` and `markitdown.twoways`.
Do not add a writer/edit API.

## Task 4 — one-way regression proof

Freeze `_image_converter.py` at
`cd49b96d29f50861625cecfb6cee7bdd1eb30b54`.

Run the unchanged converter offline by monkeypatching:

- `exiftool_metadata`;
- `ImageConverter._get_llm_description`.

Prove metadata-only, description-only and combined H25 output exactly equals one-way
Markdown without invoking subprocess/network.

## Task 5 — docs

Update `TWOWAYS.md` to add H25 and make explicit that H12-H14 retain all native PNG/JPEG
mutation authority.

## Task 6 — exact closure

Run exact final-head 9/9 CI. Repair only demonstrated failures.

After GREEN:

1. freeze final head/tree;
2. verify branch is 0 behind base and audit scope;
3. verify protected ImageConverter blob;
4. create two-parent synthetic merge with exact tree equality;
5. mark PR ready;
6. guarded expected-head merge;
7. verify main parents/tree/blob.
