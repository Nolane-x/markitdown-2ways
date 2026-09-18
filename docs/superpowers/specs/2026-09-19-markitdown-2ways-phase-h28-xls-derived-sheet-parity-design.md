# MarkItDown 2Ways Phase H28 — XlsConverter derived sheet parity

Date: 2026-09-19
Status: frozen design
Base: `main@e5b9ed1b65c8d6be713534b259f28b71299f348f`

## Purpose

H28 closes the remaining human-readable semantic gap between the unchanged one-way
`XlsConverter` and H17's deliberately narrow native BIFF8 NUMBER-slot authority.

H17 proves native ownership only for existing BIFF8 NUMBER records and permits exact
8-byte Xnum replacement while preserving CFB/BIFF topology. It does not claim that the
full workbook table Markdown produced by pandas + HtmlConverter is native writable
content.

H28 therefore adds a read-only derived adapter. The caller supplies:

1. exact XLS source bytes; and
2. an ordered tuple of already-materialized per-sheet Markdown values, each value
   representing the exact `HtmlConverter.convert_string(DataFrame.to_html(index=False),
   **kwargs).markdown` result for that sheet before `XlsConverter` applies its local
   `.strip()` and workbook scaffold.

Production H28 performs no CFB/BIFF parsing, pandas execution, xlrd execution,
DataFrame construction, HTML rendering, BeautifulSoup parsing, markdownify execution,
network access or subprocess execution.

## Protected one-way authority

The protected converter file is:

- file: `packages/markitdown/src/markitdown/converters/_xlsx_converter.py`
- Git blob at H28 base: `355dd8f8d74ab5c9a40bba37e1f7a7d601eeba27`
- target converter: `XlsConverter`

H28 freezes only the `XlsConverter` semantics below:

- accepted extension: `.xls`, case-insensitive;
- accepted MIME prefixes: `application/vnd.ms-excel`, `application/excel`;
- `pd.read_excel(..., sheet_name=None, engine="xlrd")` determines ordered sheet names;
- for each sheet in iteration order:
  - append `## {sheet_name}\n`;
  - append `sheet_markdown.strip()`;
  - append `\n\n`;
- apply final `md_content.strip()`;
- no title is produced by `XlsConverter`.

H28 does not claim to reproduce pandas/xlrd/DataFrame-to-HTML/HtmlConverter semantics
from native XLS bytes. Those stages are caller-materialized derived evidence.

H28 must not edit `_xlsx_converter.py`.

## Snapshot contract

H28 introduces two immutable public contracts.

### XlsSheetMarkdownSnapshot

Fields:

- `name: str` — non-empty sheet name;
- `markdown: str` — exact caller-materialized per-sheet Markdown before the one-way
  per-sheet `.strip()`;
- optional `materialization_id: str`.

The Markdown string may be empty and may contain arbitrary leading/trailing whitespace.
Those bytes are provenance-relevant because `XlsConverter` strips them before assembly.

### XlsConverterSnapshot

Fields:

- `sheets: tuple[XlsSheetMarkdownSnapshot, ...]`;
- `provider: str` — non-empty materializer identity;
- optional `materialization_id: str`;
- optional `table_provider: str` describing the external pandas/xlrd/DataFrame stage;
- optional `html_markdown_provider: str` describing the external HtmlConverter stage.

The sheet tuple must be non-empty. Sheet names must be unique and order is
identity-bearing. This mirrors the ordered mapping returned by `pd.read_excel(...,
sheet_name=None)` and avoids ambiguous caller evidence.

## Source acceptance boundary

H28 mirrors only the explicit one-way `XlsConverter.accepts()` surface:

- extension `.xls`, case-insensitive;
- MIME starting with `application/vnd.ms-excel` or `application/excel`,
  case-insensitive.

No OLE/CFB signature sniffing is added. H17 remains the native structural authority.

## Derived projection

For each snapshot sheet in order:

```text
## {sheet.name}
{sheet.markdown.strip()}

```

All sheet blocks are concatenated and the final result is `.strip()`.

This means:

- leading/trailing whitespace in a materialized sheet Markdown value is omitted from
  visible output but retained in snapshot provenance/digests;
- empty materialized sheet Markdown yields only the sheet heading in visible output;
- sheet order is preserved exactly;
- no additional blank-line normalization is performed beyond the one-way assembly;
- no Markdown table parsing/reconstruction is performed.

## Capability boundary

The derived workbook root has no native locator.

`replace_text` is `CapabilityState.DERIVED` with:

- reason: `xls.output.not_native_writable`;
- `identity_markdown=False`;
- `native_owner=False`;
- `remote_writeback=False`;
- `materialization="explicit-local-only"`.

H28 adds no XLS writer/edit operation. H17 remains the only XLS native mutation path.

## Provenance envelope

H28 records `twoways.xls_converter_snapshot.v1` including:

- exact source SHA-256 and byte size;
- filename/MIME/extension/URI when supplied;
- acceptance authority (extension or MIME);
- provider and optional materialization descriptors;
- ordered sheet count;
- ordered sheet names;
- for every sheet:
  - index;
  - name;
  - raw Markdown SHA-256 and UTF-8 size;
  - stripped Markdown SHA-256 and UTF-8 size;
  - optional per-sheet materialization ID;
- final workbook Markdown SHA-256 and UTF-8 size;
- converter identity and frozen Git blob;
- `cfb_biff_parsing_performed_by_twoways=False`;
- `pandas_executed_by_twoways=False`;
- `xlrd_executed_by_twoways=False`;
- `html_conversion_executed_by_twoways=False`;
- `network_performed_by_twoways=False`;
- `subprocess_performed_by_twoways=False`.

Source bytes and every ordered sheet materialization are independent identity
authorities.

## Resource budgets

`XlsDerivedLimits` independently bounds:

- source bytes;
- number of materialized sheets;
- aggregate raw per-sheet Markdown UTF-8 bytes;
- final workbook Markdown UTF-8 bytes.

Source capture uses read requests no larger than 64 KiB. Limits are positive integers;
booleans and non-integers fail closed. Exact boundaries are accepted; one unit over is
rejected.

## Dependency discipline

Production H28 must not import or execute:

- pandas;
- xlrd;
- openpyxl;
- BeautifulSoup/bs4;
- markdownify;
- `HtmlConverter`;
- `XlsConverter`;
- network clients/sockets;
- subprocess;
- sleep/retry machinery.

The one-way converter may be imported only by dedicated regression tests.

## Required courts

H28 completion requires:

1. explicit extension/MIME acceptance parity;
2. exact ordered sheet scaffold assembly;
3. exact per-sheet `.strip()` behavior;
4. exact final `.strip()` behavior;
5. empty-sheet-Markdown behavior;
6. sheet-order preservation;
7. duplicate/blank sheet-name rejection;
8. exact source and ordered sheet digest binding;
9. source-vs-sheet-vs-order document identity independence;
10. exact source/sheet-count/raw-Markdown/final-Markdown budget boundaries;
11. bounded source reads;
12. invalid snapshot descriptor fail-closed behavior;
13. DERIVED/no-native capability state;
14. canonical serialization determinism;
15. public read-only exports with no writer symbols;
16. production pandas/xlrd/HTML/runtime/network/process firewall;
17. frozen `_xlsx_converter.py` Git blob;
18. offline full `XlsConverter` differential using deterministic fake pandas frames and
    fake HtmlConverter outputs.

## Closure rule

The exact final H28 head must pass:

- pre-commit;
- package Python 3.10, 3.11, 3.12, 3.13;
- OCR Python 3.10, 3.11, 3.12, 3.13.

Only after exact 9/9 GREEN may H28 freeze head/tree, prove a two-parent synthetic merge
against the exact frozen base, verify tree equality, mark the PR ready, perform an
expected-head guarded merge and re-verify main plus the protected converter blob.
