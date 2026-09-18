# Phase H16 — Outlook MSG Unicode Subject fixed-stream preservation

Status: approved continuation of the v0.8 media / MSG / legacy-XLS program after integrated H15.

Base authority: `main@e05f580cc0a5cbeece4a2074af8237aa197a254d` (merged H15).

## Goal

Add one conservative Outlook `.msg` native two-way mutation boundary without turning MarkItDown 2Ways into a general MAPI or Compound File Binary editor. H16 permits mutation only of the already-existing top-level Unicode `PidTagSubject` property (`0x0037`, `PtypString/PT_UNICODE = 0x001F`) when the subject value stream, property-stream entry, Compound File Binary topology, and physical stream ownership are all provable and the replacement occupies exactly the same encoded stream length.

The design deliberately chooses exact-size subject replacement because it permits a preservation proof that does not allocate, relocate, resize, create, delete, or reorder any CFB stream, directory entry, FAT/MiniFAT chain, or MAPI property entry.

## Normative format authority

An Outlook MSG file is a Compound File Binary (CFB) container holding MAPI storages and streams.

For the H16 property:

- `PidTagSubject` has property identifier `0x0037`;
- Unicode subject uses `PtypString/PT_UNICODE` type `0x001F`;
- the corresponding top-level variable-length property value stream is named exactly `__substg1.0_0037001F`;
- the top-level property stream is named exactly `__properties_version1.0`;
- a top-level MSG property stream has a 32-byte header followed by 16-byte property entries;
- for a variable-length `PtypString` entry, the property-stream `Size` field equals the subject value stream byte length plus two bytes for the logical UTF-16 terminating NUL;
- the stored subject stream bytes themselves are treated as the UTF-16LE payload owned by that property entry; H16 does not synthesize, remove, or resize a property stream entry.

MSG Unicode/non-Unicode authority is message-wide. H16 supports only a source whose string-property authority is Unicode and whose subject owner is the exact `0x0037001F` stream. ANSI `0x0037001E` subject authority remains read-only.

CFB allocates streams smaller than the mini-stream cutoff (normally 4096 bytes) through MiniFAT and the root mini stream, and larger streams through ordinary FAT sector chains. H16 supports the subject only when its complete physical byte ranges can be derived unambiguously from the existing directory entry and the relevant FAT/MiniFAT chains.

## In scope

- extension `.msg` and MIME `application/vnd.ms-outlook`;
- CFB major version 3 or 4 with standard little-endian byte order;
- exact CFB signature and header validation;
- exact top-level stream `__properties_version1.0`;
- exact top-level stream `__substg1.0_0037001F`;
- exactly one top-level `PidTagSubject/PT_UNICODE` property entry;
- exact agreement between the property entry and subject stream:
  - property tag = `0x0037001F`;
  - `Size = subject_stream_size + 2`;
  - nonzero, even subject stream byte length;
  - strict UTF-16LE decoding;
  - no embedded U+0000 in the stored subject payload;
- a single semantic text node for the top-level subject;
- one typed operation: `update_msg_subject_text`;
- exact source SHA-256 and byte-size authority;
- exact directory-entry identity and raw digest evidence;
- exact property-stream entry offset and raw digest evidence;
- exact subject stream logical range, chain identity, raw digest, and physical file ranges;
- bounded CFB directory/FAT/MiniFAT traversal;
- persisted read-time resource limits with tamper-evident fingerprint;
- complete transaction preflight before candidate mutation;
- exact-size UTF-16LE replacement only;
- byte-for-byte preservation outside the subject stream's authorized physical ranges;
- strict candidate re-read and topology verification;
- test-only differential validation through `olefile` where available;
- one-way Outlook converter regression proving H16 does not alter existing conversion behavior.

## Explicitly out of scope

H16 does not:

- create a missing subject;
- delete a subject;
- convert ANSI `PT_STRING8` subject to Unicode;
- support simultaneous Unicode and ANSI string authority;
- grow or shrink the subject stream;
- change the `Size` field in `__properties_version1.0`;
- allocate, free, relocate, compact, or extend any CFB sector or mini sector;
- edit FAT, DIFAT, MiniFAT, header, directory topology, red-black directory links, root mini-stream size, or directory stream size;
- mutate `From`, `To`, `Cc`, body text, HTML body, RTF body, conversation topic/index, normalized subject, subject prefix, attachments, recipients, named properties, embedded messages, or storage attachments;
- synchronize related semantic properties such as `PidTagNormalizedSubject` or `PidTagSubjectPrefix`;
- edit Windows Information Protection/encrypted property payloads;
- provide identity-Markdown writeback;
- rebuild or serialize the MSG through `olefile`, Outlook, COM, libgsf, or any other external writer;
- alter the existing one-way `OutlookMsgConverter`.

Because H16 does not update subject prefix/normalized-subject companions, writable authority is intentionally restricted to sources where no competing subject-semantics carrier creates ambiguity under the rules below.

## CFB structural contract

The H16 parser is strict and bounded. A writable source must satisfy all of the following.

### Header

The parser requires:

- exact CFB signature `D0 CF 11 E0 A1 B1 1A E1`;
- CLSID/header fields structurally valid for the supported CFB versions;
- byte order `0xFFFE`;
- major version 3 with sector shift 9 (512-byte sectors), or major version 4 with sector shift 12 (4096-byte sectors);
- mini-sector shift 6 (64-byte mini sectors);
- mini-stream cutoff exactly `0x1000`;
- FAT/DIFAT/MiniFAT counts and starting sectors in bounds;
- no arithmetic overflow when converting sector identifiers to file offsets.

### DIFAT and FAT

The parser records and validates:

- all FAT sector identifiers reachable from the header DIFAT and chained DIFAT sectors;
- exact FAT sector count agreement;
- no duplicate FAT/DIFAT sector ownership;
- bounded DIFAT traversal;
- FAT entries for all sectors used by the directory stream, root mini stream, MiniFAT stream, subject stream, and property stream;
- chains terminate with `ENDOFCHAIN`;
- no cycles;
- no sector appears twice inside one chain;
- no writable subject physical sector overlaps structural CFB sectors.

H16 does not need to prove every arbitrary application stream semantically, but it must prove enough global ownership to ensure the authorized subject bytes do not alias FAT, DIFAT, MiniFAT, directory, property-stream, or another directory-owned stream range.

### Directory stream

Directory entries are fixed 128-byte records. H16 records:

- directory stream chain and raw digest;
- every allocated directory entry needed to resolve the root and top-level streams;
- stream ID;
- object type;
- UTF-16 directory name;
- sibling/child identifiers;
- starting sector;
- stream size;
- raw 128-byte entry digest.

Writable authority requires exactly one top-level stream named `__properties_version1.0` and exactly one top-level stream named `__substg1.0_0037001F`.

A same-name stream nested under an attachment, recipient, or embedded-message storage is not the H16 owner and does not count as the top-level owner.

Duplicate or ambiguous top-level stream ownership is read-only.

### MiniFAT and root mini stream

For a stream whose size is below the header mini-stream cutoff:

- its directory starting-sector value is interpreted as a mini-sector index;
- the mini-sector chain is followed through MiniFAT;
- the root storage's stream chain supplies the backing mini-stream bytes;
- every logical 64-byte mini sector is translated to one exact physical file range through the root mini-stream FAT chain;
- the chain must contain enough mini sectors for the subject/property stream size and must terminate without cycle or alias;
- physical ranges are recorded in logical stream order.

For a stream at or above the mini-stream cutoff, the ordinary FAT chain is used directly.

The subject stream and property stream may independently use MiniFAT or ordinary FAT according to their sizes.

## MSG property-stream contract

The top-level `__properties_version1.0` stream must be large enough for a 32-byte top-level header followed by complete 16-byte entries.

H16 requires:

- `(stream_size - 32) % 16 == 0`;
- entry count within resource limits;
- exactly one entry with property tag `0x0037001F`;
- its `Size` field equals `subject_stream_size + 2`;
- reserved/flags bytes are preserved exactly and treated as immutable;
- no duplicate `0x0037001F` entry;
- no `0x0037001E` subject entry;
- no contradictory message-wide ANSI authority;
- no encrypted/protected subject payload signature recognized by the bounded H16 policy.

H16 records the exact logical offset and physical ranges of the subject property's 16-byte property entry but never mutates that entry.

## Subject-semantic ambiguity blockers

`PidTagSubject` can coexist with properties used to express subject prefix and normalized subject semantics. H16 is not a subject-normalization engine.

Writable authority is therefore blocked when the top-level property stream advertises a related property that H16 would be required to update to keep message subject semantics synchronized. At minimum, H16 treats present `PidTagSubjectPrefix` and `PidTagNormalizedSubject` string owners as competing semantic authority unless the design can prove they are absent from the source.

This rule is intentionally conservative. H16 mutates only a standalone full subject owner whose requested replacement cannot leave a second subject representation stale.

## Unicode subject ownership

The subject stream must:

- have nonzero, even byte length;
- decode strictly as UTF-16LE;
- contain no embedded U+0000 code point;
- contain no unpaired surrogate;
- have a unique top-level directory owner;
- match the `0x0037001F` property entry's declared size rule;
- have a physical range map whose total logical bytes equal the directory stream size exactly;
- have no physical overlap with CFB structural sectors, the top-level property stream, or any other allocated stream range;
- have a raw SHA-256 digest matching IR evidence.

The replacement value must:

- be a Python string;
- contain no U+0000;
- encode strictly as UTF-16LE;
- have encoded byte length exactly equal to the existing subject stream byte length.

Equal encoded length is the H16 allocation boundary. A semantically shorter value padded with NULs is not allowed because that would change the logical PtypString value. A longer value is not allowed. H16 does not resize the stream or alter the MAPI Size field.

## IR mapping

H16 projects one subject node with semantic role `msg-subject-text` and `TextPayload`.

Document metadata includes at least:

- source format `msg`;
- source SHA-256 and byte size;
- CFB major version;
- CFB sector size;
- mini-sector size;
- mini-stream cutoff;
- CFB topology digest;
- persisted `MsgLimits` mapping;
- deterministic SHA-256 fingerprint of that mapping.

Per-node metadata includes at least:

- `msg.property_id = 0x0037`;
- `msg.property_type = 0x001F`;
- `msg.property_tag = 0x0037001F`;
- `msg.property_name = PidTagSubject`;
- `msg.stream_name = __substg1.0_0037001F`;
- `msg.property_stream_name = __properties_version1.0`;
- `msg.property_entry_index`;
- `msg.property_entry_offset`;
- `msg.property_entry_sha256`;
- `msg.declared_size`;
- `msg.subject_stream_size`;
- `msg.subject_stream_sha256`;
- `msg.subject_directory_id`;
- `msg.subject_directory_entry_sha256`;
- `msg.subject_chain_kind` = `mini` or `fat`;
- `msg.subject_chain`;
- `msg.subject_physical_ranges`;
- `msg.encoding = utf-16-le`;
- common capability metadata.

The native locator uses backend `msg`, top-level part URI `/`, object identity `mapi:0037001F`, and the exact logical subject stream plus physical-range evidence.

## Resource limits

`MsgLimits` records at least:

- `max_source_bytes`;
- `max_difat_sectors`;
- `max_fat_sectors`;
- `max_chain_sectors`;
- `max_directory_entries`;
- `max_minifat_sectors`;
- `max_property_entries`;
- `max_stream_bytes`;
- `max_subject_bytes`;
- `max_total_owned_stream_bytes`.

All values are positive integers.

Read-time limits are persisted under `msg.read_limits.v1` and bound to a deterministic SHA-256 fingerprint. The writer rejects a missing, malformed, stale, or forged limit mapping before using any budget. Writer-supplied limits are intersected field-by-field with read-time limits and can only tighten authority.

## Capability model

The single H16 operation is `update_msg_subject_text`.

A safe subject node advertises writable capability with constraints equivalent to:

- `identity_markdown = false`;
- `existing_owner_only = true`;
- `fixed_allocation = true`;
- `exact_encoded_length = true`;
- `encoding = utf-16-le`;
- `source_preservation = msg-exact-outside-subject-ranges`;
- `property_identity_immutable = true`;
- `cfb_topology_immutable = true`.

All malformed, ambiguous, unsupported, or competing-authority cases are read-only.

## Mutation contract

Before caller output receives any bytes, the writer must:

1. validate the `DocumentIR`;
2. verify source format, SHA-256, and byte size;
3. load persisted read-time limits and verify their fingerprint;
4. intersect caller limits with read-time limits;
5. fresh-parse the complete authoritative source under effective limits;
6. revalidate CFB header, DIFAT, FAT, MiniFAT, directory, root mini stream, top-level property stream, and subject stream;
7. independently recompute all H16 blockers from fresh source bytes rather than trusting cached capability metadata;
8. resolve the edit by exact native locator `mapi:0037001F`;
9. verify property tag/type, property entry location/digest, subject directory identity/digest, logical size, chain kind, chain identity, physical ranges, and subject stream digest against fresh source;
10. verify node payload text and edit `old_value` equal the fresh subject value;
11. require payload keys exactly `property_tag`, `old_value`, and `value`;
12. require immutable `property_tag = 0x0037001F`;
13. reject embedded U+0000 in `value`;
14. encode `value` strictly as UTF-16LE;
15. require encoded replacement length exactly equal to the existing subject stream byte length;
16. preflight the complete transaction before constructing a candidate;
17. copy the complete source into an internal same-size buffer;
18. map replacement logical bytes over the exact authorized physical subject ranges in logical stream order;
19. mutate no other byte;
20. require candidate size exactly equal source size;
21. strict-reparse source and candidate;
22. verify identical CFB topology and MSG property topology;
23. verify exact equality of every byte outside authorized subject physical ranges;
24. verify the candidate subject re-reads to exactly the requested text;
25. emit bytes only after verification succeeds.

Zero edits and semantic no-ops return the exact original bytes.

## Candidate verification

Source and candidate must have identical:

- total file byte length;
- CFB header bytes;
- DIFAT sector identities/content;
- FAT sector identities/content;
- MiniFAT sector identities/content;
- directory stream bytes and every 128-byte directory entry;
- root mini-stream size and FAT chain;
- subject directory stream size and chain;
- top-level property-stream bytes;
- property entry set/order/flags/reserved/size;
- complete storage/directory topology;
- every non-subject stream byte;
- exact subject physical range map.

The only bytes allowed to differ are the physical bytes that correspond to the existing logical subject stream. Those changed bytes must reconstruct exactly the requested UTF-16LE subject and nothing else.

## Stable failure reasons

Representative reason codes include:

- `msg.subject.writable`;
- `msg.subject.missing`;
- `msg.subject.ansi_read_only`;
- `msg.subject.duplicate_property`;
- `msg.subject.duplicate_stream`;
- `msg.subject.invalid_utf16`;
- `msg.subject.embedded_nul`;
- `msg.subject.size_mismatch`;
- `msg.subject.value_size_change`;
- `msg.subject.stale_owner`;
- `msg.subject.competing_semantics`;
- `msg.cfb.invalid_header`;
- `msg.cfb.invalid_difat`;
- `msg.cfb.invalid_fat`;
- `msg.cfb.invalid_minifat`;
- `msg.cfb.invalid_directory`;
- `msg.cfb.chain_cycle`;
- `msg.cfb.chain_overlap`;
- `msg.cfb.stream_overlap`;
- `msg.cfb.unsupported_version`;
- `msg.resource_limit`;
- `msg.structure.invalid`.

Unknown or absent capability remains read-only through the common capability kernel. Any preflight or verification failure leaves caller output untouched.

## Independent validation

Production H16 uses only deterministic byte parsing/writing logic inside the 2Ways MSG adapter and existing core primitives. `olefile` is permitted only as an independent test oracle and for one-way regression checks. Production H16 does not ask `olefile` to serialize or rewrite the MSG.

Differential tests should confirm, where `olefile` is available:

- source and candidate both open successfully;
- candidate `__substg1.0_0037001F` decodes to the requested subject;
- property stream is unchanged;
- all non-subject stream bytes are unchanged;
- directory listing is unchanged.

The checked-in real `test_outlook_msg.msg` fixture is used as an independent real-container regression input when it satisfies the H16 writable subset. Synthetic fixtures are used to cover malformed CFB and adversarial ownership cases.

## One-way regression contract

The existing `packages/markitdown/src/markitdown/converters/_outlook_msg_converter.py` remains byte-for-byte unchanged.

H16 adds a separate native two-way path under `markitdown.twoways.formats.msg`. It does not alter one-way extension/MIME acceptance, Unicode/ANSI code-page decoding, sender/recipient/body extraction, Markdown formatting, dependency behavior, or title selection.

## Security and fail-closed rules

H16 must never infer writability from `.msg` extension alone.

It must reject or remain read-only for:

- malformed CFB files;
- truncated sector chains;
- sector identifiers outside source bounds;
- chain cycles;
- duplicate/aliased subject ownership;
- directory topology ambiguity;
- subject stream aliasing any structural or non-subject stream bytes;
- contradictory property-entry size;
- duplicate Unicode subject property entries;
- simultaneous/competing ANSI subject authority;
- competing subject-prefix/normalized-subject semantic authority;
- subject stream with invalid UTF-16LE;
- encrypted/protected subject representation recognized by policy;
- resource-limit exhaustion;
- caller attempts to loosen read-time limits;
- forged capability, native locator, directory, chain, physical-range, property-entry, or stream-digest metadata.

No failure path may write partial bytes to caller output.

## TDD and completion gate

H16 is complete only after all of the following are true:

- this design is committed on the H16 branch and approved;
- a detailed implementation plan is committed before production implementation;
- RED evidence exists before each production behavior tranche;
- parser fixtures/tests cover:
  - CFB v3 512-byte sectors;
  - CFB v4 4096-byte sectors where supported by the bounded parser;
  - DIFAT/FAT chains;
  - directory entries;
  - MiniFAT/root mini-stream mapping;
  - ordinary FAT-backed streams;
  - chain cycles/overlap/out-of-bounds/truncation;
  - source and resource limits;
- MSG property tests cover:
  - top-level property-stream header/entries;
  - exact `0x0037001F` subject owner;
  - declared `Size = stream_size + 2`;
  - duplicate/missing/ANSI/competing subject authority;
  - strict UTF-16LE;
- reader/capability tests prove deterministic IR and persisted tamper-evident read limits;
- writer tests cover:
  - zero-edit identity;
  - semantic no-op identity;
  - safe same-byte-length subject replacement;
  - Unicode replacement of equal encoded length;
  - MiniFAT-backed subject;
  - FAT-backed subject if supported;
  - size-change rejection;
  - embedded-NUL rejection;
  - stale source;
  - stale owner;
  - duplicate transaction target;
  - forged capability/native evidence;
  - no caller output on all failures;
- verifier tests prove:
  - exact byte preservation outside authorized physical subject ranges;
  - immutable header/FAT/DIFAT/MiniFAT/directory/property stream;
  - identical directory/storage topology;
  - requested semantic subject readback;
- `olefile` differential checks pass where available;
- the checked-in real MSG fixture remains readable through the existing one-way converter;
- the existing one-way `_outlook_msg_converter.py` blob is unchanged;
- `TWOWAYS.md` is updated with H16 scope, operation, blockers, fidelity, and roadmap status;
- all temporary diagnostic workflows are removed;
- full repository regression is GREEN;
- exact final branch head passes pre-commit plus package/OCR Python 3.10–3.13, for exact 9/9 GREEN;
- the PR synthetic merge tree equals the final branch-head tree;
- only then may H16 merge into `main`.

## Deferred MSG roadmap

H16 intentionally leaves the following for later independent tranches, each requiring a new design and preservation proof:

- exact-size ANSI `PidTagSubject` under declared message code page;
- safe coordinated subject-prefix / normalized-subject semantics;
- body text owners;
- HTML/RTF body authority;
- sender/recipient display/address properties;
- attachments and recipient storages;
- named properties;
- embedded MSG mutation;
- variable-length stream resize/reallocation;
- general-purpose CFB structural editing.

H16 succeeds by proving one native MSG mutation can be made exactly, not by maximizing the number of editable MAPI properties.
