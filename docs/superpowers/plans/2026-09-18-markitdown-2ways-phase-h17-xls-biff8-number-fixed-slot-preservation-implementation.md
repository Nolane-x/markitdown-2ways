# Phase H17 — XLS BIFF8 NUMBER fixed-slot preservation implementation plan

## Baseline

- repository: `Nolane-x/markitdown-2ways`
- base: `main@db6d2a82e028195226c2311c67c42cba4cf534eb`
- base tree: `433a80d128641460cb3e343443e5b0ba7a529701`
- H16 is merged and frozen.
- one-way XLS implementation baseline:
  `packages/markitdown/src/markitdown/converters/_xlsx_converter.py`
  blob `355dd8f8d74ab5c9a40bba37e1f7a7d601eeba27`.

The design authority is:
`docs/superpowers/specs/2026-09-18-markitdown-2ways-phase-h17-xls-biff8-number-fixed-slot-preservation-design.md`.

## Completion rule

H17 is not complete because code exists or focused tests pass. Completion requires one
exact final SHA to satisfy the complete 9-job court, scope audit, synthetic merge-tree
equality and guarded merge.

No later task may weaken the frozen design to make a test pass.

## Task 1 — CFB and BIFF parser RED

Add failing tests first:

- `packages/markitdown/tests/twoways/_xls_fixtures.py`
- `packages/markitdown/tests/twoways/test_xls_cfb_parser.py`
- `packages/markitdown/tests/twoways/test_xls_biff_parser.py`

Fixtures must be deterministic byte fixtures, not files generated at test time by an XLS
writer whose output becomes hidden authority.

The RED court must cover:

- valid BIFF8 Workbook stream discovery;
- competing `Book` + `Workbook` stream rejection;
- missing/duplicate Workbook stream rejection;
- CFB chain truncation/cycle/out-of-range cases;
- BIFF record truncation and oversized declarations;
- globals BOF/EOF authority;
- BoundSheet8 parsing and BOF pointer validation;
- ordinary worksheet vs chart/macro/dialog sheet distinction;
- NUMBER record row/column/XF/value decoding;
- duplicate coordinate ownership;
- FILEPASS detection;
- FORMULA presence detection;
- non-finite NUMBER source values.

RED must fail because production H17 parser surfaces do not exist.

## Task 2 — Parser/model GREEN

Create:

- `packages/markitdown/src/markitdown/twoways/formats/xls/limits.py`
- `packages/markitdown/src/markitdown/twoways/formats/xls/model.py`
- `packages/markitdown/src/markitdown/twoways/formats/xls/cfb.py`
- `packages/markitdown/src/markitdown/twoways/formats/xls/biff.py`

Rules:

- parse from bytes only;
- no pandas/xlrd in production authority;
- no serializer;
- no mutation;
- deterministic immutable evidence objects;
- exact logical Workbook-stream to physical-source range mapping;
- complete BIFF record topology evidence;
- all configured limits checked during parsing.

The XLS CFB code remains H17-local in this tranche. Do not refactor H16 MSG CFB code
during H17; cross-format deduplication is a later isolated change after both contracts are
frozen.

GREEN only the parser tests from Task 1.

## Task 3 — Reader/capability RED -> GREEN

Add:

- `packages/markitdown/src/markitdown/twoways/formats/xls/reader.py`
- `packages/markitdown/tests/twoways/test_xls_number_reader.py`
- `packages/markitdown/tests/twoways/test_xls_number_adapters.py`
- `packages/markitdown/tests/twoways/test_xls_number_public_imports.py`

Reader contract:

- `.xls` / supported XLS MIME identity only;
- BIFF8 Workbook stream only;
- worksheet canvases;
- NUMBER-backed numeric cell nodes;
- H17 native locators/digests;
- existing `update_sheet_cells` capability only for eligible NUMBER cells;
- identity Markdown inspection-only;
- globally read-only when FORMULA or FILEPASS blocks mutation;
- unsupported cell record kinds represented as read-only where safely readable.

RED first, then implement.

## Task 4 — Writer RED -> GREEN

Add:

- `packages/markitdown/src/markitdown/twoways/formats/xls/writer.py`
- `packages/markitdown/tests/twoways/test_xls_number_writer.py`

Writer RED cases:

- exact one-cell NUMBER edit;
- multiple disjoint NUMBER edits;
- zero-edit byte identity;
- stale source hash/size;
- stale record locator;
- stale slot digest;
- stale expected old value;
- duplicate coordinates in one edit set;
- overlapping native slot attempt;
- bool rejection;
- NaN/Inf rejection;
- non-exact large-int rejection;
- unsupported target record kind;
- FORMULA-present workbook rejection;
- caller output stays empty on failure.

Production writer must patch an internal candidate only after complete preflight.

## Task 5 — Verifier RED -> GREEN

Add:

- `packages/markitdown/src/markitdown/twoways/formats/xls/verification.py`
- `packages/markitdown/tests/twoways/test_xls_number_verification.py`

Verifier must prove:

- CFB topology unchanged;
- every stream size/identity required by H17 unchanged;
- Workbook stream length and chain unchanged;
- BIFF record count/order/type/size unchanged;
- BoundSheet8 identity unchanged;
- sheet topology unchanged;
- cell coordinate/native-kind topology unchanged;
- NUMBER row/column/XF unchanged;
- requested numeric semantics equal requested values;
- unrequested NUMBER raw bytes unchanged;
- non-NUMBER raw records unchanged;
- exact physical bytes outside authorized value ranges unchanged.

Only after candidate verification may writer emit bytes.

## Task 6 — Independent differential + one-way regression

Add:

- `packages/markitdown/tests/twoways/test_xls_number_differential.py`
- `packages/markitdown/tests/twoways/test_xls_number_oneway_regression.py`

Use `xlrd` as a read-only independent oracle in tests.

Differential checks:

- sheet names/order;
- requested values;
- sampled unrequested values;
- zero-edit semantic equivalence.

Regression checks:

- one-way `XlsConverter` source blob remains the H17 baseline blob;
- converter registration/acceptance behavior unchanged;
- ordinary one-way markdown conversion still works;
- H17 code does not monkey-patch pandas/xlrd or the existing converter.

## Task 7 — Hardening court

Add:
`packages/markitdown/tests/twoways/test_xls_number_hardening.py`.

Cover at minimum:

- invalid CFB signature/version/sector shifts;
- malformed DIFAT/FAT/MiniFAT chains;
- directory cycles and overlapping stream ownership;
- mini-stream edge cases;
- Workbook slot crossing sector boundaries;
- malformed BIFF headers and truncated records;
- unexpected BOF/EOF sequencing;
- invalid/duplicate BoundSheet8 pointers;
- duplicate sheet identities;
- duplicate cell owners;
- FILEPASS anywhere in global authority;
- FORMULA anywhere in workbook;
- non-finite source NUMBER;
- writer-time resource-limit downgrade/forgery attempts;
- tampered IR metadata and native locators;
- candidate verifier rejection before destination emission.

The hardening court must assert stable reason codes where public diagnostics promise one.

## Task 8 — Documentation and public surface closure

Update:

- `packages/markitdown/src/markitdown/twoways/formats/xls/__init__.py`
- any required narrow public exports;
- `TWOWAYS.md`.

Documentation must say exactly:

- H17 is BIFF8 only;
- only existing NUMBER record value slots are writable;
- formulas make the workbook read-only in H17;
- RK/MulRk/LabelSst and structural edits remain unsupported;
- identity Markdown is inspection-only;
- xlrd is test oracle / one-way dependency, not mutation authority;
- existing one-way XlsConverter is unchanged.

Run scope audit to ensure no unrelated production paths changed.

## Task 9 — Final exact-head court

Freeze one final head SHA.

Required checks on that exact SHA:

1. pre-commit;
2. package tests Python 3.10;
3. package tests Python 3.11;
4. package tests Python 3.12;
5. package tests Python 3.13;
6. OCR tests Python 3.10;
7. OCR tests Python 3.11;
8. OCR tests Python 3.12;
9. OCR tests Python 3.13.

All nine must be SUCCESS.

Record:

- exact head SHA;
- exact head tree SHA;
- main SHA;
- merge-base;
- ahead/behind relation;
- exact changed-file set;
- workflow run IDs and job results.

## Task 10 — Synthetic merge and guarded merge

Require unchanged main and unchanged final head.

Read GitHub's `refs/pull/<PR>/merge` synthetic merge commit and verify:

- parent 1 == recorded main SHA;
- parent 2 == exact final H17 head;
- synthetic merge tree == exact H17 head tree.

Then:

- update PR body with frozen completion evidence;
- add a provenance comment;
- mark Ready;
- re-read PR/main/head/CI/merge-ref after the metadata transition;
- merge with `expected_head_sha=<exact H17 head>`;
- verify resulting `main` points to the merge commit;
- verify merge commit parents;
- verify merge tree == frozen H17 tree.

Any movement invalidates the proof and returns H17 to verification.
