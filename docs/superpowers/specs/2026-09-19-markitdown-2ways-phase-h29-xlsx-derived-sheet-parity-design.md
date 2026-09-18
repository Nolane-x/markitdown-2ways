# MarkItDown 2Ways Phase H29 — XlsxConverter derived sheet parity

Date: 2026-09-19
Status: frozen design
Base: `main@2dcf127700151a28aff6a12eb52d23dde8b48aa9`

## Purpose

H29 closes the remaining human-readable semantic gap between the unchanged one-way
`XlsxConverter` and the native-safe XLSX reader/writer plus identity-Markdown path.

The native XLSX path is authoritative for SpreadsheetML cells and bounded
`update_sheet_cells` mutation. It deliberately preserves typed/native cell semantics.
The one-way converter has different visible semantics: it loads worksheets through
pandas/openpyxl, allows pandas to infer a DataFrame header/schema, renders that frame to
HTML with `index=False`, converts the HTML through `HtmlConverter`, strips each sheet
Markdown, adds a `## sheet-name` scaffold and finally strips the complete workbook.

Those one-way semantics are useful for parity but must not be treated as native XLSX
ownership.

H29 therefore adds a separate read-only derived adapter. The caller supplies:

1. exact XLSX source bytes; and
2. an ordered tuple of already-materialized per-sheet Markdown values, each representing
   the exact `HtmlConverter.convert_string(DataFrame.to_html(index=False),
   **kwargs).markdown` result immediately before the one-way converter applies its local
   per-sheet `.strip()` and workbook scaffold.

Production H29 performs no ZIP/OOXML parsing, pandas execution, openpyxl execution,
DataFrame construction, XLSX repair, HTML rendering, BeautifulSoup parsing, markdownify
execution, network access or subprocess execution.

## Protected one-way authority

Protected converter file:

- `packages/markitdown/src/markitdown/converters/_xlsx_converter.py`
- Git blob at H29 base: `355dd8f8d74ab5c9a40bba37e1f7a7d601eeba27`
- target converter: `XlsxConverter`

H29 freezes only these `XlsxConverter` semantics:

- accepted extension: `.xlsx`, case-insensitive;
- accepted MIME prefix:
  `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`;
- `_read_xlsx_sheets()` produces an ordered mapping of sheet names to DataFrames;
- each frame is rendered with `to_html(index=False)`;
- each HTML value is converted through `HtmlConverter.convert_string(..., **kwargs)`;
- each returned sheet Markdown is `.strip()`-ed;
- output block is `## {sheet_name}\n{stripped_sheet_markdown}\n\n`;
- final workbook output is `.strip()`;
- no document title is produced.

The one-way loader's compatibility fallback for legacy worksheet `showZeroes`
attributes is outside H29's production execution boundary. A caller may describe which
external materialization route was used, but H29 does not claim to verify that route.

H29 must not edit `_xlsx_converter.py`.

## Snapshot contracts

### XlsxSheetMarkdownSnapshot

Fields:

- `name: str` — non-empty worksheet name;
- `markdown: str` — exact materialized sheet Markdown before one-way per-sheet strip;
- optional `materialization_id: str`.

Markdown may be empty and may contain arbitrary leading/trailing whitespace.

### XlsxConverterSnapshot

Fields:

- `sheets: tuple[XlsxSheetMarkdownSnapshot, ...]` — non-empty ordered tuple;
- `provider: str` — non-empty materializer identity;
- optional `materialization_id: str`;
- optional `table_provider: str` — e.g. pandas/openpyxl materializer identity;
- optional `html_markdown_provider: str`;
- optional `materialization_path: str` — descriptive route such as
  `openpyxl-direct` or `openpyxl-showZeroes-repair`.

Sheet names must be unique and order is identity-bearing.

`materialization_path` is descriptive provenance only and is recorded with
`materialization_path_verified_by_twoways=False`.

## Source acceptance boundary

H29 mirrors only the one-way explicit registration surface:

- extension `.xlsx`, case-insensitive; or
- MIME starting with
  `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`,
  case-insensitive.

H29 adds no ZIP signature sniffing and claims no native XLSX structure. The existing
native XLSX reader/writer remains the structural authority.

## Derived projection

For each sheet in order:

```text
## {sheet.name}
{sheet.markdown.strip()}

```

Concatenate all blocks and apply final `.strip()`.

Consequences:

- leading/trailing materialized sheet whitespace is provenance-bearing but omitted from
  visible output;
- an empty sheet Markdown value yields only its heading;
- sheet order is preserved exactly;
- no DataFrame, HTML or Markdown table reconstruction occurs in H29;
- no additional whitespace normalization occurs beyond the unchanged one-way assembly.

## Capability boundary

The H29 root has no native locator.

`replace_text` is `CapabilityState.DERIVED` with:

- reason: `xlsx.output.not_native_writable`;
- `identity_markdown=False`;
- `native_owner=False`;
- `remote_writeback=False`;
- `materialization="explicit-local-only"`.

H29 adds no XLSX writer. Existing `read_xlsx_ir`, identity Markdown and
`patch_xlsx` retain native authority.

## Provenance envelope

H29 records `twoways.xlsx_converter_snapshot.v1` including:

- exact source SHA-256 and byte size;
- filename/MIME/extension/URI when supplied;
- acceptance authority;
- provider and optional materialization descriptors;
- optional descriptive materialization path;
- ordered sheet count and names;
- for each sheet:
  - index and name;
  - raw Markdown SHA-256 and UTF-8 size;
  - stripped Markdown SHA-256 and UTF-8 size;
  - optional sheet materialization ID;
- final workbook Markdown SHA-256 and UTF-8 size;
- converter identity and frozen Git blob;
- `xlsx_parsing_performed_by_twoways=False`;
- `pandas_executed_by_twoways=False`;
- `openpyxl_executed_by_twoways=False`;
- `show_zeroes_repair_executed_by_twoways=False`;
- `html_conversion_executed_by_twoways=False`;
- `network_performed_by_twoways=False`;
- `subprocess_performed_by_twoways=False`;
- `materialization_path_verified_by_twoways=False`.

Source bytes and ordered sheet snapshots are independent identity authorities.

## Resource budgets

`XlsxDerivedLimits` independently bounds:

- source bytes;
- materialized sheet count;
- aggregate raw per-sheet Markdown UTF-8 bytes;
- final workbook Markdown UTF-8 bytes.

Source capture uses requests no larger than 64 KiB. Limits are positive integers;
booleans and non-integers fail closed. Exact boundaries are accepted and one unit over
is rejected.

## Dependency discipline

Production H29 must not import or execute:

- pandas;
- openpyxl;
- zipfile/OOXML parsing for source semantics;
- BeautifulSoup/bs4;
- markdownify;
- `HtmlConverter`;
- `XlsxConverter`;
- `_read_xlsx_sheets`;
- `_repair_sheetview_show_zeroes`;
- network clients/sockets;
- subprocess;
- retry/sleep machinery.

The unchanged one-way converter may be imported only by regression tests.

## Required courts

H29 completion requires:

1. explicit extension/MIME acceptance parity;
2. exact ordered sheet scaffold assembly;
3. exact per-sheet strip behavior;
4. exact final strip behavior;
5. empty-sheet-Markdown behavior;
6. order preservation;
7. blank/duplicate sheet-name rejection;
8. exact source/raw-sheet/stripped-sheet/final-output digest binding;
9. source-vs-sheet-vs-order identity independence;
10. source/sheet-count/raw-Markdown/final-Markdown exact budget boundaries;
11. bounded source reads;
12. invalid snapshot descriptor fail-closed behavior;
13. DERIVED/no-native capability state;
14. canonical serialization determinism;
15. public read-only exports with no writer symbols;
16. production pandas/openpyxl/HTML/repair/network/process firewall;
17. frozen `_xlsx_converter.py` blob;
18. offline full `XlsxConverter` differential using deterministic fake sheet frames and
    fake HtmlConverter outputs;
19. native XLSX public writer/identity contracts remain unchanged.

## Closure rule

The exact final H29 head must pass:

- pre-commit;
- package Python 3.10, 3.11, 3.12, 3.13;
- OCR Python 3.10, 3.11, 3.12, 3.13.

Only after exact 9/9 GREEN may H29 freeze head/tree, prove a two-parent synthetic merge
against the exact frozen base, verify tree equality, mark the PR ready, perform an
expected-head guarded merge and re-verify main plus the protected converter blob.
