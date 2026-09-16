# MarkItDown 2Ways Phase H12 — PNG Existing tEXt Metadata Preservation Design

## Status

Approved continuation of the full-parity program from `main@22edae2222c3190a8025e10428a5f775f34ab1d8` after H1–H11 integration closure. H12 is the first bounded v0.8 media-native tranche.

## Goal

Add deterministic PNG reading into `DocumentIR` and a single source-preserving native mutation for the value of an **existing** PNG `tEXt` chunk. H12 must prove target ownership, preserve all unrequested chunk bytes, re-read the complete candidate before output, and fail closed when PNG structure or ownership is ambiguous.

This tranche does not turn MarkItDown 2Ways into an image editor or a general metadata authoring library.

## Writable boundary

H12 exposes one operation:

```text
update_png_text_metadata
```

A writable target is an existing `tEXt` chunk whose:

- PNG chunk framing and CRC are valid;
- keyword is syntactically valid under the PNG Latin-1 keyword rules;
- value decodes as ISO-8859-1;
- exact chunk index and byte range are authoritative;
- keyword occurs exactly once among `tEXt` chunks, avoiding semantic-key ambiguity;
- source has no H12 policy blocker.

The keyword is immutable. H12 only replaces the existing text value. Replacement text must be representable in ISO-8859-1 and must satisfy configured size limits.

## Explicitly out of scope

- creating, deleting, renaming or reordering chunks;
- adding a new metadata keyword;
- `zTXt` or `iTXt` mutation;
- XMP, EXIF, ICC profile or color-profile mutation;
- `IHDR`, `PLTE`, `IDAT`, `IEND`, transparency or palette mutation;
- pixel/image recompression or rendering changes;
- APNG (`acTL`, `fcTL`, `fdAT`) mutation;
- arbitrary ancillary-chunk replacement;
- identity-Markdown writeback;
- LLM image descriptions as native editable content;
- subprocess or network I/O in the 2Ways core.

The existing one-way image converter remains unchanged.

## Reader and authority model

The H12 parser uses only the Python standard library. It validates the PNG signature and walks the complete chunk stream using the native wire framing:

```text
length(4) + type(4) + data(length) + crc(4)
```

For every chunk it records at least:

- zero-based chunk index;
- four-byte type;
- data length;
- chunk start/end offsets;
- data start/end offsets;
- stored CRC and computed CRC;
- raw chunk SHA-256;
- raw data SHA-256.

The parser enforces conservative structural rules needed for safe H12 mutation:

- exact PNG signature;
- one `IHDR`, first, length 13;
- one `IEND`, last, length 0, with no trailing bytes;
- at least one `IDAT`;
- valid four-letter ASCII chunk type and reserved-bit rule;
- CRC correctness for every chunk;
- no unknown critical chunk;
- `PLTE`, when present, precedes `IDAT`;
- `IDAT` chunks are consecutive;
- source/chunk/count limits are respected.

Unknown ancillary chunks are preserved and do not by themselves block H12. APNG control/data chunks are recognized as a policy blocker: the PNG remains readable, but no H12 writable capability is advertised.

## DocumentIR mapping

The document source format is `png`. A single image canvas represents the PNG container. Each existing `tEXt` owner is materialized as a deterministic text node with:

- semantic role `png-text-metadata`;
- payload equal to the decoded text value;
- metadata containing keyword, chunk index, byte spans, source/raw digests and policy evidence;
- a native locator with backend `png`, part URI `/`, object id bound to the chunk index and keyword.

`update_png_text_metadata` is writable only for H12-safe unique-keyword owners. Duplicate `tEXt` keywords are readable but read-only with a stable reason code.

`zTXt` and `iTXt` are not writable in H12 and need not be projected as editable text owners.

## Mutation contract

Before any output bytes are emitted, the writer must:

1. validate the supplied `DocumentIR`;
2. verify source SHA-256 and byte size;
3. fresh-parse the source PNG;
4. resolve every requested target by exact native chunk index and immutable keyword;
5. revalidate complete chunk authority and target raw digest;
6. verify the node capability is writable;
7. validate semantic/native/old-value edit preconditions;
8. validate the complete edit set, rejecting duplicate owners;
9. encode every replacement as ISO-8859-1;
10. construct replacement `tEXt` chunks in memory with recomputed length and CRC;
11. patch requested chunk byte ranges only;
12. strict re-read the complete candidate;
13. verify candidate topology and requested semantics;
14. prove every unrequested chunk raw byte sequence is identical;
15. write candidate bytes to the caller only after all checks pass.

A semantic no-op returns the exact source bytes. Zero edits return the exact source bytes.

## Preservation proof

H12 permits target chunk length to change. Therefore offsets of following chunks may shift, but their **raw chunk bytes** must remain exact. Verification compares source and candidate ordered chunk inventories by logical index/type and requires:

- identical chunk count and type order;
- identical `IHDR`/`PLTE`/`IDAT`/`IEND` raw bytes;
- identical raw bytes for every unrequested ancillary chunk;
- immutable keyword for every requested `tEXt` chunk;
- requested decoded value for requested chunks;
- identical raw bytes and semantics for every unrequested `tEXt` chunk.

This proves source preservation without relying on a whole-image serializer.

## Resource limits

H12 defines explicit deterministic limits, initially:

- maximum source bytes: 64 MiB;
- maximum chunk count: 16,384;
- maximum single chunk data bytes: 16 MiB;
- maximum writable `tEXt` value bytes: 1 MiB.

A caller may use stricter limits, but the writer must not accept a candidate that exceeds the authority under which the IR was read.

## Capability and reason codes

Representative stable reason codes:

- `png.text.writable`
- `png.text.duplicate_keyword`
- `png.text.invalid_keyword`
- `png.text.value_not_latin1`
- `png.apng.read_only`
- `png.structure.unsupported_critical_chunk`
- `png.structure.invalid_crc`
- `png.resource_limit`

Unknown/absent capability remains read-only through the common capability kernel.

## Fidelity

No edit:

```text
exact-preserve
```

Successful H12 mutation:

```text
high
```

with evidence for:

- requested metadata semantic readback;
- exact ordered chunk topology;
- exact raw preservation of every unrequested chunk;
- exact preservation of all image-bearing critical chunks;
- source authority and target ownership revalidation.

H12 makes no claim that metadata changes preserve a file-wide byte digest, because the target chunk and CRC necessarily change.

## Independent validation

Production code must not depend on Pillow or ExifTool. Tests may use Pillow, when installed, as an independent decoder/metadata oracle. Synthetic valid PNG fixtures should be constructible with `struct`, `zlib` and CRC primitives so core H12 tests have no optional dependency.

## Security and failure behavior

Malformed/truncated chunks, arithmetic boundary errors, invalid CRCs, unknown critical chunks, illegal chunk-type bytes, reserved-bit violations, invalid keyword encoding, duplicate writable keywords, APNG policy blockers and resource-limit violations fail closed for mutation. Caller output remains empty on every failed edit transaction.

## One-way compatibility

H12 must not change `packages/markitdown/src/markitdown/converters/_image_converter.py` or the existing `MarkItDown` one-way conversion API. LLM descriptions remain derived content and are never advertised as native PNG text owners.

## Completion gate

H12 is complete only after:

- spec and implementation plan are committed on the H12 branch;
- test-first RED evidence exists;
- parser/reader/writer/public-contract tests are GREEN;
- stale source, stale locator, duplicate ownership, malformed PNG, CRC, APNG and resource-limit tests are GREEN;
- zero-edit byte identity and target-only raw preservation are proven;
- optional independent decoder regression passes where available;
- existing one-way image behavior is unchanged;
- full repository regression is GREEN;
- pre-commit and package/OCR Python 3.10–3.13 CI are GREEN on the exact final head;
- the final merge is authorized by those exact-head gates.
