# Phase H13 — PNG compressed and international text preservation implementation plan

Base: `main@4f179f99725d9a09331385e29bb8020e5d1969f7`

Branch: `phase-h13-png-compressed-international-text-preservation`

## Execution rules

- TDD only: every behavioral expansion begins with a failing test.
- Preserve H12 public operation name `update_png_text_metadata`.
- Do not modify the one-way image converter.
- Do not emit caller output until candidate verification succeeds.
- Treat exact final-tree CI as merge authority.

## Task 1 — Freeze H13 contracts and create RED fixture vocabulary

Files:
- `docs/superpowers/specs/2026-09-17-markitdown-2ways-phase-h13-png-compressed-international-text-preservation-design.md`
- `docs/superpowers/plans/2026-09-17-markitdown-2ways-phase-h13-png-compressed-international-text-preservation-implementation.md`
- `packages/markitdown/tests/twoways/_png_fixtures.py`
- new H13 PNG tests

Add fixture helpers capable of creating valid `zTXt` and compressed/uncompressed `iTXt` chunks without optional dependencies.

RED expectations:
- parser discovers `zTXt` decoded Latin-1 value;
- parser discovers uncompressed and compressed `iTXt` UTF-8 values plus immutable metadata;
- reader projects all three text chunk types;
- cross-type duplicate keyword owners are read-only;
- malformed/incomplete/trailing zlib streams fail;
- decompression expansion beyond the active limit fails;
- invalid `iTXt` UTF-8/language-tag/compression fields fail;
- writer preserves chunk type and immutable metadata.

Commit RED evidence before production changes.

## Task 2 — Generalize native text-owner model and strict parser

Files:
- `packages/markitdown/src/markitdown/twoways/formats/png/model.py`
- `packages/markitdown/src/markitdown/twoways/formats/png/parser.py`
- `packages/markitdown/src/markitdown/twoways/formats/png/limits.py` only if a proven limit-field change is required

Extend `PngTextOwner` to retain:
- chunk type;
- keyword/value;
- raw/data digests;
- compression method;
- `iTXt` compression flag;
- `iTXt` language tag and raw evidence;
- `iTXt` translated keyword and raw evidence.

Implement bounded `_decompress_text_zlib()` using `decompressobj` with a hard decoded-output cap. Require EOF and reject unconsumed/unused/trailing input.

Implement strict `zTXt` and `iTXt` parsing while preserving current H12 `tEXt` behavior.

Focused GREEN: parser/model tests only.

## Task 3 — Extend reader/capability authority across text chunk types

Files:
- `packages/markitdown/src/markitdown/twoways/formats/png/reader.py`
- reader/capability tests

Project every parsed `tEXt`, `zTXt`, and `iTXt` owner as `png-text-metadata`.

Compute keyword counts over the complete text-owner set. Writable only when:
- source is not APNG;
- keyword count is exactly one;
- chunk-specific structural authority was proven by parser.

Record chunk type and immutable owner metadata in node/native locator evidence.

Focused GREEN: reader and capability tests.

## Task 4 — Generalize writer encoding without widening authority

Files:
- `packages/markitdown/src/markitdown/twoways/formats/png/writer.py`
- writer/hardening tests

Fresh-source checks must independently revalidate:
- APNG blocker;
- cross-type duplicate keyword blocker;
- exact chunk type at native locator;
- raw owner digest;
- immutable compression/language/translated-keyword metadata.

Prepare replacement values by native type:
- `tEXt`: Latin-1 raw;
- `zTXt`: Latin-1 + method-0 zlib;
- `iTXt`: UTF-8, with original compression mode retained.

Rebuild only requested chunk spans. Preserve all non-value native fields exactly.

Focused GREEN: mutation/no-op/stale-authority/transaction tests.

## Task 5 — Extend candidate verification

Files:
- `packages/markitdown/src/markitdown/twoways/formats/png/verification.py`
- verification tests

Candidate verification must fresh-parse both source and candidate and prove:
- same chunk count and type order;
- exact raw identity for every unrequested chunk;
- requested semantic readback;
- immutable requested owner metadata;
- exact image-bearing critical chunks.

Focused GREEN: verifier tests including target-length changes and multiple requested owners.

## Task 6 — Adversarial compression and Unicode hardening

Files:
- `packages/markitdown/tests/twoways/test_png_h13_hardening.py` or equivalent bounded H13 test module

Cover:
- tiny compressed payload expanding over text limit;
- invalid zlib stream;
- incomplete zlib stream;
- valid stream with trailing compressed bytes;
- unsupported zTXt compression method;
- invalid iTXt compression flag;
- invalid iTXt method;
- invalid language tag;
- invalid translated-keyword UTF-8;
- invalid text UTF-8;
- NUL replacement rejection;
- forged writable capability cannot bypass fresh cross-type duplicate/APNG policy;
- caller output remains empty on every failed transaction.

Focused GREEN before proceeding.

## Task 7 — Independent decoder and one-way regression

Files:
- `packages/markitdown/tests/twoways/test_png_differential.py`
- `packages/markitdown/tests/twoways/test_png_oneway_regression.py`

Where Pillow supports the fixture, verify decoded pixels are unchanged and edited text is visible through an independent decoder. Keep optional dependency out of production.

Prove the existing one-way image conversion path is unchanged.

## Task 8 — Documentation/support matrix

File:
- `TWOWAYS.md`

Document H13 as the second bounded v0.8 PNG tranche:
- existing `tEXt`/`zTXt`/`iTXt` value mutation;
- preservation and ambiguity rules;
- compressed-text resource limits;
- explicit exclusions.

Do not claim generic PNG metadata editing.

## Task 9 — Full verification and integration

Run/observe:
- pre-commit;
- package Python 3.10, 3.11, 3.12, 3.13;
- OCR Python 3.10, 3.11, 3.12, 3.13;
- exact-tree comparison between final H13 head and synthetic PR merge tree.

Audit PR diff for accidental workflow or one-way converter changes.

Only after exact-tree 9/9 GREEN:
- update PR body with final head/tree/run provenance;
- mark ready;
- merge with expected H13 head SHA;
- verify `main` merge commit tree equals the final H13 tree.
