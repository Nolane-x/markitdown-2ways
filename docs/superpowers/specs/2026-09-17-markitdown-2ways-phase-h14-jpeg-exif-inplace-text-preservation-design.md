# Phase H14 — JPEG Exif in-place text preservation

Status: approved continuation of the v0.8 media tranche after integrated H13.

Base authority: `main@da5446843f5df36b61b6530d06eaa56ace5dad00` (merged H13).

## Goal

Add one conservative JPEG-native two-way mutation boundary without turning MarkItDown 2Ways into a JPEG rewriter or general Exif editor.

H14 permits mutation only of an already-existing, uniquely owned Exif APP1 IFD0 text allocation for the standard `ImageDescription` or `Artist` tag when the complete change fits inside the exact existing TIFF value allocation. No marker, APP1 segment, TIFF entry, count, type, offset, image scan, thumbnail, XMP/IPTC carrier, or unrelated byte may be rewritten.

Normative format authority is the CIPA Exif/JPEG APP1 structure: JPEG APP1 carries `Exif\0\0` followed by TIFF-structured attribute information. H14 intentionally implements a much narrower subset than Exif itself.

## Why in-place allocation only

JPEG metadata becomes dangerous when a writer changes APP1 length or relocates TIFF data. Relocation can invalidate offsets, thumbnail ownership, MakerNote/private structures, sub-IFDs, or vendor data that the writer does not fully understand.

H14 therefore refuses growth beyond an existing text allocation. The source and candidate have exactly the same byte length. All marker positions and segment lengths remain exact. The writer changes only the target value slot bytes.

## In scope

- JPEG/JFIF-family streams accepted by `.jpg`, `.jpeg`, `image/jpeg`, or `image/jpg` surfaces;
- strict JPEG marker traversal from SOI through all scans to EOI, including byte stuffing and restart markers;
- bounded APP1 discovery and exact raw segment evidence;
- Exif APP1 identification by `Exif\0\0`;
- TIFF little-endian (`II`) and big-endian (`MM`) parsing with magic 42;
- bounded reachable IFD traversal sufficient to prove target allocation ownership and overlap safety;
- existing IFD0 `ImageDescription` tag `0x010E` and `Artist` tag `0x013B` only;
- TIFF type 2 text owners only;
- strict ASCII-compatible source text for H14 writable ownership;
- one typed operation: `update_jpeg_exif_text`;
- exact source SHA-256/size authority;
- exact APP1/IFD/tag/value-slot locator and digest evidence;
- complete transaction preflight before mutation;
- same-size in-place replacement with NUL termination and zero padding inside the existing count/allocation;
- exact byte preservation outside authorized target slots;
- strict candidate re-read and topology comparison;
- optional independent Pillow Exif/pixel checks in tests only.

## Explicitly out of scope

H14 does not:

- create or delete APP/COM/JPEG markers;
- create, delete, reorder, resize, or convert TIFF/Exif tags;
- change a TIFF entry type, count, value offset, byte order, IFD count, IFD chain, or pointer;
- grow a text value beyond its current allocation;
- relocate any TIFF payload;
- mutate Exif sub-IFD, GPS, interoperability, thumbnail, MakerNote, UserComment, DateTime, Copyright, ImageTitle, or vendor-private tags;
- mutate XMP, IPTC/Photoshop APP13, ICC APP2, JFIF/JFXX, comments, quantization/Huffman tables, frame/scan headers, entropy-coded image data, or embedded thumbnails;
- interpret or rewrite non-ASCII legacy encodings;
- provide identity-Markdown writeback;
- modify the existing one-way `ImageConverter` or its ExifTool/LLM behavior.

## JPEG structural contract

The parser requires:

- SOI (`FFD8`) at byte 0;
- bounded marker traversal;
- valid segment lengths for all length-bearing markers;
- valid scan traversal where `FF00` is stuffed data and `FFD0`–`FFD7` are restart markers;
- exactly one terminal EOI (`FFD9`);
- no trailing bytes after EOI for writable H14 authority;
- no truncated marker, segment, or scan.

H14 may inspect baseline, progressive, and multi-scan JPEGs because it never rewrites scan data. The parser must still walk every scan so metadata carriers after a scan cannot escape authority checks.

## Metadata authority blockers

A JPEG is read-only for H14 mutation when any of the following is true:

- zero Exif APP1 segments;
- more than one Exif APP1 segment;
- an XMP APP1 carrier is present;
- an APP13 Photoshop/IPTC carrier is present;
- the Exif TIFF structure cannot be parsed safely;
- target tag ownership is duplicated or ambiguous;
- target allocation overlaps another external TIFF value allocation or reachable IFD structure;
- configured resource limits are exceeded.

The XMP/IPTC blockers are deliberate dual-authority protection. H14 will not update an Exif description/artist while leaving another common metadata authority silently stale.

## TIFF traversal and ownership

The Exif APP1 payload begins with six bytes `Exif\0\0`; TIFF offset zero is the first byte immediately after that identifier.

H14 validates:

- byte order (`II` or `MM`);
- TIFF magic `42`;
- IFD0 offset;
- every traversed IFD entry table and next-IFD pointer;
- standard TIFF field types required to compute value byte widths;
- external value offsets/ranges;
- cycles and duplicate IFD offsets;
- global entry/value/depth budgets.

Reachable standard pointer tags are traversed conservatively so the writer can detect structural/value overlaps around the H14 target. Opaque MakerNote/vendor payloads are preserved as byte ranges and never interpreted or mutated.

## Writable tags

H14 supports exactly:

| Tag | ID | IFD | TIFF type |
| --- | ---: | --- | --- |
| `ImageDescription` | `0x010E` | IFD0 | ASCII/type 2 |
| `Artist` | `0x013B` | IFD0 | ASCII/type 2 |

A writable owner must have:

- exactly one matching IFD0 entry for that tag;
- TIFF type 2;
- count at least 2;
- a fully in-bounds value allocation;
- bytes up to the first NUL that decode as strict ASCII;
- all bytes after the first NUL in that allocation equal to zero;
- no overlapping authority with another external TIFF value or IFD structural span;
- no global JPEG metadata-authority blocker.

Strict ASCII is an intentional H14 subset. It is valid UTF-8 and avoids guessing among historical Exif/text conventions. Broader modern UTF-8 support may be a later tranche only with explicit evidence.

## IR mapping

Each supported owner is projected as semantic role `jpeg-exif-text` with `TextPayload`.

Per-node metadata includes at least:

- `jpeg.exif_tag_id`;
- `jpeg.exif_tag_name`;
- `jpeg.marker_index`;
- `jpeg.segment_start` / `jpeg.segment_end`;
- `jpeg.app1_sha256`;
- `jpeg.tiff_byte_order`;
- `jpeg.ifd_path` (`IFD0` for H14 targets);
- `jpeg.ifd_entry_offset`;
- `jpeg.tiff_type`;
- `jpeg.count`;
- `jpeg.value_offset` and `jpeg.value_length`;
- `jpeg.value_slot_sha256`;
- `jpeg.inline_value`;
- common capability metadata.

The native locator binds backend `jpeg`, the exact APP1 marker index, IFD path, tag id, and value slot.

## Resource limits

`JpegLimits` records at least:

- `max_source_bytes`;
- `max_markers`;
- `max_segment_data_bytes`;
- `max_ifd_depth`;
- `max_ifd_entries`;
- `max_total_ifd_entries`;
- `max_tiff_value_bytes`;
- `max_text_value_bytes`.

Read-time limits are persisted in `DocumentIR`. Writer-supplied limits may only tighten them. A caller cannot read under a strict budget and later widen authority during write.

## Mutation contract

Before caller output receives bytes, the writer must:

1. validate the `DocumentIR`;
2. verify source format, SHA-256, and byte size;
3. intersect writer limits with persisted read-time limits;
4. fresh-parse the complete JPEG under effective limits;
5. re-evaluate Exif-count, XMP, and IPTC authority blockers from fresh source bytes;
6. fresh-parse the authoritative Exif TIFF graph;
7. resolve each edit by exact APP1/IFD/tag/value-slot locator;
8. verify target tag id/name, TIFF type/count, byte order, entry offset, value offset/length, APP1 digest, and value-slot digest;
9. verify capability plus semantic/native/expected-old-value preconditions;
10. verify transaction-wide target uniqueness and non-overlap;
11. encode replacement as strict ASCII with no embedded NUL;
12. require `len(encoded) + 1 <= existing_count`;
13. build replacement slot as `encoded + NUL + zero padding` to exactly the existing allocation length;
14. patch only authorized slot byte ranges in an internal buffer;
15. require candidate byte length exactly equal source byte length;
16. strict re-read the complete candidate;
17. verify JPEG marker topology, every segment length, Exif TIFF structure, target immutable metadata, and requested semantic values;
18. prove every byte outside authorized target slots equals the source byte-for-byte;
19. emit candidate bytes only after all verification passes.

Zero edits and semantic no-ops return exact original bytes.

## Candidate verification

Source and candidate must have identical:

- total byte length;
- marker count/order/code/start/end topology;
- all segment length fields;
- SOI/SOS/EOI and scan topology;
- every byte outside target value slots;
- Exif APP1 position and total size;
- TIFF byte order, magic, IFD offsets, IFD entry count/order;
- target tag id, type, count, entry offset, value offset, and allocation length;
- every unrequested TIFF entry/value raw evidence.

Requested target text must re-read to exactly the replacement value.

## Stable failure reasons

Representative reason codes:

- `jpeg.exif.text.writable`
- `jpeg.exif.missing`
- `jpeg.exif.multiple_segments`
- `jpeg.metadata.xmp_read_only`
- `jpeg.metadata.iptc_read_only`
- `jpeg.exif.duplicate_tag`
- `jpeg.exif.unsupported_type`
- `jpeg.exif.invalid_text_encoding`
- `jpeg.exif.value_overlap`
- `jpeg.exif.value_growth`
- `jpeg.exif.stale_owner`
- `jpeg.resource_limit`
- `jpeg.structure.invalid`

Unknown or absent capability remains read-only through the common capability kernel.

## Independent validation

Production H14 remains stdlib-only. Pillow may be used only in tests as an independent JPEG decoder/Exif oracle and to prove decoded pixel bytes are unchanged. The production path never serializes through Pillow, ExifTool, piexif, or another JPEG/Exif writer.

## Completion gate

H14 is complete only after:

- design and implementation plan are committed on the H14 branch;
- RED evidence exists before production support;
- focused parser/reader/writer/verifier tests are GREEN;
- little- and big-endian TIFF cases are covered;
- inline/external value ownership is covered;
- growth, duplicate tag, overlapping allocation, stale source/owner, XMP/IPTC/multiple-Exif, malformed marker/TIFF and resource-limit tests are GREEN;
- zero-edit and semantic no-op exact identity are proven;
- exact byte preservation outside target slots is proven;
- optional Pillow metadata + pixel differential checks pass where available;
- existing one-way image behavior is unchanged;
- `TWOWAYS.md` support matrix and roadmap are updated;
- full repository regression is GREEN;
- pre-commit plus package/OCR Python 3.10–3.13 are GREEN on the exact final tree;
- synthetic PR merge tree equals final head tree;
- only then may H14 merge into `main`.