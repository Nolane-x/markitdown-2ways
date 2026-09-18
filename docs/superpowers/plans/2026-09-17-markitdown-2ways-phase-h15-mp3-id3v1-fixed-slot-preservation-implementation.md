# Phase H15 MP3 ID3v1 Fixed-Slot Preservation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a conservative native MP3 two-way adapter that updates only existing terminal ID3v1/ID3v1.1 Title, Artist, and Album fixed-width slots while preserving every other byte exactly.

**Architecture:** Introduce a stdlib-only `markitdown.twoways.formats.mp3` package with bounded MPEG Layer III + terminal metadata parsing, deterministic IR/capability projection, fixed-slot transactional writing, and strict re-read verification. The reader may inspect an ID3v1 trailer when writable audio authority is unavailable, but the writer independently fresh-parses source bytes and refuses mutation unless MPEG topology and competing-metadata policy are freshly satisfied.

**Tech Stack:** Python stdlib (`dataclasses`, `hashlib`, `struct`, `typing`), existing MarkItDown 2Ways IR/capability/writer protocols, pytest, optional Mutagen/independent decoder in tests only when already available.

**Spec:** `docs/superpowers/specs/2026-09-17-markitdown-2ways-phase-h15-mp3-id3v1-fixed-slot-preservation-design.md`

## Global Constraints

- Writable surfaces are `.mp3` and `audio/mpeg` only.
- Writable fields are existing ID3v1/1.1 `Title`, `Artist`, and `Album` only; each allocation is exactly 30 bytes.
- Production remains stdlib-only and performs no network, subprocess, ExifTool, FFmpeg, Mutagen, or transcoding I/O.
- File length, MPEG audio bytes, ID3v1 `TAG`, Year, Comment/Track and Genre are immutable.
- ID3v2/APEv2/Lyrics3 or unprovable MPEG audio topology make H15 text owners read-only.
- Writer limits may tighten but never widen persisted read-time limits.
- All edits are preflighted before caller output receives bytes.
- Every byte outside authorized target 30-byte ranges must remain exact.
- Existing one-way `AudioConverter` must not change.

---

### Task 1: Native model, limits, fixtures, and strict MP3/ID3v1 parser

**Files:**
- Create: `packages/markitdown/src/markitdown/twoways/formats/mp3/limits.py`
- Create: `packages/markitdown/src/markitdown/twoways/formats/mp3/model.py`
- Create: `packages/markitdown/src/markitdown/twoways/formats/mp3/parser.py`
- Create: `packages/markitdown/tests/twoways/_mp3_fixtures.py`
- Create: `packages/markitdown/tests/twoways/test_mp3_id3v1_parser.py`

**Interfaces:**
- Produces `Mp3Limits(max_source_bytes, max_audio_frames, max_frame_bytes, max_terminal_metadata_bytes)`.
- Produces immutable `Mp3AudioFrame`, `Mp3Id3v1Owner`, and `ParsedMp3` dataclasses.
- Produces `Mp3FormatError(ValueError)` and `parse_mp3(data: bytes, *, limits: Mp3Limits | None = None) -> ParsedMp3`.
- `ParsedMp3` exposes `owners`, `audio_frames`, `id3v1_start`, `id3v1_end`, `id3v1_sha256`, `blockers`, and deterministic `owner(field)` lookup.

- [ ] **Step 1: Build deterministic synthetic MP3 fixtures**

Create helpers that emit complete MPEG Layer III frames from explicit version/bitrate/sample-rate/padding choices and append an ID3v1 trailer. A fixture frame must be sized from the same public MPEG formula but implemented independently in test code. Include helpers for leading ID3v2, terminal APEv2 footer/tag, Lyrics3v1/v2, malformed trailer padding, truncated audio frame, and ID3v1.1 Comment/Track bytes.

- [ ] **Step 2: Write parser RED tests**

Tests must assert at minimum:

```python
parsed = parse_mp3(make_mp3(title="Alpha", artist="Nolane", album="Lab"))
assert parsed.owner("Title").value == "Alpha"
assert parsed.owner("Artist").slot_length == 30
assert parsed.owner("Album").slot_start == parsed.id3v1_start + 63
assert len(parsed.audio_frames) >= 2
```

Also assert little policy details: full 30-byte no-NUL values are accepted, `b"A\x00B"`-style nonzero bytes after first NUL make that owner ambiguous/read-only evidence, ID3v1.1 track bytes are recognized but never projected as writable fields, and reserved/free-format/truncated MPEG headers do not create writable audio authority.

- [ ] **Step 3: Run parser tests and record RED evidence**

Run:

```bash
cd packages/markitdown
pytest -q tests/twoways/test_mp3_id3v1_parser.py
```

Expected: collection/import failure because the `mp3` package/parser does not exist yet.

- [ ] **Step 4: Implement `Mp3Limits` and immutable native models**

Use positive-integer validation identical in spirit to `JpegLimits`. Keep offsets absolute in the source so verifier/writer can compare exact spans without reconstructing relative positions.

- [ ] **Step 5: Implement ID3v1 parsing**

Require `len(data) >= 128` and `data[-128:-125] == b"TAG"`. Bind Title `[tag+3:tag+33]`, Artist `[tag+33:tag+63]`, Album `[tag+63:tag+93]`. Decode bytes before first NUL with `iso-8859-1`; if a NUL exists and any following byte is nonzero, preserve the field for inspection but mark it noncanonical so capability later becomes read-only.

- [ ] **Step 6: Implement conservative MPEG Layer III frame traversal**

Parse 32-bit frame headers. Accept MPEG-1/2/2.5 Layer III only, reject reserved version/layer/sample-rate, free-format bitrate index `0`, and invalid bitrate index `15`. Use the Layer III tables from the spec:

```python
_MPEG1_L3_KBPS = (0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320, 0)
_MPEG2_L3_KBPS = (0, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160, 0)
_SAMPLE_RATES = {
    0b11: (44100, 48000, 32000),
    0b10: (22050, 24000, 16000),
    0b00: (11025, 12000, 8000),
}
```

Frame length is `floor(144 * bitrate / sample_rate) + padding` for MPEG-1 Layer III and `floor(72 * bitrate / sample_rate) + padding` for MPEG-2/2.5 Layer III. Require at least two complete frames and exact boundary consumption for writable audio authority.

- [ ] **Step 7: Detect competing metadata blockers without rewriting them**

Detect leading `ID3`; terminal APEv2 immediately before ID3v1 using a bounded 32-byte `APETAGEX` footer and declared size; Lyrics3v1 `LYRICSEND`; Lyrics3v2 `LYRICS200` plus six ASCII size digits and matching `LYRICSBEGIN`. Peel only ranges that can be proven in bounds. Malformed declarations become blockers rather than writable authority.

- [ ] **Step 8: Run parser tests GREEN and commit**

Run the focused parser file plus pre-commit. Commit only parser/model/limits/fixtures/tests when GREEN.

---

### Task 2: Deterministic IR reader, capabilities, adapters, and public surface

**Files:**
- Create: `packages/markitdown/src/markitdown/twoways/formats/mp3/reader.py`
- Create: `packages/markitdown/src/markitdown/twoways/formats/mp3/__init__.py`
- Create: `packages/markitdown/tests/twoways/test_mp3_id3v1_reader.py`
- Create: `packages/markitdown/tests/twoways/test_mp3_id3v1_adapters.py`
- Create: `packages/markitdown/tests/twoways/test_mp3_id3v1_public_imports.py`

**Interfaces:**
- Produces `read_mp3_ir(source: BinaryIO, *, filename: str | None = None, mimetype: str | None = None, limits: Mp3Limits | None = None) -> DocumentIR`.
- Produces `Mp3IRReader(DocumentIRReader)` accepting `.mp3` and exact MIME `audio/mpeg`.
- Public package exports `Mp3Limits`, `Mp3FormatError`, `parse_mp3`, `read_mp3_ir`, and `Mp3IRReader`.

- [ ] **Step 1: Write reader/capability RED tests**

Require deterministic `canonical_json_digest`, source SHA/size, one image/audio-like canvas, semantic role `mp3-id3v1-text`, `TextPayload`, exact native locator `id3v1:<field>`, all metadata required by the spec, and persisted `mp3.read_limits.v1`.

Writable decision:

```python
decision = capabilities_for_node(title_node).for_operation("update_mp3_id3v1_text")
assert decision.state is CapabilityState.WRITABLE
assert decision.constraints["fixed_allocation"] is True
assert decision.constraints["source_preservation"] == "mp3-exact-outside-target-slot"
```

Blocker tests must expect stable reasons for ID3v2, APEv2, Lyrics3, noncanonical padding and unproven audio topology.

- [ ] **Step 2: Run focused reader tests RED**

Expected: missing `read_mp3_ir` / `Mp3IRReader` imports.

- [ ] **Step 3: Implement deterministic reader and capability projection**

Persist the read limits exactly. Node IDs include source digest + field identity. Capability state comes from fresh parser evidence, not extension alone. Unknown blockers default read-only.

- [ ] **Step 4: Implement adapters/public exports and run GREEN**

Run reader/adapters/public-import tests and pre-commit; commit only after GREEN.

---

### Task 3: Transactional fixed-slot writer and strict verifier

**Files:**
- Create: `packages/markitdown/src/markitdown/twoways/formats/mp3/verification.py`
- Create: `packages/markitdown/src/markitdown/twoways/formats/mp3/writer.py`
- Modify: `packages/markitdown/src/markitdown/twoways/formats/mp3/__init__.py`
- Create: `packages/markitdown/tests/twoways/test_mp3_id3v1_writer.py`
- Create: `packages/markitdown/tests/twoways/test_mp3_id3v1_verification.py`

**Interfaces:**
- Produces `verify_mp3_candidate(source_bytes: bytes, candidate_bytes: bytes, *, requested_values: Mapping[str, str], requested_ranges: Mapping[str, tuple[int, int]], limits: Mp3Limits | None = None) -> None`.
- Produces `patch_mp3(document: DocumentIR, source: BinaryIO, output: BinaryIO, *, edits: Sequence[EditOperation], limits: Mp3Limits | None = None) -> WriterResult`.
- Produces `Mp3PatchWriter(DocumentWriter)`.

- [ ] **Step 1: Write writer/verifier RED tests**

Cover zero-edit identity, semantic no-op identity, each supported field, full-width 30-byte replacement, shorter NUL padding, two-field transaction, duplicate target rejection, source digest mismatch, source size mismatch, wrong operation, immutable field mismatch, old-value mismatch, non-Latin-1 replacement, >30-byte replacement, stale slot digest and empty caller output on every failure.

- [ ] **Step 2: Run RED and confirm missing writer/verifier behavior**

Expected: missing `patch_mp3` / verifier imports, not unrelated regression.

- [ ] **Step 3: Implement source authority and monotonic read-time limits**

Validate `DocumentIR`, source format `mp3`, SHA-256 and size. Load exactly the persisted limit fields; invalid/missing metadata raises `PatchPreconditionError`. Effective limits are field-wise `min(requested, read_time)`.

- [ ] **Step 4: Implement fresh native binding and complete preflight**

For every edit, require exact locator backend/part/object ID/slot offsets and node metadata digest equality with the fresh owner. Re-evaluate all fresh blockers independently from cached capability metadata. Reject duplicate field targets before candidate construction.

- [ ] **Step 5: Implement ISO-8859-1 fixed-slot encoding**

Encode strictly. If encoded length >30 raise `UnsupportedEditError` with `mp3.id3v1.value_growth`. If shorter than 30, append `b"\x00" * (30-len(encoded))`; exactly 30 bytes remain unpadded.

- [ ] **Step 6: Implement candidate verifier**

Strict re-read both source and candidate. Require equal length, equal frame topology, equal trailer position, exact all bytes outside requested ranges, immutable Year/Comment/Track/Genre and unrequested slots, and requested semantic readback.

- [ ] **Step 7: Emit only after verification**

Build candidate in memory, call verifier, then call `output.write(candidate)`. Zero edits and all no-ops write exact source bytes.

- [ ] **Step 8: Run focused writer/verifier GREEN and commit**

Run both focused test files and pre-commit before commit.

---

### Task 4: Adversarial fresh-authority hardening

**Files:**
- Create: `packages/markitdown/tests/twoways/test_mp3_id3v1_hardening.py`
- Modify as evidence requires: `packages/markitdown/src/markitdown/twoways/formats/mp3/reader.py`
- Modify as evidence requires: `packages/markitdown/src/markitdown/twoways/formats/mp3/writer.py`
- Modify as evidence requires: `packages/markitdown/src/markitdown/twoways/formats/mp3/parser.py`

**Interfaces:** Existing H15 public interfaces only; no scope expansion.

- [ ] **Step 1: Add forged capability RED tests**

Replace a read-only node's capability metadata with a writable decision and prove writer still blocks fresh ID3v2, APEv2, Lyrics3, unproven audio structure and noncanonical padding with empty output.

- [ ] **Step 2: Add forged native evidence RED tests**

Forge slot start/end, field identity, ID3v1 digest, slot digest, payload value, locator object ID and persisted read limits independently. Every case must fail before output.

- [ ] **Step 3: Add malformed terminal metadata/resource RED tests**

Cover oversized/underflow APE size, nonnumeric Lyrics3v2 size, mismatched `LYRICSBEGIN`, source/frame/terminal-metadata budget exhaustion, truncated MPEG frame and reserved header values.

- [ ] **Step 4: Run RED and classify every failure**

Do not patch production until each new test fails for the intended missing policy rather than fixture defects.

- [ ] **Step 5: Apply minimal GREEN fixes and run full hardening file**

Keep fresh-source checks independent of cached capability. Commit only after focused hardening GREEN and pre-commit GREEN.

---

### Task 5: Independent differential, one-way regression, and documentation closure

**Files:**
- Create: `packages/markitdown/tests/twoways/test_mp3_id3v1_differential.py`
- Create: `packages/markitdown/tests/twoways/test_mp3_id3v1_oneway_regression.py`
- Modify: `TWOWAYS.md`

**Interfaces:** No production API expansion beyond H15.

- [ ] **Step 1: Add independent differential checks**

If Mutagen is importable in the test environment, use it as a read-only oracle for ID3v1 semantic values; skip cleanly otherwise. Independently compare audio prefix bytes before the terminal ID3v1 trailer before/after every mutation. Never serialize through the oracle.

- [ ] **Step 2: Lock one-way `AudioConverter` behavior**

Test that H15 introduces no modification to `packages/markitdown/src/markitdown/converters/_audio_converter.py` behavior/routing and does not make the native writer depend on ExifTool or transcription dependencies.

- [ ] **Step 3: Update `TWOWAYS.md`**

Add MP3 ID3v1 fixed-slot support to production scope, a concise H15 usage/preservation section, support matrix entry, fidelity details, and v0.8 roadmap text. Explicitly state ID3v2/APEv2/Lyrics3 and non-MP3 audio formats remain outside H15.

- [ ] **Step 4: Run focused closure tests and pre-commit**

All H15 test files must be GREEN before starting the repository-wide final gate.

---

### Task 6: Exact-tree regression, scope audit, PR provenance, and integration

**Files:**
- No new production scope unless a test proves a defect.
- PR body for the H15 branch is updated with exact provenance only after final CI.

**Interfaces:** Final repository/integration gate.

- [ ] **Step 1: Audit changed-file scope**

Expected scope is H15 spec/plan, `TWOWAYS.md`, `formats/mp3/**`, and H15 tests only. No diagnostic workflow and no change to `_audio_converter.py` may remain.

- [ ] **Step 2: Run repository pre-commit + full package/OCR matrix**

Required exact final gate is nine successes: pre-commit plus package tests Python 3.10, 3.11, 3.12, 3.13 and OCR tests Python 3.10, 3.11, 3.12, 3.13.

- [ ] **Step 3: Record Python 3.13 full-suite counts and inspect warnings**

Any new H15 warning is a closure blocker unless documented and proven unavoidable; pre-existing unrelated warnings are recorded separately.

- [ ] **Step 4: Prove synthetic merge tree equality**

Fetch final branch commit/tree and the PR synthetic merge commit/tree. Require exact tree SHA equality while `main` remains the expected H14 ancestor.

- [ ] **Step 5: Update PR body and mark ready**

Record base SHA, final head SHA/tree, synthetic merge SHA/tree, RED provenance, hardenings, exact 9/9 run, Python 3.13 counts, changed-file audit, and one-way regression result.

- [ ] **Step 6: Merge with expected head SHA and verify `main`**

Use merge commit semantics and `expected_head_sha` to reject drift. After merge, fetch `main` and verify the resulting tree/content contains the exact final H15 tree before declaring H15 integrated.