# MarkItDown 2Ways Phase H27 — PdfConverter derived extraction parity

Date: 2026-09-18
Status: frozen design
Base: `main@797a90f9f58e85d412e67ae6817d48863e1e55d7`

## Purpose

H27 closes the remaining human-readable semantic gap between the existing one-way
`PdfConverter` and the native-safe H9-H11 PDF authority.

H9-H11 deliberately own only narrow native mutation surfaces: existing Document
Information text values, existing URI-link targets, and existing safe terminal plain-text
AcroForm values. They do not claim that page text extraction is native writable content.

H27 therefore adds a separate derived reader. The caller supplies:

1. the exact PDF source bytes; and
2. an already-materialized extraction snapshot representing the text produced by the
   one-way converter immediately before its final deterministic partial-numbering
   post-processing step.

Production H27 performs no PDF parsing, pdfplumber extraction, pdfminer extraction,
network access, browser automation or subprocess execution.

## Protected one-way authority

The protected converter is:

- file: `packages/markitdown/src/markitdown/converters/_pdf_converter.py`
- Git blob at H27 base: `ffbcbd990cfc40a577404c453ebe47bf477c4929`
- converter: `PdfConverter`

H27 freezes the following one-way semantics:

- accepted extension: `.pdf`;
- accepted MIME prefixes: `application/pdf`, `application/x-pdf`;
- final local transform: `_merge_partial_numbering_lines(text)`;
- MasterFormat-style partial numbering matches exactly `^\.\d+$`;
- when a line consists only of partial numbering, it is merged with the next non-empty
  line using one ASCII space;
- empty lines skipped between the numbering token and merged content disappear;
- a terminal numbering-only line with no later non-empty content remains unchanged;
- all other lines preserve their text and relative sequence;
- output is not implicitly stripped by the post-process helper.

H27 must not edit `_pdf_converter.py`.

## Snapshot contract

H27 introduces `PdfConverterExtractionSnapshot`:

- `extracted_text: str` — exact caller-materialized text immediately before
  `_merge_partial_numbering_lines`;
- `provider: str` — non-empty materialization identity;
- `extraction_path: str` — non-empty descriptive path such as
  `pdfminer-whole-document`, `pdfplumber-mixed`, or `pdfminer-fallback`;
- optional `materialization_id: str`.

`extraction_path` is provenance only. H27 does not pretend to verify which external
extractor actually produced the snapshot.

The extracted text may be empty.

## Source acceptance boundary

H27 mirrors only the explicit one-way registration surface:

- extension `.pdf`, case-insensitive;
- MIME starting with `application/pdf` or `application/x-pdf`, case-insensitive.

It does not add signature sniffing or claim authority for arbitrary bytes.

The exact source bytes are SHA-256 bound and size bound. H27 does not claim structural
PDF validity; H9-H11 remain the native structural authority for mutation.

## Derived projection

Visible Markdown is:

`_merge_partial_numbering_lines(snapshot.extracted_text)`

implemented locally with the same pattern and line algorithm as the unchanged one-way
converter.

No other normalization, stripping, table reconstruction or whitespace cleanup occurs.

## Capability boundary

The sole root node has no native locator.

`replace_text` is `CapabilityState.DERIVED` with:

- reason: `pdf.output.not_native_writable`;
- `identity_markdown=False`;
- `native_owner=False`;
- `remote_writeback=False`;
- `materialization="explicit-local-only"`.

H27 adds no PDF writer or edit operation. H9-H11 remain the only PDF native mutation
paths.

## Provenance envelope

H27 records `twoways.pdf_converter_snapshot.v1` including:

- exact source SHA-256 and byte size;
- filename/MIME/extension/URI when supplied;
- acceptance authority (extension or MIME);
- provider;
- extraction path;
- optional materialization ID;
- extracted-text SHA-256 and UTF-8 size;
- derived Markdown SHA-256 and UTF-8 size;
- converter identity and frozen Git blob;
- `pdf_parsing_performed_by_twoways=False`;
- `pdfminer_executed_by_twoways=False`;
- `pdfplumber_executed_by_twoways=False`;
- `network_performed_by_twoways=False`;
- `subprocess_performed_by_twoways=False`;
- `extraction_path_verified_by_twoways=False`.

Source and materialized extraction are independent identity authorities.

## Resource budgets

`PdfDerivedLimits` independently bounds:

- source bytes;
- extracted-text UTF-8 bytes;
- final Markdown UTF-8 bytes.

Source capture uses read requests no larger than 64 KiB. Limits are positive integers;
booleans and non-integers fail closed. Exact boundaries are accepted; one byte over is
rejected.

## Dependency discipline

The production H27 reader must not import or execute:

- `pdfminer`;
- `pdfplumber`;
- requests/httpx/urllib network clients;
- socket;
- subprocess;
- sleep/retry machinery.

The one-way converter may be imported only by dedicated regression tests.

## Required courts

H27 completion requires:

1. explicit extension/MIME acceptance parity;
2. exact partial-numbering merge parity;
3. skipped-empty-line merge behavior;
4. terminal partial-number preservation;
5. non-matching line preservation;
6. exact source/extraction/Markdown digest binding;
7. independent source-vs-extraction document identity;
8. exact source/extraction/Markdown budget boundaries;
9. bounded source reads;
10. invalid snapshot descriptor fail-closed behavior;
11. DERIVED/no-native capability state;
12. canonical serialization determinism;
13. public read-only exports with no writer symbols;
14. production pdfminer/pdfplumber/network/process firewall;
15. frozen `_pdf_converter.py` Git blob;
16. pure helper differential against unchanged `_merge_partial_numbering_lines`;
17. offline full converter differential using in-memory fake pdfplumber/pdfminer behavior.

## Closure rule

The exact final H27 head must pass:

- pre-commit;
- package Python 3.10, 3.11, 3.12, 3.13;
- OCR Python 3.10, 3.11, 3.12, 3.13.

Only after exact 9/9 GREEN may H27 freeze head/tree, prove a two-parent synthetic merge
against the exact frozen base, verify tree equality, mark the PR ready, perform an
expected-head guarded merge and re-verify main plus the protected converter blob.
