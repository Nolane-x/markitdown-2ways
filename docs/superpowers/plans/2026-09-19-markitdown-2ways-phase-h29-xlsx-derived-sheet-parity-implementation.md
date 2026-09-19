# MarkItDown 2Ways Phase H29 — implementation plan

Date: 2026-09-19
Base: `main@2dcf127700151a28aff6a12eb52d23dde8b48aa9`
Design: `2026-09-19-markitdown-2ways-phase-h29-xlsx-derived-sheet-parity-design.md`

## Execution discipline

Proceed strict RED -> GREEN. Keep `_xlsx_converter.py` byte-identical. Production H29
must be standard-library/internal-only and must not parse XLSX or execute
pandas/openpyxl/HtmlConverter.

## Task 1 — freeze RED contracts

Add courts for:

- `XlsxSheetMarkdownSnapshot`
- `XlsxConverterSnapshot`
- `XlsxDerivedLimits`
- `read_xlsx_converter_snapshot_ir`

Lock acceptance, ordered sheet assembly, strip semantics, provenance, identity, budgets,
bounded reads, DERIVED capabilities, no-writer exports and native-XLSX non-regression.

Expected state: RED because H29 reader/public symbols do not exist.

## Task 2 — implement pure derived reader

Create
`packages/markitdown/src/markitdown/twoways/readers/xlsx_converter.py`.

Requirements:

- explicit .xlsx/MIME acceptance only;
- source reads <=64 KiB;
- immutable ordered sheet snapshots;
- unique non-empty sheet names;
- exact one-way sheet-heading/per-sheet-strip/final-strip assembly;
- source, raw sheet, stripped sheet and final output digest binding;
- deterministic identity that includes sheet order;
- one DERIVED text root with no native locator;
- explicit no-parser/no-runtime-dependency evidence;
- no writer.

## Task 3 — public read-only exports

Export all four H29 symbols from:

- `markitdown.twoways.readers`;
- `markitdown.twoways`.

Do not expose an H29 writer/edit symbol.

## Task 4 — one-way regression

Freeze `_xlsx_converter.py` at Git blob
`355dd8f8d74ab5c9a40bba37e1f7a7d601eeba27`.

Differential test the unchanged `XlsxConverter` with:

- deterministic fake ordered frames from patched `_read_xlsx_sheets`;
- fake frame `to_html(index=False)`;
- fake instance `HtmlConverter.convert_string` outputs.

Compare exact final Markdown to H29.

## Task 5 — native authority non-regression

Assert H29 exports no writer and does not modify native XLSX files. Existing
`read_xlsx_ir` / `patch_xlsx` APIs and identity Markdown remain the only native
XLSX mutation authority.

## Task 6 — documentation

Extend `TWOWAYS.md` with H29 and update the derived support/gate matrix to H18-H29.

## Task 7 — exact closure

Run exact final pre-commit plus package/OCR Python 3.10–3.13 matrices. Repair only
demonstrated defects.

After 9/9 GREEN:

1. freeze final head/tree;
2. verify branch is 0 behind and scope is H29-only;
3. verify protected converter blob;
4. create two-parent synthetic merge and prove exact tree equality;
5. mark PR ready;
6. guarded merge with expected final head;
7. verify post-merge main parents/tree and converter blob.
