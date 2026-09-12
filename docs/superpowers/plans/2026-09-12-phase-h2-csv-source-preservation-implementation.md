# Phase H2 CSV Source Preservation Implementation Plan

> Execute with TDD. H2 starts only from exact-head-green H1 (`88da1f2f060498b6d11aed3784561e3242be4466`). Do not modify H1 behavior unless an H2 regression proves a shared primitive defect.

**Goal:** Add direct typed CSV cell edits that patch only authorized lexical field spans while preserving source encoding/BOM, delimiter, row terminators, untouched field lexemes and all unrequested semantics.

**Spec:** `docs/superpowers/specs/2026-09-12-markitdown-2ways-phase-h2-csv-source-preservation-design.md`

## Global constraints

- Existing one-way `CsvConverter`, `MarkItDown` API and CLI stay unchanged.
- Production writer must never use `csv.writer`, pandas or whole-document table serialization.
- H1 text representation helpers may be reused; H1 whole-text patching may not.
- H2 identity Markdown is read-only.
- No row/column insertion/deletion, sorting, schema/type inference or multiline replacement insertion.
- Every failure before final verification leaves destination untouched.
- Exact-head pre-commit + package 3.10-3.13 + OCR 3.10-3.13 are required before H2 is considered complete.

## Task 1 - Lexical scanner and dialect proof

**Files**
- Create `packages/markitdown/tests/twoways/test_csv_lexical.py`
- After RED create `packages/markitdown/src/markitdown/twoways/formats/csv/model.py`
- After RED create `packages/markitdown/src/markitdown/twoways/formats/csv/lexical.py`

- [ ] Write RED tests for exact field spans, quoted delimiters, doubled quotes, empty fields, blank records, ragged rows, CR/LF/CRLF/mixed terminators and multiline quoted fields.
- [ ] Add RED malformed tests for unclosed quote, quote in unquoted field and non-delimiter content after closing quote.
- [ ] Add RED deterministic dialect tests for comma/semicolon/tab/pipe, explicit delimiter and ambiguity.
- [ ] Run focused test and record missing-module/feature RED.
- [ ] Implement immutable lexical field/row/dialect models and a deterministic scanner.
- [ ] Cross-check scanner semantics with strict `csv.reader`; mismatch fails closed.
- [ ] Require unique dialect evidence for writable auto-detected sources; single-column sources without explicit delimiter remain semantically readable but unproven for mutation.
- [ ] Focused tests GREEN.

## Task 2 - Deterministic CSV IR and capability

**Files**
- Create `packages/markitdown/tests/twoways/test_csv_reader.py`
- After RED create `packages/markitdown/src/markitdown/twoways/formats/csv/reader.py`
- Modify after RED `packages/markitdown/src/markitdown/twoways/ir/edits.py` only to register `update_csv_cells`.

- [ ] RED deterministic IR test for SHA/size/source format, one table canvas/node, exact semantic cell values and stable canonical digest.
- [ ] RED metadata tests for char spans, quote state, multiline flag, raw digest and table dialect/encoding/BOM representation.
- [ ] RED capability tests for writable proven dialect and read-only unproven single-column/encoding cases.
- [ ] RED acceptance tests limited to `.csv`, `text/csv`, `application/csv`.
- [ ] Implement `read_csv_ir` and `CsvIRReader` using H1 representation decoding plus H2 lexical scanner.
- [ ] Register `update_csv_cells` as a stable edit type; no schema-version bump unless validation proves one is required.
- [ ] Validate produced `DocumentIR`; focused tests GREEN.

## Task 3 - Writer source authority and edit preflight

**Files**
- Create `packages/markitdown/tests/twoways/test_csv_writer.py`
- After RED create `packages/markitdown/src/markitdown/twoways/formats/csv/writer.py`

- [ ] RED zero-edit byte-identity test.
- [ ] RED source SHA/size mismatch tests with empty destination.
- [ ] RED malformed edit tests: wrong type/target, unknown keys, non-int/bool coordinates, non-string values, duplicate coordinates, out-of-order coordinates, no-op updates, stale `old_text`, missing native coordinate.
- [ ] RED forged locator and read-only capability tests.
- [ ] Implement full edit-set preflight before candidate construction.
- [ ] Re-scan actual source and prove values/spans/raw digests still match IR before applying edits.
- [ ] Focused preflight tests GREEN.

## Task 4 - Target-only lexical rendering

**Files**
- Extend `packages/markitdown/tests/twoways/test_csv_writer.py`
- Modify after RED `packages/markitdown/src/markitdown/twoways/formats/csv/writer.py`

- [ ] RED unquoted->unquoted patch with unchanged delimiter/terminators/neighbors.
- [ ] RED quoted->quoted patch retaining quotes.
- [ ] RED doubled-quote escaping.
- [ ] RED target-only quote introduction when delimiter/quote makes quoting necessary.
- [ ] RED replacement CR/LF rejection.
- [ ] RED multi-cell operation proving descending-span replacement does not corrupt offsets.
- [ ] Implement field renderer and descending exact-span patcher. Never regenerate delimiters or records.
- [ ] Focused tests GREEN.

## Task 5 - Encoded untouched-byte preservation

**Files**
- Create/extend `packages/markitdown/tests/twoways/test_csv_encoding_preservation.py`
- Modify after RED CSV writer/internal helper.

- [ ] RED UTF-8 BOM, UTF-16 LE/BE BOM and reversible legacy codec mutation tests.
- [ ] RED test that only authorized encoded field byte regions can differ.
- [ ] RED test simulating representation drift/stateful codec effects and require `RoundTripVerificationError` before output.
- [ ] Implement incremental character-boundary byte map and verify its complete encoding equals strict whole-text encoding.
- [ ] Compare every untouched source/candidate byte segment; require exact identity plus exact BOM.
- [ ] Focused tests GREEN.

## Task 6 - Candidate re-read and semantic preservation

**Files**
- Extend CSV reader/writer tests.

- [ ] RED candidate verification test where requested target is correct but an unrelated cell changes; writer must reject.
- [ ] RED structure-change verification test.
- [ ] RED dialect/encoding/BOM drift verification test.
- [ ] Re-read candidate with recorded delimiter and encoding.
- [ ] Verify requested cells, all unrequested coordinates/values, row count, materialized coordinate set, dialect and source representation before output.
- [ ] Focused tests GREEN.

## Task 7 - Identity-Markdown safety and public imports

**Files**
- Create `packages/markitdown/tests/twoways/test_csv_public_imports.py`
- Create `packages/markitdown/src/markitdown/twoways/formats/csv/__init__.py`
- Add/extend identity projection regression test only if required.

- [ ] RED public import tests for `CsvIRReader`, `CsvPatchWriter`, `read_csv_ir`, `patch_csv`.
- [ ] Prove H2 CSV table identity projection advertises no editable capability and unchanged projection imports to zero edits.
- [ ] Add minimal lazy/focused public exports.
- [ ] Do not alter generic table importer unless a regression demonstrates unsafe capability leakage.
- [ ] Focused tests GREEN.

## Task 8 - Documentation and exact-head verification

**Files**
- Update `TWOWAYS.md`
- Update this plan status after evidence exists.

- [ ] Document H2 direct CSV path, quoting behavior, read-only boundaries and why generic identity Markdown remains read-only.
- [ ] Add regression ensuring one-way `CsvConverter` output did not change.
- [ ] Run all `tests/twoways`.
- [ ] Run full package matrix Python 3.10-3.13.
- [ ] Run OCR matrix Python 3.10-3.13.
- [ ] Run pre-commit.
- [ ] Review H2 diff for accidental H1/one-way/JSON/XML/HTML scope creep.
- [ ] Require exact final-head green evidence before calling H2 complete.

## Completion gate

H2 is complete only when exact final head is green across pre-commit, package tests and OCR tests on Python 3.10-3.13, with no unresolved review blockers and no unrelated lexical changes in target-only corpus tests.

After H2, begin H3 JSON lexical token/subtree patching on a new stacked branch from the H2 green head.
