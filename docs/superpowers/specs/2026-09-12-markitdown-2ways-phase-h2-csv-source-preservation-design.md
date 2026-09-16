# MarkItDown 2Ways Phase H2 CSV Source Preservation Design

## Status

Execution design for the CSV tranche of the approved v0.5.0 text/structured parity program. H2 is stacked on the exact-head-green H1 text source substrate at `88da1f2f060498b6d11aed3784561e3242be4466`.

H2 is intentionally narrower than a generic CSV editor. It adds deterministic CSV semantics and source-preserving cell mutation while proving lexical ownership of each changed field. It does not route writes through the existing one-way `CsvConverter`, pandas, or `csv.writer`.

## Goal

Add a native CSV round-trip path:

```text
CSV bytes -> reversible text representation -> lexical CSV spans -> DocumentIR
         -> typed update_csv_cells -> target-only lexical patch -> verified CSV bytes
```

A writable source must preserve source encoding, BOM, all untouched field lexemes, delimiters, row terminators, row order, blank records, quoting outside requested fields, and all unrequested cell semantics.

## Non-goals

- no whole-document CSV serialization;
- no pandas/dataframe writer;
- no dialect normalization;
- no automatic delimiter conversion;
- no row/column insertion or deletion;
- no sorting, header inference, type inference, schema coercion, or formula semantics;
- no generic text `replace_text` fallback;
- no editable identity-Markdown path in H2;
- no JSON/XML/HTML work in this tranche;
- no network, subprocess, database, spreadsheet, or workflow features.

## Public surface

Create `markitdown.twoways.formats.csv` with a focused API:

- `read_csv_ir(source, *, filename=None, mimetype=None, encoding=None, delimiter=None) -> DocumentIR`
- `patch_csv(document, source, destination, *, edits=()) -> WriterResult`
- `CsvIRReader`
- `CsvPatchWriter`

Lexical scanner/dialect models remain internal unless a later tranche demonstrates a stable public need.

## Reuse from H1

H2 may reuse only the representation primitives proven by H1:

- `TextRepresentation`
- `decode_text_source`
- `encode_text_source`

H2 must not call H1 `patch_text`, because a CSV edit must preserve lexical field ownership rather than replace the whole decoded document.

H1 newline classification is informational only for CSV. Mixed physical row terminators do not automatically make CSV read-only because H2 patches field spans and leaves every untouched terminator byte in place.

## CSV lexical model

The native scanner operates on the exact decoded source text before any universal-newline conversion.

Each materialized field records:

- zero-based `row` and `column`;
- semantic decoded `value`;
- exact character span `[start, end)` of the field lexeme, including surrounding quotes when quoted but excluding delimiter and row terminator;
- whether the field was quoted;
- digest of the original raw lexeme;
- whether the field contains embedded CR/LF characters;
- stable lexical writability/reason metadata.

Each row records its exact terminator (`\r\n`, `\n`, `\r`, or EOF) separately from fields. Delimiters and row terminators are never part of a field edit span.

### First-tranche grammar

H2 supports RFC-4180-like lexical rules with deliberate restrictions:

- one-character delimiter;
- candidate auto-detect delimiters: comma, semicolon, tab, pipe;
- quote character is `"`;
- quoted fields escape quotes by doubled `""`;
- delimiters and CR/LF may appear inside quoted source fields;
- an unquoted field containing an unescaped quote is malformed;
- after a closing quote, only delimiter, row terminator, or EOF is accepted;
- `escapechar` and backslash-escape dialects are outside H2;
- `skipinitialspace` semantics are outside H2;
- malformed or structurally ambiguous input fails closed rather than being repaired.

Blank physical records are preserved. Rows may have different field counts; `TablePayload.columns` is the maximum observed width, while only actual native fields are materialized as cells. Missing coordinates are not writable.

## Dialect resolution

The reader accepts an optional explicit `delimiter=`. An explicit delimiter must be one non-newline character and is authoritative after lexical/semantic validation.

Without `delimiter=`, H2 performs deterministic candidate evaluation rather than trusting `csv.Sniffer` as proof:

1. scan candidates from the fixed set `, ; TAB |` while respecting quoted regions;
2. validate each candidate through both the lexical scanner and Python `csv.reader(..., strict=True)` configured with `quotechar='"'`, `doublequote=True`, `escapechar=None`, `skipinitialspace=False`;
3. prefer a unique candidate that produces delimiter evidence outside quotes and a coherent multi-field parse;
4. if no delimiter occurs outside quotes, expose a conventional one-column semantic view using comma but mark mutation read-only with `csv.dialect.unproven_single_column` unless the caller supplies `delimiter=`;
5. if multiple candidates remain materially plausible, fail closed with `csv.dialect.ambiguous` instead of inventing source semantics.

`csv.Sniffer` may be used only as diagnostic evidence, never as sole write authority.

## IR mapping

A CSV source maps to one `Canvas(kind="table")` and one `Node(kind="table", semantic_role="csv-grid")` with `TablePayload`.

The table native locator is:

```text
backend = "csv"
part_uri = "/"
object_id = "table"
```

Each `TableCell.text` is the exact semantic string value returned by the validated CSV parse. Cell metadata contains at minimum:

- `csv.row`
- `csv.column`
- `csv.char_start`
- `csv.char_end`
- `csv.quoted`
- `csv.multiline`
- `csv.raw_digest`
- `csv.present = true`
- `csv.writable`
- `csv.reason_code`

The table node records:

- `csv.delimiter`
- `csv.quotechar = '"'`
- `csv.doublequote = true`
- `csv.escapechar = null`
- `csv.skipinitialspace = false`
- `csv.encoding`
- `csv.bom`
- `csv.byte_roundtrip`
- physical row-terminator kinds observed
- `csv.identity_markdown = false`

The `SourceDescriptor` records `format="csv"`, SHA-256, size, filename/mimetype and `preserved_source_ref="csv:sha256:<digest>"`.

## Capability contract

H2 introduces direct typed operation `update_csv_cells`.

The table node advertises it as writable only when:

- decoded bytes are exactly reversible under the recorded encoding/BOM;
- delimiter is explicit or uniquely proven;
- lexical and `csv.reader` semantics agree exactly for every materialized field;
- all field spans are non-overlapping and bounded;
- first-tranche quote/doublequote restrictions hold.

Writable constraints include:

```json
{
  "source_preservation": "lexical-field-spans",
  "identity_markdown": false,
  "target_only": true,
  "structural_edits": false
}
```

Stable read-only/fail-closed reasons include:

- `csv.encoding.not_roundtrippable`
- `csv.dialect.unproven_single_column`
- `csv.dialect.ambiguous`
- `csv.dialect.unsupported`
- `csv.structure.malformed`
- `csv.cell.missing_native_field`
- `csv.cell.multiline_replacement_unsupported`

Identity Markdown remains inspection-only for CSV in H2. The existing generic table importer is semantic and cannot prove preservation of source delimiter/quotes/blank records, so it must not manufacture `update_csv_cells` edits.

## Edit contract

Add `update_csv_cells` to the stable edit-type registry.

Payload:

```json
{
  "cells": [
    {
      "row": 0,
      "column": 1,
      "old_text": "North",
      "text": "South"
    }
  ]
}
```

Rules:

- row/column are zero-based integers; booleans are rejected;
- coordinates must exist as native fields;
- coordinates are unique and supplied in deterministic ascending `(row, column)` order;
- `old_text` and `text` must be strings;
- stale `old_text` fails before mutation;
- no-op cell updates fail before mutation;
- unknown keys fail closed;
- duplicate coordinates fail closed;
- row/column structure cannot change;
- optional existing `EditPrecondition` semantic/native-locator checks remain authoritative.

Multiple cell changes belong in one `update_csv_cells` operation targeting the single CSV table node. H2 does not accept multiple operations targeting the same CSV document in one patch call.

## Target field rendering

The writer never calls `csv.writer` for output.

For each requested target:

1. if the source field was quoted, keep it quoted and escape each quote as doubled `""`;
2. if the source field was unquoted and the replacement contains no delimiter, quote character, CR, or LF, keep it unquoted;
3. if an unquoted source field requires quoting because the replacement contains delimiter or quote character, H2 may introduce quotes only around that target field and reports high fidelity rather than exact target-lexeme preservation;
4. replacement text containing CR or LF is rejected in H2 even though existing quoted multiline source fields may be read; a later tranche may add a proven multiline insertion policy.

No other field's quote state may change.

## Character-span patching

All edits are applied to the decoded source by exact original character spans. Spans are processed from the end of the document toward the beginning so earlier offsets remain valid. No delimiter or row terminator is regenerated.

The writer keeps the original source text and candidate text plus a mapping from original target spans to candidate target spans.

## Encoding and untouched-byte proof

After lexical edits, the full candidate text is encoded with the H1 representation primitive so original BOM/encoding are retained. H2 then proves source locality at the byte layer.

To avoid assumptions about single-byte or stateless codecs, a helper incrementally encodes text character-by-character using the recorded Python codec and records emitted-byte boundaries. It verifies that incremental encoding plus final flush equals the normal strict payload encoding.

Using original and candidate character-boundary maps, the writer compares every untouched segment between authorized target spans. Every untouched original byte segment must be exactly equal to the corresponding candidate byte segment. Any stateful-encoding drift outside target spans raises `RoundTripVerificationError` before output.

BOM bytes must remain identical.

## Transactional writer

`CsvPatchWriter` executes:

1. read source bytes fully;
2. verify SHA-256 and size against `DocumentIR.source`;
3. validate document and the complete edit set;
4. require the authoritative CSV table locator and writable `update_csv_cells` capability;
5. validate semantic/native edit preconditions;
6. decode/re-scan the actual source with the recorded encoding and delimiter;
7. prove the current lexical model still matches IR values/spans/raw digests;
8. validate every requested coordinate and `old_text`;
9. render only requested target field lexemes;
10. apply exact character-span replacements;
11. encode candidate with original encoding/BOM;
12. verify untouched byte segments are byte-identical;
13. re-read candidate through `read_csv_ir(..., delimiter=<recorded delimiter>)`;
14. verify all requested cells equal requested text;
15. verify every unrequested cell semantic value/coordinate is unchanged and row/column structure is unchanged;
16. verify dialect, encoding and BOM remain within contract;
17. write destination only after every check passes.

With zero edits, output is the original byte sequence exactly.

## Verification requirements

Focused tests must prove:

- deterministic lexical spans and IR digests;
- comma/semicolon/tab/pipe detection when uniquely provable;
- explicit delimiter override;
- quoted delimiters and doubled quotes;
- embedded newlines in existing quoted fields;
- CRLF/LF/CR and mixed physical row terminators remain untouched;
- blank records and ragged rows are preserved;
- ambiguous dialect fails closed and unproven one-column CSV is direct-read-only without explicit delimiter;
- UTF-8, UTF-8 BOM, UTF-16 BOM and reversible legacy encodings preserve representation;
- no-op output is byte-identical;
- unquoted target remains unquoted when possible;
- quoted target remains quoted;
- quote insertion is limited to the authorized target field when necessary;
- quote characters are doubled correctly;
- newline insertion is rejected;
- stale source, stale old value, forged locator, duplicate/out-of-order coordinates, malformed payload and missing native cell fail before output;
- untouched decoded spans and untouched encoded byte segments remain exact;
- candidate re-read verifies requested values and all unrequested values;
- identity Markdown exposes no editable CSV capability;
- public imports are stable;
- existing one-way `CsvConverter` output remains unchanged;
- full package tests, OCR tests, pre-commit, Python 3.10-3.13 and exact-head verification are green.

## Follow-on boundary

H3 should address JSON with syntax-aware lexical token spans; XML and HTML follow with subtree/source-span ownership. None may use a parser's general serializer as evidence of safe writeback.
