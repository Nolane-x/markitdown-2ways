# Phase H16 MSG Unicode Subject Fixed-Stream Preservation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a conservative native Outlook MSG two-way adapter that updates only an existing top-level Unicode `PidTagSubject` stream when the replacement has exactly the same UTF-16LE byte length and every byte outside that stream can be proven unchanged.

**Architecture:** Introduce a stdlib-only `markitdown.twoways.formats.msg` package with a bounded CFB parser, strict MAPI property authority, deterministic IR/capability projection, exact-size subject patching over proven physical ranges, and strict candidate re-read verification. The writer never rebuilds CFB and never uses `olefile` as a serializer; `olefile` is optional test-only differential authority.

**Tech Stack:** Python stdlib (`dataclasses`, `hashlib`, `struct`, `typing`), existing MarkItDown 2Ways IR/capability/writer protocols, pytest, optional `olefile` only in tests.

**Spec:** `docs/superpowers/specs/2026-09-18-markitdown-2ways-phase-h16-msg-unicode-subject-fixed-stream-preservation-design.md`

## Global Constraints

- Writable surface is Outlook `.msg` / `application/vnd.ms-outlook` only.
- Writable property is existing top-level Unicode `PidTagSubject` tag `0x0037001F` only.
- `PidTagStoreSupportMask` tag `0x340D0003` must exist uniquely with `STORE_UNICODE_OK (0x00040000)`.
- ANSI subject `0x0037001E`, `PidTagSubjectPrefix`, and `PidTagNormalizedSubject` block H16 writability.
- Replacement UTF-16LE byte length must equal the existing subject stream size exactly.
- CFB header, DIFAT, FAT, MiniFAT, directory entries, stream sizes/chains, MAPI property stream, and all non-subject bytes are immutable.
- Production performs no network/subprocess I/O and does not depend on `olefile` for writing.
- Writer limits may tighten but never widen persisted read-time limits.
- All edits are preflighted before caller output receives bytes.
- Existing one-way `OutlookMsgConverter` must remain byte-for-byte unchanged.

---

### Task 1: Bounded CFB model, limits, synthetic fixtures, and parser

**Files:**
- Create: `packages/markitdown/src/markitdown/twoways/formats/msg/limits.py`
- Create: `packages/markitdown/src/markitdown/twoways/formats/msg/model.py`
- Create: `packages/markitdown/src/markitdown/twoways/formats/msg/cfb.py`
- Create: `packages/markitdown/tests/twoways/_msg_fixtures.py`
- Create: `packages/markitdown/tests/twoways/test_msg_cfb_parser.py`

**Interfaces:**
- Produces `MsgLimits(max_source_bytes, max_difat_sectors, max_fat_sectors, max_chain_sectors, max_directory_entries, max_minifat_sectors, max_property_entries, max_stream_bytes, max_subject_bytes, max_total_owned_stream_bytes)`.
- Produces immutable `CfbHeader`, `CfbDirectoryEntry`, `CfbStream`, `CfbPhysicalRange`, and `ParsedCfb`.
- Produces `MsgFormatError(ValueError)`.
- Produces `parse_cfb(data: bytes, *, limits: MsgLimits | None = None) -> ParsedCfb`.
- `ParsedCfb.stream(name, *, parent_id=0)` resolves one exact top-level stream or reports ambiguity.

- [ ] **Step 1: Build deterministic synthetic CFB fixtures**

Implement a fixture builder independent from production parsing. It must emit valid CFB v3 with 512-byte sectors and MiniFAT-backed small streams, plus a v4 header/FAT fixture with 4096-byte sectors for parser coverage. Include explicit controls for FAT cycles, MiniFAT cycles, out-of-range sector IDs, duplicate directory names, stream overlap, truncated sectors, and source/resource limits.

- [ ] **Step 2: Write parser RED tests**

Require exact CFB signature/version/sector-size validation, directory decoding, FAT chain traversal, MiniFAT/root mini-stream mapping, physical range derivation, and deterministic topology evidence. Example:

```python
parsed = parse_cfb(make_msg_cfb(subject="Alpha"))
subject = parsed.stream("__substg1.0_0037001F", parent_id=0)
assert subject.logical_bytes == "Alpha".encode("utf-16-le")
assert subject.chain_kind == "mini"
assert sum(r.length for r in subject.physical_ranges) >= len(subject.logical_bytes)
```

Add RED tests for cycle/overlap/out-of-bounds/truncated chains and invalid v3/v4 sector shifts.

- [ ] **Step 3: Run parser tests RED**

Run:

```bash
cd packages/markitdown
pytest -q tests/twoways/test_msg_cfb_parser.py
```

Expected: import/collection failure because the MSG package/parser does not exist.

- [ ] **Step 4: Implement `MsgLimits` and immutable models**

All limits are positive integers. All source offsets/ranges are absolute file offsets. Keep stream logical bytes separate from physical ranges so later verification can prove exact outside-range preservation.

- [ ] **Step 5: Implement strict CFB header + DIFAT/FAT traversal**

Validate v3/v4 sector shifts, byte order, MiniFAT cutoff, sector bounds, DIFAT/FAT counts, cycles, duplicate structural ownership, and chain termination. Do not tolerate reserved/invalid sector identifiers in reachable chains.

- [ ] **Step 6: Implement directory parsing and top-level stream resolution**

Parse fixed 128-byte entries, strict UTF-16LE names, object types, sibling/child IDs, start sectors, and stream sizes. Record raw entry digests. Resolve only the root child tree; nested attachment/recipient streams must not alias top-level names.

- [ ] **Step 7: Implement MiniFAT/root mini-stream mapping**

Translate mini-sector chains into exact physical source ranges through the root stream's ordinary FAT chain. Detect mini-sector cycle, root-chain truncation, cross-stream overlap, and logical-size mismatch.

- [ ] **Step 8: Run parser GREEN, pre-commit, and commit**

Run focused parser tests plus pre-commit. Commit only when parser tests are GREEN.

---

### Task 2: Strict top-level MSG/MAPI subject authority

**Files:**
- Create: `packages/markitdown/src/markitdown/twoways/formats/msg/parser.py`
- Extend: `packages/markitdown/src/markitdown/twoways/formats/msg/model.py`
- Extend: `packages/markitdown/tests/twoways/_msg_fixtures.py`
- Create: `packages/markitdown/tests/twoways/test_msg_subject_parser.py`

**Interfaces:**
- Produces immutable `MsgPropertyEntry`, `MsgSubjectOwner`, and `ParsedMsg`.
- Produces `parse_msg(data: bytes, *, limits: MsgLimits | None = None) -> ParsedMsg`.
- `ParsedMsg.subject_owner` is present for readable Unicode subject ownership; `blockers` controls writability.

- [ ] **Step 1: Write MAPI subject RED tests**

Require:
- exact top-level `__properties_version1.0`;
- 32-byte header plus 16-byte entries;
- unique `0x0037001F` entry;
- unique `0x340D0003` store-support entry with `STORE_UNICODE_OK`;
- subject flags include `PROPATTR_READABLE|PROPATTR_WRITABLE` and StoreSupportMask flags include `PROPATTR_READABLE`;
- subject entry declared size = stream size + 2;
- strict UTF-16LE subject decode;
- no embedded NUL/unpaired surrogate;
- exact property-entry raw digest and physical evidence.

- [ ] **Step 2: Add blocker RED tests**

Cover missing/duplicate Unicode subject, ANSI `0x0037001E`, missing/duplicate store-support mask, missing Unicode bit, missing subject readable/writable flags, unreadable StoreSupportMask, subject-prefix tags `0x003D001F/001E`, normalized-subject tags `0x0E1D001F/001E`, property-size mismatch, duplicate top-level subject stream, and malformed property stream cardinality.

- [ ] **Step 3: Run RED and record exact failure**

Expected: missing `parse_msg` / model interfaces, not fixture errors.

- [ ] **Step 4: Implement property-stream parser**

Parse each 16-byte entry as little-endian tag, flags, and 8-byte value area. For `PT_LONG`, read the 32-bit value from the fixed value area. For variable-length Unicode subject, read declared stream size from the value area and preserve all raw bytes/flags as immutable evidence.

- [ ] **Step 5: Implement subject owner + blocker policy**

Require the exact Unicode/store-support authority and reject competing subject semantics. Readable but non-writable owners remain inspectable with stable blockers.

- [ ] **Step 6: Run GREEN, pre-commit, and commit**

Run subject parser tests and the CFB parser suite together.

---

### Task 3: Deterministic IR reader, capabilities, adapters, and public surface

**Files:**
- Create: `packages/markitdown/src/markitdown/twoways/formats/msg/reader.py`
- Create: `packages/markitdown/src/markitdown/twoways/formats/msg/__init__.py`
- Create: `packages/markitdown/tests/twoways/test_msg_subject_reader.py`
- Create: `packages/markitdown/tests/twoways/test_msg_subject_adapters.py`
- Create: `packages/markitdown/tests/twoways/test_msg_subject_public_imports.py`

**Interfaces:**
- Produces `read_msg_ir(source: BinaryIO, *, filename: str | None = None, mimetype: str | None = None, limits: MsgLimits | None = None) -> DocumentIR`.
- Produces `MsgIRReader(DocumentIRReader)` accepting `.msg` and exact MIME `application/vnd.ms-outlook`.
- Public exports: `MsgLimits`, `MsgFormatError`, `parse_cfb`, `parse_msg`, `read_msg_ir`, `MsgIRReader`.

- [ ] **Step 1: Write reader/capability RED tests**

Require deterministic `canonical_json_digest`, source SHA/size, one message canvas, semantic role `msg-subject-text`, `TextPayload`, exact locator `mapi:0037001F`, all spec metadata, persisted `msg.read_limits.v1`, and deterministic read-limit fingerprint.

Writable capability must advertise:
```python
{
    "identity_markdown": False,
    "existing_owner_only": True,
    "fixed_allocation": True,
    "exact_encoded_length": True,
    "encoding": "utf-16-le",
    "source_preservation": "msg-exact-outside-subject-ranges",
    "property_identity_immutable": True,
    "cfb_topology_immutable": True,
}
```

- [ ] **Step 2: Run RED**

Expected: missing reader/imports.

- [ ] **Step 3: Implement deterministic reader and capability projection**

Node ID binds source digest + `mapi:0037001F`. Persist read limits plus fingerprint. Capability is writable only when fresh parser evidence has no H16 blockers.

- [ ] **Step 4: Implement adapters/public exports and run GREEN**

Run reader/adapters/public import tests and pre-commit.

---

### Task 4: Transactional exact-size writer and strict verifier

**Files:**
- Create: `packages/markitdown/src/markitdown/twoways/formats/msg/verification.py`
- Create: `packages/markitdown/src/markitdown/twoways/formats/msg/writer.py`
- Modify: `packages/markitdown/src/markitdown/twoways/formats/msg/__init__.py`
- Create: `packages/markitdown/tests/twoways/test_msg_subject_writer.py`
- Create: `packages/markitdown/tests/twoways/test_msg_subject_verification.py`

**Interfaces:**
- Produces `verify_msg_candidate(source_bytes: bytes, candidate_bytes: bytes, *, requested_subject: str, authorized_ranges: Sequence[tuple[int, int]], limits: MsgLimits | None = None) -> None`.
- Produces `patch_msg(document: DocumentIR, source: BinaryIO, output: BinaryIO, *, edits: Sequence[EditOperation], limits: MsgLimits | None = None) -> WriterResult`.
- Produces `MsgPatchWriter(DocumentWriter)`.

- [ ] **Step 1: Write writer/verifier RED tests**

Cover zero-edit identity, semantic no-op identity, equal-byte-length ASCII replacement, equal-byte-length non-ASCII Unicode replacement, MiniFAT subject, FAT subject if fixture size crosses cutoff, value-size growth/shrink rejection, embedded-NUL rejection, stale source SHA/size, stale owner, duplicate transaction target, wrong operation, property-tag mutation, forged physical ranges, and empty caller output on all failures.

- [ ] **Step 2: Run RED**

Expected: missing writer/verifier imports.

- [ ] **Step 3: Implement source authority + tamper-evident monotonic limits**

Verify exact `msg` source metadata. Recompute read-limit fingerprint before using any budget. Effective limits are field-wise minimum of caller and read-time values.

- [ ] **Step 4: Implement fresh native binding and full preflight**

Fresh-parse complete source. Recompute blockers independently of cached capability. Verify native locator, property entry digest, subject directory entry digest, chain kind/identity, physical ranges, stream digest, and payload old value. Reject duplicate edits before candidate construction.

- [ ] **Step 5: Implement exact-size UTF-16LE encoding**

Require payload keys exactly `property_tag`, `old_value`, `value`; immutable tag `0x0037001F`; no embedded U+0000; strict UTF-16LE; encoded byte length exactly equals subject stream size.

- [ ] **Step 6: Patch only authorized physical ranges**

Copy full source into a bytearray. Scatter logical replacement bytes across the exact physical ranges in logical order, touching only `subject_stream_size` bytes; bytes in any final partially used mini sector beyond logical stream size remain unchanged.

- [ ] **Step 7: Implement strict candidate verifier**

Require equal total length; identical header/DIFAT/FAT/MiniFAT/directory/property stream/topology; identical non-subject streams; identical subject physical map; exact bytes outside authorized logical subject bytes; candidate semantic subject equals requested value.

- [ ] **Step 8: Emit only after verification and run GREEN**

Only after verifier success write to caller output. Run writer + verifier tests + pre-commit.

---

### Task 5: Adversarial hardening, independent differential, and one-way regression

**Files:**
- Create: `packages/markitdown/tests/twoways/test_msg_subject_hardening.py`
- Create: `packages/markitdown/tests/twoways/test_msg_subject_differential.py`
- Create: `packages/markitdown/tests/twoways/test_msg_subject_oneway_regression.py`
- Modify production files only when RED evidence proves a gap.

**Interfaces:** Existing H16 public interfaces only.

- [ ] **Step 1: Add forged capability/native-evidence RED tests**

Forge writable capability over ANSI/missing-mask/competing-subject sources. Independently forge property tag, entry offset/digest, directory ID/digest, chain kind, chain IDs, physical ranges, stream digest, payload text, locator object ID, and persisted read limits. Every case must fail with empty output.

- [ ] **Step 2: Add CFB adversarial RED tests**

Cover FAT/MiniFAT cycles, sector aliasing, subject range aliasing property stream or directory sectors, truncated root mini stream, duplicate top-level stream names, out-of-range directory IDs, and oversized resource declarations.

- [ ] **Step 3: Run RED and classify failures**

Do not patch production until each failing case is proven to fail for the intended missing policy.

- [ ] **Step 4: Apply minimal GREEN fixes**

Keep fresh-source policy independent from cached IR/capability metadata. Run full H16 hardening suite GREEN.

- [ ] **Step 5: Add optional `olefile` differential tests**

When `olefile` is installed, open source/candidate read-only and prove candidate subject stream decodes to requested text, property stream is unchanged, directory listing is unchanged, and every non-subject stream is unchanged. Skip cleanly if unavailable.

- [ ] **Step 6: Lock one-way Outlook regression**

Run the checked-in `test_outlook_msg.msg` through existing `OutlookMsgConverter`; also lock that `packages/markitdown/src/markitdown/converters/_outlook_msg_converter.py` is absent from the H16 diff.

---

### Task 6: Documentation closure and exact-tree integration

**Files:**
- Modify: `TWOWAYS.md`
- No other production scope unless a RED test proves a defect.
- PR #32 body updated only after exact final CI.

**Interfaces:** Final repository/integration gate.

- [ ] **Step 1: Update `TWOWAYS.md`**

Add H16 MSG Unicode Subject scope, operation `update_msg_subject_text`, exact-size/fixed-stream semantics, ANSI/subject-prefix/normalized-subject blockers, CFB preservation proof, one-way unchanged statement, and v0.8 roadmap progress.

- [ ] **Step 2: Audit changed-file scope**

Expected final scope: H16 spec/plan, `TWOWAYS.md`, `formats/msg/**`, and H16 tests only. No temporary diagnostic workflow and no one-way converter modification may remain.

- [ ] **Step 3: Run exact final pre-commit + package/OCR matrix**

Required exact gate: pre-commit plus package tests Python 3.10/3.11/3.12/3.13 plus OCR tests Python 3.10/3.11/3.12/3.13 = exact 9/9 GREEN.

- [ ] **Step 4: Record Python 3.13 counts/warnings**

Any new H16 warning is a closure blocker unless proven unrelated and documented.

- [ ] **Step 5: Prove synthetic merge-tree equality**

Fetch final branch commit/tree and PR synthetic merge commit/tree. Require exact tree SHA equality while `main` remains the expected H15 ancestor.

- [ ] **Step 6: Update PR provenance and mark ready**

Record base SHA, final head/tree, RED→GREEN evidence, hardening evidence, exact 9/9 run IDs, Python 3.13 counts, changed-file audit, one-way converter blob proof, synthetic merge SHA/tree, and tree equality.

- [ ] **Step 7: Guarded merge and post-merge verification**

Merge PR #32 with `expected_head_sha`. Fetch `main`; require merge parents = expected H15 main + final H16 head and merge tree = exact final H16 tree before declaring H16 integrated.
