# MarkItDown 2Ways Phase H27 — implementation plan

Date: 2026-09-18
Base: `main@797a90f9f58e85d412e67ae6817d48863e1e55d7`
Design: `2026-09-18-markitdown-2ways-phase-h27-pdf-derived-extraction-parity-design.md`

## Execution discipline

Proceed strict RED -> GREEN. Keep `_pdf_converter.py` byte-identical. Production H27
must be standard-library/internal-only and must never import pdfminer or pdfplumber.

## Task 1 — freeze RED contracts

Add tests for the intended public surface:

- `PdfConverterExtractionSnapshot`
- `PdfDerivedLimits`
- `read_pdf_converter_snapshot_ir`

Lock source acceptance, exact partial-numbering semantics, provenance, identity,
resource limits, bounded reads, DERIVED capabilities, serialization and no-writer API.

Expected state: RED because H27 reader/public symbols do not exist.

## Task 2 — implement pure local reader

Create
`packages/markitdown/src/markitdown/twoways/readers/pdf_converter.py`.

Requirements:

- explicit .pdf/MIME acceptance only;
- bounded source capture <=64 KiB per read;
- immutable extraction snapshot;
- exact duplicated `^\.\d+$` merge algorithm;
- no additional whitespace transformation;
- deterministic source + extraction + Markdown identity;
- one DERIVED text root without native locator;
- explicit no-runtime-dependency provenance;
- no writer.

## Task 3 — public read-only exports

Export the three H27 symbols from:

- `markitdown.twoways.readers`;
- `markitdown.twoways`.

Do not expose an H27 writer/edit symbol.

## Task 4 — one-way regression

Freeze `_pdf_converter.py` at Git blob
`ffbcbd990cfc40a577404c453ebe47bf477c4929`.

Compare H27's local post-process against the unchanged converter helper over adversarial
line sequences. Add one offline converter differential by monkeypatching extractor
dependencies to deterministic in-memory fakes.

## Task 5 — documentation

Extend `TWOWAYS.md` with H27. Make explicit that H27 page/extraction text is derived
and H9-H11 retain all PDF native write authority.

## Task 6 — exact closure

Run pre-commit plus package/OCR matrices on Python 3.10–3.13 at the exact final head.
Repair only demonstrated defects.

After 9/9 GREEN:

1. freeze final head/tree;
2. verify 0-behind relation and final scope;
3. verify protected converter blob;
4. create two-parent synthetic merge and prove exact tree equality;
5. mark PR ready;
6. guarded merge with expected final head;
7. verify post-merge main parents/tree and converter blob.
