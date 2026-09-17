# Phase H13 — PNG compressed and international text preservation

Status: approved continuation of the v0.8 media tranche after integrated H12.

Base authority: `main@4f179f99725d9a09331385e29bb8020e5d1969f7` (merged H12).

## Goal

Extend the H12 source-preserving PNG adapter from existing `tEXt` metadata to existing `zTXt` and `iTXt` text owners without widening the product into a generic PNG editor.

H13 keeps the same governing rule as H12: mutate only one already-owned native text value, preserve every unrelated PNG chunk byte-for-byte, and emit output only after strict native re-read and preservation verification.

Normative structural authority is PNG Second Edition / ISO/IEC 15948 textual information (`tEXt`, `zTXt`, `iTXt`). H13 implements only the subset required to prove safe bounded value replacement.

## In scope

- strict parsing of existing `zTXt` owners;
- strict parsing of existing `iTXt` owners, compressed and uncompressed;
- IR projection for `tEXt`, `zTXt`, and `iTXt` native text owners;
- one existing typed operation, `update_png_text_metadata`, for writable owners across all three chunk types;
- unique-keyword writable ownership across all parsed PNG text chunks, not merely within one chunk type;
- source-authority, native-locator, raw-owner-digest and old-value revalidation at write time;
- exact preservation of chunk type and immutable per-owner metadata;
- bounded zlib decompression and recompression for `zTXt` and compressed `iTXt`;
- exact preservation of every unrequested raw chunk;
- optional independent Pillow decode/metadata checks in tests only.

## Explicitly out of scope

H13 does not add, delete, reorder or convert text chunks. In particular it does not:

- convert `tEXt` to `zTXt` or `iTXt`;
- convert `zTXt` to `tEXt`;
- change the compression flag or method of `iTXt`;
- change a `zTXt` compression method;
- change keyword, language tag or translated keyword;
- create a missing text owner;
- mutate XMP semantics merely because XMP happens to be stored in an `iTXt` chunk; the standard `XML:com.adobe.xmp` owner is inspection-only and explicitly read-only;
- mutate EXIF, ICC, pixels, palette, transparency, APNG control/data chunks or arbitrary ancillary chunks;
- add identity-Markdown writeback;
- modify the one-way image converter.

APNG remains readable but H13 text owners are read-only under the existing policy.

## PNG text semantics

### `tEXt`

H12 behavior is preserved unchanged:

- keyword: 1–79-byte PNG keyword;
- value: Latin-1;
- keyword immutable;
- replacement value must contain no NUL.

### `zTXt`

A writable H13 `zTXt` owner must have:

- valid PNG keyword;
- compression method exactly `0`;
- one complete zlib datastream with no trailing compressed stream bytes;
- decompressed value bounded by the active read-time text limit;
- decompressed value interpreted as Latin-1 and containing no NUL.

A successful edit preserves the keyword and method byte, recompresses only the replacement value into one zlib stream, and rebuilds only the target `zTXt` chunk length/CRC.

### `iTXt`

A writable H13 `iTXt` owner must have:

- valid PNG keyword other than the standard XMP keyword `XML:com.adobe.xmp`;
- compression flag `0` or `1`;
- compression method `0`;
- language tag either empty or a hyphen-separated sequence of 1–8 ASCII alphanumeric characters per component;
- translated keyword valid UTF-8 and containing no NUL;
- text valid UTF-8 and containing no NUL;
- if compressed, one complete zlib datastream with bounded decompressed bytes and no trailing compressed stream bytes.

The keyword, compression flag, compression method, language tag raw bytes and translated-keyword raw bytes are immutable native evidence. Only the text field may change. Uncompressed `iTXt` remains uncompressed; compressed `iTXt` remains compressed. XMP `iTXt` remains projected for inspection but never advertises writable capability.

## Ownership and ambiguity

PNG permits multiple text chunks with the same keyword. 2Ways therefore cannot infer a unique semantic owner merely from the keyword.

H13 projects every valid text owner for inspection but advertises `update_png_text_metadata` as writable only when that keyword occurs exactly once across the complete parsed set of `tEXt` + `zTXt` + `iTXt` owners and the owner is not the standard XMP `iTXt` carrier.

This cross-type uniqueness and XMP exclusion policy is re-evaluated from a fresh authoritative source at write time. Cached or forged capability metadata cannot bypass it.

## IR mapping

All three native chunk types use semantic role `png-text-metadata` and `TextPayload` for the decoded value.

Per-node metadata includes at least:

- `png.keyword`;
- `png.chunk_index`;
- `png.chunk_type` (`tEXt`, `zTXt`, or `iTXt`);
- chunk/data offsets and SHA-256 evidence;
- `png.compression_method` where applicable;
- `png.compression_flag` for `iTXt`;
- `png.language_tag` and its raw digest/evidence for `iTXt`;
- `png.translated_keyword` and its raw digest/evidence for `iTXt`;
- `png.is_apng`;
- common capability metadata.

The native locator object id remains bound to chunk index + keyword and adds the authoritative chunk type in locator attributes.

## Bounded decompression contract

Production code must never call an unbounded convenience decompressor for text owners.

For each compressed owner the parser uses a zlib decompression object with output capped at `max_text_value_bytes + 1` and requires:

- decoded output length not greater than the active text limit;
- zlib EOF reached;
- no unconsumed compressed input;
- no unused/trailing compressed bytes;
- no zlib error.

Failure is a structural H13 parse error. This prevents a small compressed chunk from expanding without bound in memory.

The existing `PngLimits.max_text_value_bytes` remains the decoded/writable value-byte authority for H13. H13 does not weaken the H12 read-time limits contract; writer-supplied limits may only tighten the limits persisted in the IR.

## Mutation contract

Before any output bytes are emitted, the writer must:

1. validate the supplied `DocumentIR`;
2. verify PNG source SHA-256 and byte size;
3. intersect requested limits with persisted read-time limits;
4. fresh-parse the complete source PNG under those effective limits;
5. reject APNG mutation from fresh source evidence;
6. recompute cross-type text keyword counts and the XMP read-only policy from the fresh source;
7. resolve each target by exact native chunk index, type and immutable keyword;
8. verify raw-owner digest and immutable owner metadata;
9. verify capability plus semantic/native/old-value preconditions;
10. validate the entire edit set before mutation;
11. encode the replacement according to the target chunk type;
12. preserve target chunk type and immutable owner fields;
13. rebuild only requested chunk byte ranges with new length/CRC;
14. strict re-read the complete candidate under the same effective limits;
15. verify requested semantic readback and immutable metadata;
16. prove every unrequested chunk raw byte sequence is identical;
17. write candidate bytes only after every verification passes.

Zero edits and semantic no-ops return the exact source bytes.

## Target encoding

- `tEXt`: Latin-1 bytes, no NUL.
- `zTXt`: Latin-1 bytes, no NUL, compressed as one method-0 zlib stream.
- `iTXt`: UTF-8 bytes, no U+0000; compressed only when the original compression flag is `1`.

H13 makes no promise that a modified compressed target chunk retains the same compressed bytes or compressed length. The preservation claim is semantic for the requested owner and byte-exact for all unrequested chunks.

## Candidate verification

Source and candidate must have identical:

- chunk count;
- ordered chunk-type sequence;
- all unrequested raw chunks;
- image-bearing critical chunks;
- requested owner keyword and chunk type;
- requested `zTXt` compression method;
- requested `iTXt` compression flag/method, language tag and translated keyword.

Requested decoded values must equal the edit values after a fresh strict parse.

## Stable failure reasons

Representative reason codes:

- `png.text.writable`
- `png.text.duplicate_keyword`
- `png.text.unsupported_chunk_type`
- `png.ztxt.unsupported_compression_method`
- `png.ztxt.invalid_zlib_stream`
- `png.itxt.invalid_compression_flag`
- `png.itxt.unsupported_compression_method`
- `png.itxt.invalid_language_tag`
- `png.itxt.invalid_utf8`
- `png.itxt.xmp_read_only`
- `png.text.decompression_limit`
- `png.apng.read_only`
- `png.resource_limit`

Unknown or absent capability remains read-only through the common capability kernel.

## Security and failure behavior

Malformed separators, invalid UTF-8, invalid language tags, unsupported compression methods, incomplete/trailing zlib streams, decompression-limit violations, duplicate semantic ownership, XMP `iTXt` owners, APNG policy blockers, stale owner evidence and resource-limit violations all fail closed before caller output receives bytes.

## Independent validation

Production H13 remains stdlib-only for this tranche (`struct`, `hashlib`, `zlib`, codecs). Pillow may be used only by tests as an independent PNG decoder/metadata oracle. Synthetic fixtures must be constructible without Pillow.

## Completion gate

H13 is complete only after:

- design and implementation plan are committed on the H13 branch;
- test-first RED evidence exists for `zTXt`, compressed/uncompressed `iTXt`, cross-type duplicate ownership, XMP exclusion and decompression hardening;
- focused H13 tests are GREEN;
- H12 `tEXt` behavior remains GREEN unchanged;
- malformed compression, trailing zlib bytes, invalid UTF-8/language-tag and decompression-bomb tests are GREEN;
- zero-edit byte identity and unrequested raw-chunk preservation are proven;
- optional independent decoder checks pass where available;
- existing one-way image behavior is unchanged;
- full repository regression is GREEN;
- pre-commit plus package/OCR Python 3.10–3.13 are GREEN on the exact final tree;
- only then may H13 merge into `main`.
