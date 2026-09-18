# MarkItDown 2Ways Phase H28 — implementation plan

Date: 2026-09-19
Base: `main@e5b9ed1b65c8d6be713534b259f28b71299f348f`
Design: `2026-09-19-markitdown-2ways-phase-h28-xls-derived-sheet-parity-design.md`

## Execution discipline

Proceed strict RED -> GREEN. Keep `_xlsx_converter.py` byte-identical. Production H28
must be standard-library/internal-only and must not import pandas, xlrd or HtmlConverter.

## Task 1 — freeze RED contracts

Add tests for:

- `XlsSheetMarkdownSnapshot`
- `XlsConverterSnapshot`
- `XlsDerivedLimits`
- `read_xls_converter_snapshot_ir`

Lock explicit acceptance, ordered sheet assembly, per-sheet/final strip semantics,
provenance, identity, budgets, bounded reads, DERIVED capabilities and no-writer API.

Expected state: RED because H28 reader/public symbols do not exist.

## Task 2 — implement pure local reader

Create
`packages/markitdown/src/markitdown/twoways/readers/xls_converter.py`.

Requirements:

- explicit .xls/MIME acceptance only;
- bounded source capture <=64 KiB per read;
- immutable ordered sheet snapshots;
- unique non-empty sheet names;
- exact one-way `## name\n + markdown.strip() + "\n\n"` assembly;
- exact final `.strip()`;
- deterministic source + sheet-order + sheet-content + output identity;
- one DERIVED text root without native locator;
- explicit no-runtime-dependency provenance;
- no writer.

## Task 3 — public read-only exports

Export the four H28 symbols from:

- `markitdown.twoways.readers`;
- `markitdown.twoways`.

Do not expose an H28 writer/edit symbol.

## Task 4 — one-way regression

Freeze `_xlsx_converter.py` at Git blob
`355dd8f8d74ab5c9a40bba37e1f7a7d601eeba27`.

Use deterministic offline fakes for `pd.read_excel`, frame `to_html(index=False)` and
the converter instance's `HtmlConverter.convert_string`; compare H28 final Markdown
against the unchanged `XlsConverter`.

## Task 5 — documentation

Extend `TWOWAYS.md` with H28 and make explicit that H28 full-sheet Markdown is derived
while H17 remains the only native XLS mutation authority.

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
