# MarkItDown 2Ways Phase H24 — AudioConverter local-derived snapshot parity

Date: 2026-09-18
Status: frozen design
Base: `main@485a9c1d404268d99b5bf770a7aa9a52c7328a64`

## Purpose

H24 closes the local derived-audio parity gap that remains after H15.

H15 is the native MP3 ID3v1/ID3v1.1 mutation authority. It intentionally does not model
the one-way `AudioConverter`'s optional exiftool metadata projection or speech transcript.
H24 adds those one-way semantics as an explicitly DERIVED, read-only snapshot layer for
the complete default `AudioConverter` acceptance surface.

The caller supplies:

1. the exact local source bytes used by one-way conversion; and
2. an `AudioConverterSnapshot` containing the exact already-materialized Markdown returned
   by the unchanged one-way `AudioConverter.convert()`.

2Ways does not execute exiftool, speech recognition, ffmpeg, network I/O, subprocesses,
model inference or transcription in the H24 production reader.

## Protected one-way authority

H24 freezes:

- file: `packages/markitdown/src/markitdown/converters/_audio_converter.py`
- Git blob: `3d96b53c85490021269f198df94e50096f738b19`
- converter: `AudioConverter`

Current default acceptance authority:

- extensions: `.wav`, `.mp3`, `.m4a`, `.mp4`;
- MIME prefixes: `audio/x-wav`, `audio/mpeg`, `video/mp4`.

Current transcription-format routing authority:

1. `.wav` extension OR exact MIME `audio/x-wav` -> `wav`;
2. else `.mp3` extension OR exact MIME `audio/mpeg` -> `mp3`;
3. else `.mp4` or `.m4a` extension OR exact MIME `video/mp4` -> `mp4`;
4. otherwise no transcription attempt.

This branch order matters. For example, a conflicting `.m4a` + exact
`audio/mpeg` StreamInfo follows the one-way converter's second branch and records
`mp3` as the transcription format. H24 mirrors that behavior exactly rather than
normalizing it into a preferred interpretation.

The final one-way converter return value is `md_content.strip()`. H24 accepts the exact
already-materialized final string and performs no additional semantic transform.

## Ownership boundary

H24 never grants native authority.

For MP3:
- H15 remains the native source-preserving authority for supported ID3v1 text slots;
- H24 is an optional derived enrichment view over the same source bytes;
- an H24 node never carries an H15 native locator and never lowers into an H15 edit.

For WAV/M4A/MP4:
- H24 is derived/read-only only;
- no native writer is introduced.

## Snapshot contract

`AudioConverterSnapshot` contains:

- `content: str` — exact materialized `AudioConverter.convert().markdown`;
- `provider: str` — non-empty identity for the materialization source;
- optional `materialization_id: str`;
- optional `metadata_provider: str`;
- optional `transcript_provider: str`.

Optional descriptors are provenance only. They never change native capability.

The content may be empty because the one-way converter can legally produce an empty
string when neither metadata nor transcript is available.

## Deterministic routing evidence

H24 independently derives from `StreamInfo`:

- whether the one-way converter accepts the source;
- the accepted extension/MIME evidence;
- the one-way transcription format: `wav`, `mp3`, `mp4` or `None`.

The reader fails closed if the source is outside the current one-way default surface.

## Deterministic identity

Document identity binds:

- exact source SHA-256 and size;
- filename, MIME, extension and URI when supplied;
- derived transcription-format route;
- exact materialized Markdown SHA-256 and UTF-8 size;
- snapshot provider/materialization descriptors;
- protected one-way converter identity.

Changing source bytes, output text, route evidence or snapshot descriptors changes the
deterministic document identity.

## Capability boundary

The single semantic root has no native locator.

`replace_text` is `CapabilityState.DERIVED` with reason
`audio.output.not_native_writable` and constraints:

- `identity_markdown=False`
- `native_owner=False`
- `remote_writeback=False`
- `materialization="explicit-local-only"`

H24 exposes no writer, edit type, audio mutation path or identity-Markdown writeback path.

## Provenance envelope

H24 records `twoways.audio_converter_snapshot.v1` with:

- source SHA-256 and byte size;
- filename/MIME/extension/URI when supplied;
- accepted extension/MIME evidence;
- derived transcription format;
- exact materialized Markdown SHA-256 and UTF-8 size;
- provider and optional materialization/metadata/transcript provider descriptors;
- converter name and frozen Git blob;
- `exiftool_executed_by_twoways=False`;
- `transcription_executed_by_twoways=False`;
- `network_performed_by_twoways=False`;
- `subprocess_performed_by_twoways=False`.

## Resource budgets

`AudioDerivedLimits` independently bounds:

- source bytes;
- materialized Markdown UTF-8 bytes.

Source capture uses read requests of at most 64 KiB. Exact boundary sizes pass and one
byte over fails. Limits must be positive integers; booleans/non-integers fail closed.

## Dependency discipline

The production reader may use only standard-library/internal 2Ways imports. It must not
import or invoke:

- `_exiftool`;
- `_transcribe_audio`;
- `speech_recognition`;
- ffmpeg wrappers;
- subprocess;
- socket;
- requests/httpx/urllib network clients;
- sleep/retry machinery.

## Differential regression proof

Tests may import the unchanged one-way converter and monkeypatch its optional helpers:

- fake `exiftool_metadata`;
- fake `transcribe_audio`.

For WAV, MP3, M4A, MP4 and conflict cases, tests prove:

- acceptance parity;
- transcription-format route parity;
- exact final Markdown parity;
- production H24 never calls optional one-way helpers.

The one-way converter Git blob is frozen so any future upstream semantic change fails
loudly before H24 can claim parity.

## Required courts

H24 must cover:

1. extension acceptance parity for WAV/MP3/M4A/MP4;
2. MIME acceptance parity for audio/x-wav, audio/mpeg and video/mp4 prefixes;
3. unsupported source rejection;
4. exact one-way branch-order transcription routing, including conflicts;
5. exact materialized Markdown preservation;
6. empty output support;
7. source/output independent deterministic identity;
8. source/output exact-boundary resource limits;
9. bounded source reads;
10. DERIVED/no-native capability state;
11. deterministic canonical serialization;
12. public read-only exports and no writer symbols;
13. production dependency/network/process firewall;
14. frozen AudioConverter blob;
15. offline differential parity against unchanged one-way AudioConverter;
16. MP3 coexistence court proving H24 never acquires native H15 write authority.

## Closure rule

H24 is complete only after the exact final branch head passes:

- pre-commit;
- package tests Python 3.10, 3.11, 3.12, 3.13;
- OCR tests Python 3.10, 3.11, 3.12, 3.13.

After exact 9/9 GREEN, freeze head/tree, verify branch scope and protected converter blob,
prove a two-parent synthetic merge with exact tree equality, mark the PR ready, merge with
an expected-head guard, then verify post-merge main/tree/parents/blob.
