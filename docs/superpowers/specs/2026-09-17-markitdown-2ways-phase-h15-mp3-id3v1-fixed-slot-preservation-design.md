# Phase H15 — MP3 ID3v1 fixed-slot metadata preservation

Status: approved continuation of the v0.8 media tranche after integrated H14.

Base authority: `main@a24b4f4d6992b1ae715b98dda9f55e471fc09691` (merged H14).

## Goal

Add one conservative MP3-native two-way mutation boundary without turning MarkItDown 2Ways into a general MP3 tag editor. H15 permits mutation only of the already-existing terminal ID3v1/ID3v1.1 `Title`, `Artist`, and `Album` fixed-width fields when the source has provable MPEG Layer III audio topology and no competing metadata authority.

## Normative format authority

ID3v1 stores a fixed 128-byte tag at the end of an MP3. Bytes 0..2 of that trailer are uppercase `TAG`; Title, Artist and Album each occupy exactly 30 bytes. ID3v1 string fields use ISO-Latin-1 and shorter strings are padded with zero bytes. ID3v1.1 reuses the last two bytes of the Comment field for track-number signaling; H15 therefore leaves Comment, Track, Year and Genre immutable.

H15 additionally validates a conservative MPEG Layer III frame chain so a random file ending in `TAG` cannot gain writable MP3 authority.

## In scope

- `.mp3` and `audio/mpeg` surfaces only;
- a terminal 128-byte ID3v1/ID3v1.1 trailer identified by exact uppercase `TAG` at `source_size - 128`;
- existing `Title`, `Artist`, and `Album` fields only;
- exact fixed slot offsets and lengths: Title `3..32`, Artist `33..62`, Album `63..92` relative to the ID3v1 trailer;
- ISO-8859-1 decoding/encoding for those fields;
- strict zero-padding interpretation: either the entire 30-byte slot is text, or the first NUL terminates text and every following byte must also be NUL for writable authority;
- conservative MPEG Layer III frame traversal for writable authority;
- one typed operation: `update_mp3_id3v1_text`;
- exact source SHA-256/size authority;
- deterministic native locator and per-slot digest evidence;
- persisted read-time resource limits that writer limits may only tighten;
- complete transaction preflight before mutation;
- fixed-size in-place replacement inside the existing 30-byte allocation;
- exact byte preservation outside requested target slots;
- strict candidate re-read and topology verification;
- independent test-only metadata/audio differential checks when a suitable library is available.

## Explicitly out of scope

H15 does not:

- create or delete an ID3v1 tag;
- resize the file or move the ID3v1 trailer;
- mutate Year, Comment, Track or Genre;
- mutate ID3v2, APEv1/APEv2, Lyrics3, Xing/Info, VBRI, replay-gain, encoder-private, or other metadata;
- rewrite, transcode, decode, normalize, or regenerate MPEG audio frames;
- support free-format MPEG audio, Layer I/II, AAC, M4A/MP4, WAV, FLAC, Ogg, WMA, or other audio containers;
- provide identity-Markdown writeback;
- change the existing one-way `AudioConverter`, ExifTool metadata path, or transcription path.

## Source and audio structural contract

The parser separates metadata inspection from writable audio authority.

A readable H15 source must:

- be at least 128 bytes long;
- contain exact `TAG` bytes at `source_size - 128`;
- expose the three supported 30-byte slots fully in bounds.

Writable authority additionally requires the bytes before the ID3v1 trailer to be a complete conservative MPEG Layer III frame chain. The frame parser:

- begins at byte zero; leading junk is not writable authority;
- requires MPEG version bits for MPEG-1, MPEG-2 or MPEG-2.5, never reserved version;
- requires Layer III, never Layer I/II or reserved layer;
- rejects free-format and invalid bitrate indexes;
- rejects reserved sample-rate indexes;
- computes frame length from the version-specific Layer III bitrate/sample-rate tables and padding bit;
- requires each computed frame to remain in bounds;
- requires at least two frames to reduce accidental sync authority;
- requires frame boundaries to consume the entire audio payload up to the first recognized terminal metadata blocker or the ID3v1 trailer;
- records frame count, start/end offsets, version/layer, bitrate index, sample-rate index and raw-frame digest evidence under configured budgets.

Sources whose ID3v1 trailer is readable but whose audio chain is not provable remain inspectable with read-only capability `mp3.audio_structure_unproven`.

## Competing metadata authority

H15 intentionally refuses native mutation when another common metadata carrier may contain a competing Title/Artist/Album value.

Read-only blockers include:

- a leading ID3v2 header (`ID3`) at byte zero;
- a terminal APE tag immediately before the ID3v1 trailer, identified through its `APETAGEX` footer and bounded size evidence;
- Lyrics3 v1 identified by terminal `LYRICSEND` immediately before ID3v1;
- Lyrics3 v2 identified by terminal `LYRICS200`, six ASCII size digits, and matching bounded `LYRICSBEGIN` start;
- any recognized terminal metadata layer whose declared range is malformed or out of bounds;
- an unprovable MPEG audio chain.

These carriers are never rewritten in H15. Their presence is a dual-authority blocker, not permission to normalize them.

## ID3v1 field ownership

Supported fields are:

| Field | Relative offset | Length |
| --- | ---: | ---: |
| `Title` | `3` | `30` |
| `Artist` | `33` | `30` |
| `Album` | `63` | `30` |

A writable owner must have:

- exact terminal ID3v1 trailer position;
- exact field start/end offsets;
- valid ISO-8859-1 bytes;
- canonical zero-padding semantics: after the first NUL, all remaining field bytes are NUL;
- no global competing-metadata or audio-topology blocker;
- a unique deterministic field identity;
- slot digest evidence matching fresh source bytes.

A 30-byte field with no NUL is a valid full-width value. A shorter replacement is rendered as encoded bytes followed by NUL padding to exactly 30 bytes. A replacement exactly 30 bytes long is written without an added terminator.

## IR mapping

Each supported field is projected as semantic role `mp3-id3v1-text` with `TextPayload`.

Per-node metadata includes at least:

- `mp3.id3v1_field` (`Title`, `Artist`, or `Album`);
- `mp3.id3v1_tag_start` / `mp3.id3v1_tag_end`;
- `mp3.slot_start` / `mp3.slot_end` / `mp3.slot_length`;
- `mp3.slot_sha256`;
- `mp3.id3v1_sha256`;
- `mp3.encoding` = `iso-8859-1`;
- `mp3.full_width`;
- `mp3.audio_frame_count`;
- common capability metadata.

The native locator uses backend `mp3`, part URI `/`, object identity `id3v1:<field>`, and exact absolute slot offsets.

## Resource limits

`Mp3Limits` records at least:

- `max_source_bytes`;
- `max_audio_frames`;
- `max_frame_bytes`;
- `max_terminal_metadata_bytes`.

All values are positive integers. Read-time limits are persisted under `mp3.read_limits.v1` and bound to a deterministic SHA-256 fingerprint. The writer rejects a stale or forged mapping before using any budget. Writer-supplied limits are intersected field-by-field with read-time limits and can never widen authority.

## Mutation contract

Before caller output receives any bytes, the writer must:

1. validate the `DocumentIR`;
2. verify source format, SHA-256 and byte size;
3. load and validate persisted read-time limits;
4. intersect caller limits with read-time limits;
5. fresh-parse the complete source under effective limits;
6. re-evaluate terminal ID3v1 position, competing metadata blockers and MPEG frame authority from fresh bytes;
7. resolve each edit by exact `id3v1:<field>` native locator;
8. verify field name, slot offsets/length, ID3v1 digest and slot digest against fresh source;
9. verify node payload and expected old value against the fresh owner;
10. require writable capability and independently enforce fresh-source policy even if capability metadata was forged;
11. reject duplicate target fields in one transaction;
12. require payload keys `field`, `old_value`, and `value` to be strings with immutable field identity;
13. encode `value` using ISO-8859-1;
14. reject values longer than 30 encoded bytes;
15. build an exact 30-byte replacement using NUL padding only when shorter than 30 bytes;
16. patch only authorized target slots in an internal buffer;
17. require candidate size exactly equal source size;
18. strict re-read source and candidate;
19. verify audio-frame topology, terminal metadata topology, ID3v1 position and all unrequested slot/raw evidence;
20. prove every byte outside authorized target slot ranges is byte-for-byte identical;
21. verify requested fields re-read to exactly the requested values;
22. emit the candidate only after verification succeeds.

Zero edits and semantic no-ops return the exact original bytes.

## Candidate verification

Source and candidate must have identical:

- total byte length;
- ID3v1 trailer start/end and `TAG` marker;
- audio frame count, boundaries and header-derived topology;
- every byte before the ID3v1 trailer;
- Year, Comment/Track and Genre bytes;
- unrequested supported field raw bytes;
- all recognized competing-metadata evidence (normally absent for writable authority).

For each requested field, only its exact 30-byte slot may differ, and the candidate semantic value must equal the requested replacement.

## Failure behavior and stable reasons

Representative reason codes:

- `mp3.id3v1.text.writable`
- `mp3.id3v1.missing`
- `mp3.id3v1.invalid_padding`
- `mp3.id3v1.value_growth`
- `mp3.id3v1.stale_owner`
- `mp3.metadata.id3v2_read_only`
- `mp3.metadata.ape_read_only`
- `mp3.metadata.lyrics3_read_only`
- `mp3.audio_structure_unproven`
- `mp3.audio.unsupported_layer`
- `mp3.audio.free_format_unsupported`
- `mp3.resource_limit`
- `mp3.structure.invalid`

Unknown or absent capability remains read-only through the common capability kernel. Any preflight or verification failure leaves caller output untouched.

## Independent validation

Production H15 remains stdlib-only. Optional test dependencies may be used only as independent metadata/audio decoders; production never serializes an MP3 through Mutagen, FFmpeg, ExifTool, or another tagging/transcoding library.

## One-way regression contract

The existing `AudioConverter` remains byte-for-byte unchanged. H15 adds a separate native two-way path under `markitdown.twoways.formats.mp3`; it does not alter extension/MIME routing, ExifTool metadata extraction, or transcription behavior in the one-way converter.

## Completion gate

H15 is complete only after:

- design and implementation plan are committed on the H15 branch;
- RED evidence exists before each production behavior tranche;
- parser tests cover ID3v1 offsets, Latin-1/full-width/zero-padding, malformed padding, ID3v1.1 comment/track preservation, MPEG-1/2/2.5 Layer III frame traversal, malformed/reserved/free-format headers, truncated frames and resource limits;
- competing ID3v2/APEv2/Lyrics3 blockers are covered;
- reader/capability tests prove deterministic IR and persisted read-time limits;
- writer tests cover zero-edit, no-op, Title/Artist/Album, 30-byte full-width replacement, shorter NUL-padded replacement, multi-edit transaction, non-Latin-1 rejection, growth rejection, stale source and stale owner;
- adversarial tests prove forged capability/native metadata cannot bypass fresh-source policy;
- verifier tests prove exact byte preservation outside authorized 30-byte slots;
- independent metadata/audio differential checks pass where available;
- one-way audio behavior is unchanged;
- `TWOWAYS.md` support matrix and roadmap are updated;
- full repository regression is GREEN;
- pre-commit plus package/OCR Python 3.10–3.13 are GREEN on the exact final tree;
- the synthetic PR merge tree equals the final branch-head tree;
- only then may H15 merge into `main`.