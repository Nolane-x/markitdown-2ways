# Phase H14 implementation plan — JPEG Exif in-place text preservation

Base: `main@da5446843f5df36b61b6530d06eaa56ace5dad00`

Design authority: `docs/superpowers/specs/2026-09-17-markitdown-2ways-phase-h14-jpeg-exif-inplace-text-preservation-design.md`.

Execution rule: strict RED → GREEN. Do not add production behavior before a focused failing test demonstrates the missing contract. Keep all H14 writes transactional and fail-closed.

## Task 1 — RED fixtures and parser contract

Create:

- `packages/markitdown/tests/twoways/_jpeg_fixtures.py`
- `packages/markitdown/tests/twoways/test_jpeg_exif_parser.py`

Fixtures must build deterministic JPEG byte streams without Pillow, including:

- little-endian Exif APP1 with external `ImageDescription`/`Artist` values;
- big-endian Exif APP1;
- inline short ASCII owner;
- multiple APP1 Exif segments;
- XMP APP1;
- Photoshop/IPTC APP13;
- duplicate IFD0 target tags;
- overlapping external value allocations;
- malformed marker length/TIFF offset/IFD count/value range;
- multi-scan/stuffed/restart scan bytes sufficient to prove complete marker traversal.

RED expectations: imports or parser calls do not yet exist.

## Task 2 — minimal bounded JPEG/Exif parser

Create:

- `packages/markitdown/src/markitdown/twoways/formats/jpeg/limits.py`
- `packages/markitdown/src/markitdown/twoways/formats/jpeg/model.py`
- `packages/markitdown/src/markitdown/twoways/formats/jpeg/parser.py`

Implement:

- SOI→EOI marker traversal across all scans;
- length-bearing/standalone marker handling;
- byte stuffing and restart marker handling inside entropy-coded scans;
- APP1 Exif/XMP and APP13 authority detection;
- TIFF endian/magic/IFD parsing;
- bounded reachable IFD traversal and value-range accounting;
- supported IFD0 text owner extraction for `0x010E` and `0x013B`;
- strict ASCII owner semantics and zero-padding validation;
- overlap/duplicate/resource-limit evidence.

Run focused parser tests to GREEN before proceeding.

## Task 3 — RED reader/capability tests

Create:

- `packages/markitdown/tests/twoways/test_jpeg_exif_reader.py`
- `packages/markitdown/tests/twoways/test_jpeg_exif_adapters.py`
- `packages/markitdown/tests/twoways/test_jpeg_exif_public_imports.py`

Lock:

- deterministic `DocumentIR` nodes;
- native locators and source authority;
- writable capability only for unique safe `ImageDescription`/`Artist` owners;
- read-only states for XMP/IPTC/multiple-Exif/duplicates/ambiguous allocation/encoding;
- `.jpg`/`.jpeg`/JPEG MIME adapter acceptance;
- no root namespace pollution.

## Task 4 — GREEN reader/public surface

Create:

- `packages/markitdown/src/markitdown/twoways/formats/jpeg/reader.py`
- `packages/markitdown/src/markitdown/twoways/formats/jpeg/__init__.py`

Persist exact read-time limits in document metadata. Expose `JpegIRReader`, `JpegLimits`, and `read_jpeg_ir` only from the format-specific package.

## Task 5 — RED writer/preflight tests

Create:

- `packages/markitdown/tests/twoways/test_jpeg_exif_writer.py`
- `packages/markitdown/tests/twoways/test_jpeg_exif_hardening.py`

Lock:

- zero-edit exact identity;
- semantic no-op exact identity;
- shorter/same-allocation replacement;
- growth rejection with empty caller output;
- non-ASCII/NUL rejection;
- source SHA/size mismatch;
- stale slot/entry/tag/type/count/offset/digest rejection;
- forged writable capability cannot bypass fresh XMP/IPTC/multiple-Exif/duplicate/overlap policy;
- duplicate transaction target rejection;
- read-time limits cannot be loosened;
- complete edit-set preflight before output.

## Task 6 — GREEN writer and candidate verifier

Create:

- `packages/markitdown/src/markitdown/twoways/formats/jpeg/verification.py`
- `packages/markitdown/src/markitdown/twoways/formats/jpeg/writer.py`

Implement `patch_jpeg` and `JpegPatchWriter` with:

- fresh source parse;
- exact native binding revalidation;
- in-place slot patching only;
- same-length candidate requirement;
- strict re-read;
- marker/TIFF topology verification;
- byte-exact proof outside authorized slot spans;
- destination emission only after verification.

## Task 7 — independent differential and one-way regression

Create:

- `packages/markitdown/tests/twoways/test_jpeg_exif_differential.py`
- `packages/markitdown/tests/twoways/test_jpeg_oneway_regression.py`

When Pillow is available, verify target Exif readback plus unchanged decoded pixel bytes. Do not use Pillow in production serialization.

Prove the existing one-way `ImageConverter` source blob/behavior remains unchanged.

## Task 8 — documentation

Update `TWOWAYS.md`:

- production scope;
- H14 JPEG section;
- capability matrix;
- fidelity details;
- fail-closed blockers;
- v0.8 execution document list;
- roadmap statement.

Explicitly state that H14 is fixed-allocation Exif IFD0 text editing, not generic JPEG/Exif authoring.

## Task 9 — scope audit and exact final gate

Audit PR changed files. No workflow diagnostic, dependency, one-way converter, unrelated adapter, or shared-kernel drift may remain unless independently justified by the H14 contract.

Final authority requires, on one exact final tree:

- pre-commit SUCCESS;
- package Python 3.10 SUCCESS;
- package Python 3.11 SUCCESS;
- package Python 3.12 SUCCESS;
- package Python 3.13 SUCCESS;
- OCR Python 3.10 SUCCESS;
- OCR Python 3.11 SUCCESS;
- OCR Python 3.12 SUCCESS;
- OCR Python 3.13 SUCCESS;
- synthetic PR merge tree SHA exactly equals final branch tree SHA.

Record final SHA/tree/run provenance in the draft PR, mark ready, and merge only with `expected_head_sha` after all gates are proven.