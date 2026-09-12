# Phase H2 CSV Source Preservation Implementation Plan

> Execution status: implementation-complete; final completion is determined only by exact-head PR CI. The document intentionally does not require a post-CI “mark green” commit because that would create a new, unverified head.

**Goal:** Add direct typed CSV cell edits that patch only authorized lexical field spans while preserving source encoding/BOM, delimiter, row terminators, untouched field lexemes and all unrequested semantics.

**Spec:** `docs/superpowers/specs/2026-09-12-markitdown-2ways-phase-h2-csv-source-preservation-design.md`

## Global constraints

- Existing one-way `CsvConverter`, `MarkItDown` API and CLI stay unchanged.
- Production writer never uses `csv.writer`, pandas or whole-document table serialization.
- H1 text representation helpers are reused only for reversible byte/text representation; H1 whole-text patching is not used.
- H2 identity Markdown is read-only.
- No row/column insertion/deletion, sorting, schema/type inference or multiline replacement insertion.
- Every failure before final verification leaves destination untouched.
- Exact-head pre-commit + package 3.10-3.13 + OCR 3.10-3.13 are required before H2 is considered complete.

## Task 1 - Lexical scanner and dialect proof

- [x] Exact field spans, quoted delimiters, doubled quotes, empty fields, blank records, ragged rows, CR/LF/CRLF/mixed terminators and multiline quoted fields are covered.
- [x] Malformed unclosed quotes, quotes in unquoted fields and content after a closing quote fail closed.
- [x] Comma/semicolon/tab/pipe auto-detection and explicit delimiters are deterministic; ambiguity fails closed.
- [x] Scanner semantics are cross-checked against strict `csv.reader`.
- [x] Single-column sources without explicit delimiter remain readable but mutation is read-only.

## Task 2 - Deterministic CSV IR and capability

- [x] CSV source SHA/size, one table canvas/node and stable semantic cells are represented deterministically.
- [x] Cell metadata records character spans, quote/multiline state and raw lexical digest.
- [x] Table metadata records delimiter, encoding, BOM and row terminator evidence.
- [x] `update_csv_cells` is writable only when representation and dialect proof are sufficient.
- [x] `CsvIRReader` accepts only `.csv`, `text/csv` and `application/csv` evidence.
- [x] `update_csv_cells` is registered as a stable edit type without a schema-version bump.

## Task 3 - Writer source authority and edit preflight

- [x] Zero-edit output is byte-identical.
- [x] Source SHA/size mismatch fails before destination output.
- [x] Wrong edit type/target, malformed payloads, bool/non-int/negative coordinates, non-string values, duplicates/out-of-order coordinates and no-op changes fail closed.
- [x] Stale `old_text`, missing native coordinates, forged locators and read-only sources fail before output.
- [x] Actual source is re-scanned and every coordinate/span/raw digest is revalidated against the IR before mutation.

## Task 4 - Target-only lexical rendering

- [x] Unquoted targets remain unquoted when safe.
- [x] Existing quoted targets remain quoted.
- [x] Quote characters are doubled correctly.
- [x] Quotes are introduced only when the requested semantic value requires them.
- [x] CR/LF insertion is rejected in H2.
- [x] Multi-cell updates are span-based and cannot corrupt later offsets.
- [x] Delimiters and record syntax outside target spans are never regenerated.

## Task 5 - Encoded untouched-byte preservation

- [x] UTF-8 BOM, UTF-16 LE/BE BOM and reversible legacy-codec mutation paths are covered.
- [x] Incremental character-to-byte boundaries are checked against strict whole-text encoding.
- [x] Every untouched encoded byte segment and BOM must remain exact.
- [x] Stateful codec leakage outside an authorized target is rejected before output.

## Task 6 - Candidate re-read and semantic preservation

- [x] Candidate output is re-read using the recorded delimiter and encoding.
- [x] Requested cells and every unrequested cell are verified.
- [x] Row/column structure and materialized coordinate set are verified.
- [x] Delimiter, encoding, BOM and physical row-terminator metadata are verified.
- [x] Candidate verifier regressions cover unrelated semantic drift, structure drift and representation drift.

## Task 7 - Identity-Markdown safety and public imports

- [x] Public `CsvIRReader`, `CsvPatchWriter`, `read_csv_ir` and `patch_csv` imports are covered.
- [x] CSV identity projection advertises no editable capability in H2.
- [x] Unchanged identity projection imports to zero edits.
- [x] Generic Markdown table importer was not widened to create an unsafe CSV path.

## Task 8 - Documentation and verification preparation

- [x] `TWOWAYS.md` documents H2 direct CSV behavior, quoting rules and read-only boundaries.
- [x] One-way `CsvConverter` behavior has a dedicated regression test and production converter code is unchanged.
- [x] Full package and OCR matrices were observed green before formatter-only cleanup.
- [x] Black/pre-commit formatter output was captured and applied exactly; diagnostic workflow was removed.
- [x] Diff review found no H1/one-way/JSON/XML/HTML scope creep.
- [x] Final exact-head CI is the sole completion gate and must be read from PR checks without creating a follow-up documentation commit.

## Completion gate

H2 is complete only when the exact final branch head is green across pre-commit, package tests and OCR tests on Python 3.10-3.13. A successful older commit does not satisfy this gate.

After H2 is exact-head green, Phase H3 begins JSON lexical token/subtree patching on a new stacked branch from the verified H2 content.
