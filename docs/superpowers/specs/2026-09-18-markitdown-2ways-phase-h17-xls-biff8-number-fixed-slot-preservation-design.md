# Phase H17 — XLS BIFF8 NUMBER fixed-slot preservation

## Goal

H17 closes the remaining bounded legacy-XLS gap in the v0.8 program without introducing
an XLS serializer. The tranche adds a native two-way path for one deliberately narrow
cell class in classic BIFF8 `.xls` workbooks:

- an existing worksheet cell represented by a BIFF8 `Number` record;
- replacement of only the record's existing 8-byte IEEE-754 `Xnum` payload;
- no record-size change, no record insertion/deletion, no CFB allocation change;
- exact physical-byte preservation everywhere outside explicitly authorized number slots.

The public typed operation is the existing spreadsheet operation `update_sheet_cells`.
H17 does not create a second XLS-specific edit vocabulary.

The existing one-way `XlsConverter` remains unchanged.

## Normative format authority

H17 follows the Microsoft `[MS-XLS]` binary file format contract and the compound-file
container contract it references.

The implementation treats the following facts as normative:

- a classic XLS file is a CFB container with a workbook stream;
- H17 accepts only a unique top-level stream named exactly `Workbook`;
- the workbook stream is a sequence of BIFF records, each with a 2-byte record type,
  a 2-byte payload size, and the record payload;
- BIFF record payload size is bounded by the format contract;
- a `BoundSheet8` record binds a sheet name/type to the byte position of that sheet BOF;
- a `Number` record owns one worksheet cell and contains a 6-byte cell structure followed
  by one 8-byte floating-point `Xnum`;
- `RK`, `MulRk`, `Formula`, `LabelSst`, `BoolErr`, `Blank`, and other cell records
  are distinct native representations and are not silently normalized to `Number`.

H17 is intentionally BIFF8-only. Older `Book` stream layouts and pre-BIFF8 files remain
read-only.

## In scope

H17 adds:

1. bounded CFB discovery sufficient to locate one exact top-level `Workbook` stream;
2. strict BIFF8 record scanning with complete record-boundary evidence;
3. workbook-global `BoundSheet8` discovery and sheet identity;
4. worksheet-substream discovery from exact BOF offsets;
5. direct `Number` record ownership for existing numeric cells;
6. typed `DocumentIR` worksheet/table/cell projection for H17-supported numeric owners;
7. `update_sheet_cells` for an existing H17-writable `Number` cell;
8. transactional patching of only the existing eight value bytes;
9. exact physical preservation proof outside authorized slots;
10. strict candidate re-read and independent `xlrd` semantic validation in tests.

## Explicitly out of scope

H17 does not write:

- `RK` or `MulRk` records;
- `Formula` records or cached formula results;
- `LabelSst`, SST/CONTINUE strings, inline labels, booleans, errors or blanks;
- new cells, deleted cells, row/column insertion, row/column deletion or sheet structure;
- sheet names, visibility, ordering, BOF offsets or workbook globals;
- styles/XF records, number formats, merged cells, comments, notes, drawings or charts;
- names, external links, connections, pivots or macros;
- CFB directory/FAT/MiniFAT topology, stream length, sector chains or allocation;
- encrypted workbooks;
- BIFF5/BIFF4/BIFF3/BIFF2 `Book` streams;
- identity-Markdown writeback;
- whole-workbook regeneration through pandas, xlrd, xlwt, LibreOffice or any serializer.

If safe ownership cannot be proven from native bytes, the target is read-only.

## Conservative workbook eligibility

A source may expose H17 write capability only when all of the following are true:

- the outer container is a valid bounded CFB file;
- there is exactly one top-level stream named `Workbook`;
- there is no competing top-level `Book` stream;
- the workbook stream can be reconstructed byte-exactly from its recorded CFB chain;
- the first workbook substream is a valid BIFF8 globals substream;
- all BIFF records are structurally bounded and non-overlapping;
- sheet BOF pointers from `BoundSheet8` are unique, in bounds, and resolve exactly;
- every writable sheet is an ordinary worksheet, not a macro/chart/dialog sheet;
- no `FilePass` encryption record is present;
- no malformed/truncated record or substream is present;
- every advertised target coordinate has exactly one `Number` owner;
- all source/resource limits hold at read time and are rechecked by the writer.

For H17, any workbook containing a BIFF `Formula` record is readable but globally
read-only for `update_sheet_cells`. This intentionally avoids emitting a workbook in
which edited input values coexist with stale cached formula results or unresolved
recalculation semantics.

## CFB preservation contract

H17 must retain evidence sufficient to prove both logical Workbook-stream ownership and
physical source-byte ownership.

The CFB reader records at minimum:

- source SHA-256 and size;
- CFB major version, sector size and mini-sector size;
- FAT/DIFAT/MiniFAT topology digests;
- complete directory-entry identity needed to resolve the Workbook stream;
- Workbook stream size and chain identity;
- mapping from logical Workbook-stream byte ranges to physical source-file ranges;
- digests for the complete Workbook stream and every non-Workbook stream/storage identity
  relevant to topology verification.

The writer never reallocates sectors. A requested 8-byte BIFF number slot is translated
through the recorded stream mapping to one or more physical ranges. A slot may cross a
CFB sector boundary; that case is supported only when the logical-to-physical mapping is
complete and unambiguous.

## BIFF8 record contract

The scanner walks the logical Workbook stream from byte zero and records every BIFF
record as immutable topology evidence:

- record index;
- record type;
- 4-byte record-header offset;
- payload offset;
- payload size;
- end offset;
- raw record digest.

A record is rejected if its declared payload extends beyond the stream or violates the
configured per-record bound.

H17 parses only the minimum structures required for authority. All unrelated records are
preserved as opaque bytes but remain part of the topology fingerprint.

### Globals substream

The first BOF must identify the workbook globals substream. H17 records:

- globals BOF identity;
- globals EOF boundary;
- ordered `BoundSheet8` records;
- sheet BOF offsets;
- sheet names and sheet types;
- presence of `FilePass`;
- presence of records that force a fail-closed decision.

Duplicate sheet names under BIFF case-insensitive rules, duplicate BOF pointers, invalid
sheet-name encodings or pointers that do not resolve to the expected BOF are rejected.

### Worksheet substreams

For every ordinary worksheet selected into H17 IR, the parser records:

- sheet name;
- exact BOF offset and EOF offset;
- ordered record identity;
- every existing `Number` owner;
- any competing owner for the same cell coordinate;
- presence of formula records.

A worksheet coordinate is writable only when its native owner is exactly one `Number`
record.

## NUMBER ownership

A BIFF8 `Number` record contains:

- row: 2 bytes;
- column: 2 bytes;
- XF index: 2 bytes;
- numeric value: 8-byte `Xnum`.

H17 treats only the final eight bytes as writable.

For each owner the reader stores:

- sheet identity;
- zero-based row and column;
- XF index;
- record offset/type/size;
- logical Workbook-stream value offset;
- physical source ranges for the eight value bytes;
- original raw 8-byte value;
- decoded finite floating-point value;
- record digest;
- slot digest;
- surrounding topology fingerprint.

The row, column and XF fields are immutable.

Non-finite source values do not receive write capability.

## IR mapping

Each eligible worksheet maps to one `Canvas(kind="worksheet")`.

H17 may materialize a bounded table/cell projection, but native BIFF authority is carried
in metadata. At minimum each H17 numeric cell exposes:

- sheet name;
- row and column;
- native record kind `NUMBER`;
- XF index;
- decoded numeric value;
- native record/slot locators;
- source/stream/slot digests;
- capability declaration for `update_sheet_cells`.

Visible text is a projection only. Writers resolve the target from native locators and
freshly parsed source bytes, never from display text alone.

Identity Markdown remains inspection-only for XLS in H17.

## Capability model

A NUMBER-backed cell is writable only for `update_sheet_cells` when all source and
workbook eligibility rules pass.

Representative read-only reasons include:

- `xls.container.invalid_cfb`
- `xls.container.workbook_stream_missing`
- `xls.container.workbook_stream_ambiguous`
- `xls.container.competing_book_stream`
- `xls.workbook.unsupported_biff_version`
- `xls.workbook.encrypted`
- `xls.workbook.formulas_present`
- `xls.sheet.unsupported_type`
- `xls.sheet.invalid_bof_pointer`
- `xls.cell.unsupported_record_type`
- `xls.cell.duplicate_owner`
- `xls.cell.non_finite`
- `xls.source.limit_exceeded`
- `xls.capability.read_only`

Unknown conditions default to read-only.

## Mutation contract

The H17 writer performs complete preflight before caller output receives bytes.

For every edit it must:

1. verify source SHA-256 and byte size against the IR;
2. parse the CFB container again from the supplied source;
3. resolve the unique Workbook stream again;
4. parse BIFF8 records again from fresh bytes;
5. re-derive sheet identity and the target NUMBER owner;
6. verify row/column/XF/record offsets and stored digests;
7. verify the expected old semantic value when supplied;
8. verify the complete edit set has unique coordinates and non-overlapping slots;
9. validate replacement numeric semantics;
10. render exactly one 8-byte little-endian IEEE-754 value per target;
11. patch only the mapped physical bytes in an internal candidate buffer;
12. verify the complete candidate;
13. emit only after verification succeeds.

Zero edits return source bytes exactly.

## Replacement numeric semantics

Accepted replacement values are Python-style integer or floating numeric scalars except
booleans.

The writer rejects:

- NaN and positive/negative infinity;
- values outside finite binary64 range;
- integers that cannot be represented exactly as binary64;
- non-numeric objects;
- values whose candidate re-read does not equal the requested H17 semantic value under
  the documented numeric normalization.

H17 does not convert the target to RK or another more compact BIFF representation.

## Candidate verification

The verifier re-reads the full candidate and requires:

- identical CFB version, directory topology, FAT/DIFAT/MiniFAT topology and stream sizes;
- identical Workbook-stream length and sector chain;
- identical BIFF record count/order/type/size and BOF/EOF structure;
- identical ordered BoundSheet8 sheet identity and BOF pointers;
- identical sheet count/order/type/name;
- identical cell-owner coordinate topology;
- identical row/column/XF fields for every NUMBER owner;
- requested cells equal the requested numeric values;
- unrequested NUMBER owners retain raw value bytes and semantics;
- all non-NUMBER records retain byte-identical raw records;
- every physical source byte outside authorized value ranges is identical;
- no new overlap, truncation or unsupported structure appears.

Verification failure leaves caller output empty.

## Independent validation

Tests use `xlrd` only as an independent read-only semantic oracle.

For accepted fixtures, `xlrd` must agree on:

- sheet names and order;
- target cell numeric values after mutation;
- unrequested sampled cell values.

Production H17 code must not use `xlrd` to locate mutation offsets and must never use a
library save path.

## One-way regression contract

The existing one-way implementation remains `XlsConverter` in
`packages/markitdown/src/markitdown/converters/_xlsx_converter.py`.

H17 must not modify that converter as part of native mutation work. Regression tests lock
its ordinary `.xls` conversion behavior and ensure adding the two-way adapter does not
change converter registration or one-way output semantics outside expected edited data.

The baseline one-way converter blob at the start of H17 is
`355dd8f8d74ab5c9a40bba37e1f7a7d601eeba27`.

## Resource limits

H17 uses monotonic, tamper-evident limits recorded in IR and re-enforced by the writer.
The effective write-time limit is never weaker than the read-time authority.

Limits cover at minimum:

- source byte size;
- CFB sector count;
- CFB directory entry count;
- Workbook stream byte size;
- BIFF record count;
- sheet count;
- materialized NUMBER-owner count.

A caller cannot forge a larger limit into stale IR and obtain broader write capability.

## Security and fail-closed rules

H17 performs no network or subprocess I/O.

Malformed CFB chains, cycles, out-of-range sectors, overlapping ownership, invalid
directory topology, malformed BIFF framing, encrypted BIFF, ambiguous workbook streams,
invalid sheet pointers, duplicate cell ownership, stale native locators, forged evidence,
non-finite numeric states and resource-limit violations all fail closed.

The parser never executes macros, formulas, external links or embedded objects.

H17 does not claim that an arbitrary legacy XLS workbook is safe content. Its guarantee is
bounded native mutation with exact preservation of everything outside authorized slots.

## TDD and completion gate

Implementation proceeds strict RED -> GREEN in bounded stages:

1. CFB/BIFF framing and workbook authority;
2. reader + capability mapping;
3. writer preflight and fixed-slot patching;
4. candidate verifier;
5. public adapter/import surface;
6. differential and one-way regression;
7. adversarial/resource-limit hardening;
8. documentation and exact-head closure.

H17 is complete only when the exact frozen branch head passes:

- pre-commit;
- package tests on Python 3.10, 3.11, 3.12 and 3.13;
- OCR tests on Python 3.10, 3.11, 3.12 and 3.13;
- focused H17 tests;
- scope audit;
- synthetic merge-tree equality against unchanged `main`;
- guarded merge with the exact expected head SHA.

Any movement of the final head or base invalidates completion proof.

## Deferred XLS roadmap

Possible later XLS tranches may add separately proved support for:

- RK/MulRk numeric owners;
- LabelSst/SST strings with continuation-aware ownership;
- booleans/errors;
- formula-aware editing with explicit recalculation/cached-result policy;
- selected metadata;
- older BIFF generations.

None of those capabilities are implied by H17.
