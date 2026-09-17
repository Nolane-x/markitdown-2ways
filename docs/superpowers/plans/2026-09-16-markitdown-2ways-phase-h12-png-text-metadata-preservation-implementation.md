# Phase H12 PNG Existing tEXt Metadata Preservation — Implementation Plan

> **For Codex/Claude/ChatGPT implementers:** execute this plan test-first. Do not weaken a failing safety assertion merely to make CI green. Preserve the one-way image converter and all H1–H11 contracts.

**Goal:** Add a pure-Python PNG 2Ways adapter that can update only an existing, uniquely-owned `tEXt` value while proving exact preservation of every unrequested PNG chunk.

**Architecture:** A strict bounded PNG parser produces immutable chunk evidence. `read_png_ir` projects existing `tEXt` owners into `DocumentIR` and advertises one typed capability only for safe owners. `patch_png` fresh-parses source authority, preflights all edits, rebuilds only requested `tEXt` chunks in memory, strict-rereads the candidate, verifies complete ordered topology plus raw preservation, then emits bytes transactionally.

**Tech stack:** Python stdlib (`dataclasses`, `hashlib`, `struct`, `zlib`), existing 2Ways IR/capability/error/result contracts, pytest. Pillow is optional test oracle only.

**Frozen base:** `main@22edae2222c3190a8025e10428a5f775f34ab1d8`

**Branch:** `phase-h12-png-text-metadata-preservation`

---

## Task 1: Freeze design and RED public contract

**Files:**
- Add: `packages/markitdown/tests/twoways/_png_fixtures.py`
- Add: `packages/markitdown/tests/twoways/test_png_public_imports.py`
- Add: `packages/markitdown/tests/twoways/test_png_reader.py`
- Add: `packages/markitdown/tests/twoways/test_png_writer.py`

**Step 1 — RED:** create stdlib-generated minimal PNG fixtures and tests importing `read_png_ir`, `patch_png`, `PngIRReader`, `PngPatchWriter`, `PngLimits`. Assert deterministic IR, writable unique `tEXt`, exact no-op identity, target-only edit, stale source rejection, duplicate-keyword read-only behavior and empty output on failed transaction.

**Step 2 — Verify RED:** open a draft PR from the H12 branch so GitHub Actions runs against the exact RED head. The expected failure is missing `markitdown.twoways.formats.png` / missing H12 symbols, not an unrelated baseline failure.

## Task 2: Strict PNG parser and limits

**Files:**
- Add: `packages/markitdown/src/markitdown/twoways/formats/png/limits.py`
- Add: `packages/markitdown/src/markitdown/twoways/formats/png/model.py`
- Add: `packages/markitdown/src/markitdown/twoways/formats/png/parser.py`
- Add: `packages/markitdown/tests/twoways/test_png_parser.py`

**RED tests:** signature, truncation, declared-length overflow, invalid CRC, invalid chunk-type bytes, reserved-bit violation, multiple/missing/misplaced IHDR/IEND, missing IDAT, non-consecutive IDAT, PLTE after IDAT, unknown critical chunk, source/chunk/count resource limits.

**GREEN implementation:** parse every chunk with checked boundaries; record exact offsets, stored/computed CRC, raw/data digests, ordered type inventory and policy blockers. Parser must not decode/recompress image pixels.

## Task 3: H12 `tEXt` ownership and DocumentIR mapping

**Files:**
- Add: `packages/markitdown/src/markitdown/twoways/formats/png/reader.py`
- Extend: `test_png_reader.py`

**RED tests:** keyword/value decoding, deterministic IDs/locators, unique keyword writable capability, duplicate keyword read-only, APNG readable-but-read-only, invalid keyword fail-closed, source SHA/size and chunk evidence bound into metadata.

**GREEN implementation:** one image canvas; one text node per valid existing `tEXt`; native locator binds chunk index + keyword; capability `update_png_text_metadata` only for unique H12-safe owners.

## Task 4: Transactional writer and fresh-source routing

**Files:**
- Add: `packages/markitdown/src/markitdown/twoways/formats/png/writer.py`
- Extend: `test_png_writer.py`

**RED tests:** valid edit, multiple distinct edits, duplicate edit owner, malformed payload, wrong edit type, missing target, forged locator, forged raw digest, stale semantic/native/old-value preconditions, unencodable replacement, replacement-size limit, APNG/duplicate read-only rejection, semantic no-op identity.

**GREEN implementation:** validate source digest/size; fresh-parse; resolve exact owner; validate capability and common edit preconditions; require payload `{keyword, old_value, value}`; encode value ISO-8859-1; replace only complete target chunk byte ranges; recompute target length/CRC; never write before candidate verification.

## Task 5: Candidate preservation verifier

**Files:**
- Add: `packages/markitdown/src/markitdown/twoways/formats/png/verification.py`
- Add: `packages/markitdown/tests/twoways/test_png_verification.py`

**RED tests:** deliberate candidate drift in unrequested ancillary chunk, IDAT byte drift, chunk reorder/count/type drift, target keyword drift, unrequested `tEXt` drift and requested semantic mismatch.

**GREEN implementation:** strict reparse candidate; compare ordered inventory; requested owners may differ only in text value/length/CRC; every unrequested raw chunk must match exactly; all image-bearing critical chunks must match exact raw bytes.

## Task 6: Adapter/public API integration

**Files:**
- Add: `packages/markitdown/src/markitdown/twoways/formats/png/__init__.py`
- Extend: `test_png_public_imports.py`
- Add: `packages/markitdown/tests/twoways/test_png_adapters.py`

Implement `PngIRReader.accepts/read` for `.png` / `image/png` and `PngPatchWriter.accepts/write` using existing reader/writer base contracts. No global one-way converter changes.

## Task 7: One-way regression and optional differential oracle

**Files:**
- Add: `packages/markitdown/tests/twoways/test_png_oneway_regression.py`
- Add: `packages/markitdown/tests/twoways/test_png_differential.py`

Protect blob/behavior of `_image_converter.py`. If Pillow is installed, verify source/candidate decode to identical pixel data and requested textual metadata is visible where Pillow exposes it. Skip cleanly when unavailable; H12 correctness must not depend on Pillow.

## Task 8: Documentation and capability matrix

**Files:**
- Modify: `TWOWAYS.md`

Document H12 API, safety boundary, unsupported metadata forms and exact chunk-preservation contract. Extend the current capability matrix with PNG H12 and identify H12 as the first v0.8 tranche. Do not claim general image editing.

## Task 9: Hardening sweep

Add adversarial tests for:

- integer/boundary arithmetic around chunk lengths;
- zero-length/maximum allowed text;
- duplicate keywords separated by arbitrary ancillary chunks;
- Latin-1 edge bytes;
- embedded NUL in replacement rejection;
- malformed keyword spaces/control bytes;
- CRC collision is not treated as authority (raw digest/locator still required);
- output stream remains empty for every failure path;
- exact unrequested-chunk preservation with target value both shorter and longer.

Run focused tests until GREEN without weakening design constraints.

## Task 10: Full verification and exact-head closure

1. Run the complete repository suite through GitHub Actions on the draft PR.
2. Require exact-head pre-commit SUCCESS.
3. Require package Python 3.10, 3.11, 3.12, 3.13 SUCCESS.
4. Require OCR Python 3.10, 3.11, 3.12, 3.13 SUCCESS.
5. Audit changed-file scope; `_image_converter.py`, workflow files, formatter config and unrelated adapters must be unchanged.
6. Audit PR reviews/threads/comments for unresolved blockers.
7. Freeze exact final head and record the 9/9 gate in the PR body/comment.
8. Merge only that exact verified head to `main`.
9. Compare final H12 tree to merged `main` tree to ensure merge provenance introduced no content drift.

## Expected H12 file boundary

Allowed production changes are restricted to:

- `packages/markitdown/src/markitdown/twoways/formats/png/**`
- PNG H12 tests under `packages/markitdown/tests/twoways/**`
- this H12 design/plan
- `TWOWAYS.md`

Any need to change shared IR, global workflows, dependency declarations, one-way image conversion or unrelated adapters is a design-review event rather than an automatic scope expansion.
