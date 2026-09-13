# MarkItDown 2Ways Phase H8 — Recursive ZIP Preservation Design

## Status

Approved architectural direction for the recursive ZIP tranche of v0.6. H8 is isolated on `phase-h8-recursive-zip-preservation` and starts from exact-green H7 completion head `dbb016db4797c5646e863735764243d0e5c5b2a7`.

H7 is immutable completion authority. H8 must not add commits to `phase-h7-epub-package-preservation` and must not weaken any H1-H7 safety contract.

## Goal

Add conservative, source-preserving two-way editing for ordinary ZIP containers whose members may themselves be supported MarkItDown 2Ways documents or nested ZIP containers.

H8 is a container-routing and preservation layer, not a generic binary patch API. The first writable boundary is deliberately narrow:

1. represent a safe ZIP inventory deterministically in `DocumentIR`;
2. classify supported members through an explicit two-way adapter registry;
3. expose writable nested nodes only when the underlying format adapter already advertises a writable typed operation;
4. route those typed edits through fresh inner-format authority;
5. recursively support nested ordinary ZIP members under strict global depth/member/expanded-byte budgets;
6. rebuild only the affected member chain while preserving untouched member content and archive inventory;
7. verify the complete recursive candidate before emitting any caller output;
8. preserve the existing one-way `ZipConverter` unchanged.

H8 does **not** add arbitrary whole-member replacement, member insertion/deletion/rename/reorder, extraction-to-disk workflows, remote fetching, archive repair, or a general archive authoring API.

## Why recursive composition

The project already has source-preserving writers for text/Markdown, CSV, JSON, XML, HTML, IPYNB, EPUB, DOCX, PPTX and XLSX. A ZIP container should not duplicate those mutation engines or bypass their preconditions.

H8 therefore treats ZIP as a preservation and routing layer:

```text
outer ZIP authority
    -> member classification
    -> inner format authority
    -> inner typed edit / verifier
    -> replacement member bytes
    -> sparse outer ZIP candidate
    -> recursive verification
```

A generic `replace_zip_member` operation is explicitly rejected because it would allow callers to bypass the typed ownership, stale-source, semantic and verification contracts of the nested format.

## Architectural principles

### 1. H8 owns container authority, not inner document semantics

H8 proves:

- source ZIP identity;
- ordered member inventory;
- safe member naming;
- per-member digest/size/compression/metadata evidence;
- member-chain identity across recursive levels;
- deterministic adapter classification;
- untouched sibling-member identity;
- recursive transaction boundaries.

The selected inner adapter proves the semantics and mutation safety of the nested document.

### 2. No extraction to disk

The H8 two-way path operates entirely on in-memory bytes/file-like streams. It never extracts archive members into filesystem paths and never trusts host filesystem normalization for security.

### 3. No generic raw-member write operation

H8 registers no `replace_zip_member`, `write_zip_member`, or equivalent arbitrary-bytes edit.

Writable nested nodes keep the underlying operation type, for example:

- `replace_text`
- `update_csv_cells`
- `replace_json_scalar`
- `replace_xml_text`
- `replace_xml_attribute`
- `replace_html_text`
- `replace_html_attribute`
- `replace_ipynb_cell_source`
- `replace_epub_metadata_text`
- `replace_epub_xhtml_text`
- existing DOCX/PPTX/XLSX typed operations.

H8 only routes an already-authorized operation to the correct fresh inner document.

### 4. Specific package formats outrank generic ZIP recursion

ZIP-based document formats must not be misclassified as ordinary recursive ZIPs.

Classification priority for ZIP-shaped member bytes is:

1. EPUB package adapter;
2. OOXML package adapters: DOCX, PPTX, XLSX;
3. any future explicitly registered package format with stronger package identity;
4. ordinary recursive ZIP.

A member that matches more than one non-equivalent strong format authority is read-only with an ambiguity reason. H8 never resolves ambiguity by guessing from filename alone.

### 5. Fail closed locally where possible

Unsafe archive structure invalidates the archive authority. Unsupported or ambiguous **member format classification** does not necessarily invalidate the whole outer ZIP: that member may remain opaque/read-only while independent safe members remain writable.

However, a requested edit whose member chain crosses an unsafe, ambiguous, unsupported or stale boundary fails the complete transaction before output.

### 6. No post-verification output mutation

All recursive mutations are built in internal buffers. Caller output receives bytes only after every inner writer and the final recursive H8 verifier have accepted the candidate.

## ZIP safety model

H8 introduces ZIP-specific evidence under `markitdown.twoways.formats.zip` rather than reusing EPUB/OOXML-named contracts.

### Archive validation

Before member classification, validate:

- valid ZIP central directory and readable structure;
- configured member-count limit;
- configured per-member uncompressed size limit;
- configured per-archive uncompressed size limit;
- configured global recursive expanded-byte budget;
- configured global recursive member-count budget;
- configured maximum recursion depth;
- configured compression-ratio limit;
- no encrypted members;
- no duplicate member names;
- no symbolic-link members;
- no empty member names;
- no backslashes in member names;
- no absolute paths;
- no drive-qualified paths;
- no `.` or `..` path segments;
- deterministic directory-entry handling;
- only `ZIP_STORED` and `ZIP_DEFLATED` compression in H8 tranche one;
- exact ordered member inventory;
- per-member uncompressed SHA-256;
- per-member uncompressed/compressed sizes;
- compression method;
- CRC;
- flag bits;
- timestamps and supported ZIP metadata;
- archive comment.

Directory members are represented but never writable targets.

H8 does not repair malformed ZIPs, normalize member names, collapse duplicate paths, or decrypt archives.

### Recursive budgets

`ZipRecursiveLimits` is immutable and carries at minimum:

- `max_depth`;
- `max_members_per_archive`;
- `max_global_members`;
- `max_member_uncompressed_bytes`;
- `max_archive_uncompressed_bytes`;
- `max_global_expanded_bytes`;
- `max_compression_ratio`.

The global counters are shared by the entire recursive read, not reset for each nested archive. A nested archive therefore cannot evade the budget by splitting a bomb across many inner ZIPs.

Recommended initial defaults are conservative and configurable:

- depth: 4 archive levels including the root;
- members per archive: 10,000;
- global members: 10,000;
- member bytes: 64 MiB;
- archive bytes: 512 MiB;
- global expanded bytes: 512 MiB;
- compression ratio: 200x.

The implementation plan may reduce defaults if test evidence shows a safer operational ceiling; it must not silently raise them during H8 implementation.

## Deterministic member classification

### Bounded two-way adapter registry

H8 uses an internal, explicit registry of **two-way** member adapters. It does not call the one-way converter registry and does not let one-way support imply writability.

The initial H8 registry may route these currently proven families:

- native text / Markdown;
- CSV;
- JSON;
- XML;
- HTML;
- IPYNB;
- EPUB;
- DOCX;
- PPTX;
- XLSX;
- ordinary ZIP recursively.

PDF, images, audio, MSG, legacy XLS and remote/derived families remain opaque/read-only in H8 until their own native two-way tranches exist.

### Classification evidence

For each regular member, record:

- full member-chain tuple from root ZIP to current member;
- member name and parent archive depth;
- source member SHA-256 and size;
- filename extension hint;
- optional content/MIME evidence where available;
- all adapter probes attempted;
- selected adapter key, if unique;
- classification state: `typed`, `opaque`, or `ambiguous`;
- stable read-only reason code when not typed.

A filename extension is a hint, never sole authority for ZIP-based package formats.

### Ordinary recursive ZIP eligibility

A member may recurse as an ordinary ZIP only when:

- the bytes are a valid H8 ZIP package;
- no stronger package adapter claims the member;
- recursion depth and global budgets permit descent;
- the member is not encrypted/unsafe/unsupported under H8 archive rules.

If recursion depth is exhausted, the member remains represented as an opaque/read-only ZIP member with reason `zip.recursion.depth_exceeded`; the outer archive may still be writable elsewhere.

## H8 evidence model

Add immutable evidence types under `markitdown.twoways.formats.zip`:

- `ZipRecursiveLimits`;
- `ZipPackageEntry`;
- `ZipPackageSnapshot`;
- `ZipMemberChain`;
- `ZipMemberClassification`;
- `ZipNestedDocumentEvidence`;
- `ParsedZipSource`;
- `ZipParseError`.

A parsed root archive records the complete recursive inventory tree required to prove a member chain without rereading arbitrary filesystem state.

## `DocumentIR` mapping

### Root document

- `SourceDescriptor(format="zip")` binds root source SHA-256 and size.
- The first canvas is `Canvas(kind="archive")` and represents the root ZIP inventory.
- Root semantic role is `zip-archive`.
- The document may contain additional namespaced canvases imported from typed members; H8 therefore does not flatten XLSX/PPTX or other multi-canvas inner documents into one archive canvas.

### Archive/member nodes

Create deterministic structural nodes on the archive canvas for:

- root archive;
- each member in archive order;
- nested ordinary ZIP archive roots;
- nested member nodes recursively.

ZIP structure nodes themselves are read-only in H8 tranche one.

Each regular member node records at minimum:

- `zip.member_chain`;
- `zip.member_path`;
- `zip.depth`;
- `zip.member_sha256`;
- `zip.member_size`;
- `zip.compression_method`;
- `zip.classification`;
- `zip.adapter_key` when typed;
- `zip.identity_markdown = false`.

### Namespaced nested canvases and nodes

When a member is classified to a supported two-way adapter, H8 reads a fresh inner `DocumentIR` and imports its canvases and user-visible semantic nodes into the outer archive document.

For every inner canvas, H8 creates a deterministic namespaced canvas that preserves the inner canvas `kind`, `name`, dimensions/unit when present, root ordering, and format-relevant metadata while adding immutable ZIP routing metadata. Global canvas indexes are assigned deterministically after the root archive canvas according to recursive archive order, member order, then inner canvas index.

Canvas identity depends on:

- canonical full member-chain;
- inner adapter key;
- original inner canvas ID.

Nested node namespacing must be collision-safe and depend on:

- canonical full member-chain;
- inner adapter key;
- inner node ID.

Conceptually:

```text
zip-canvas-id = H("zip-canvas", member_chain, adapter_key, inner_canvas_id)
zip-node-id   = H("zip-node", member_chain, adapter_key, inner_node_id)
```

All root-node references inside imported canvases and all child-node references inside imported nodes are rewritten to the corresponding namespaced outer IDs. H8 must not create cross-document dangling references.

The imported node records immutable routing evidence including:

- original `inner_node_id`;
- original inner canvas membership when applicable;
- adapter key;
- full member-chain;
- inner source SHA-256/size;
- inner semantic/native evidence required to detect drift;
- copied capability declarations, subject to H8 routing constraints.

H8 never exposes an imported node as writable unless the inner node itself advertises the matching operation as writable.

### Provenance boundary

The outer `DocumentIR` source remains the root ZIP. Imported nested nodes therefore do not pretend that the inner member is an independent caller-supplied source file.

H8 stores inner routing/native evidence in H8 metadata and reconstructs a fresh inner `DocumentIR` during preflight. It must not forge the root `SourceDescriptor` or mutate the inner adapter's native locator semantics to make nesting appear flat.

## Capability model

### Writable nested capability

An imported nested node may advertise an inner operation as writable only when all of these hold:

- every ZIP level in its member chain has valid current authority;
- the member classification is unique;
- recursion budgets permit the full chain;
- the inner adapter advertises that operation as writable;
- H8 can deterministically reconstruct the same inner owner from fresh member bytes;
- no structural ZIP mutation is needed.

### ZIP structural capability

All ZIP member/archive structure is read-only in H8 tranche one.

No capability is advertised for:

- member add/delete/rename/reorder;
- directory creation/deletion;
- compression-method changes;
- archive-comment changes;
- timestamps/permissions/extra-field changes;
- encrypted member replacement;
- arbitrary opaque-member bytes;
- archive repair.

### Stable H8 reason codes

Initial reason-code namespace should include at least:

- `zip.member.opaque_format`
- `zip.member.ambiguous_format`
- `zip.member.unsupported_format`
- `zip.member.directory`
- `zip.member.unsafe_path`
- `zip.member.encrypted`
- `zip.member.symlink`
- `zip.member.unsupported_compression`
- `zip.recursion.depth_exceeded`
- `zip.recursion.member_budget_exceeded`
- `zip.recursion.byte_budget_exceeded`
- `zip.member.stale_chain`
- `zip.member.inner_read_only`
- `zip.structure.read_only`

## Edit routing contract

H8 introduces no generic edit type.

### Outer target resolution

For each caller `EditOperation` targeting an imported nested node:

1. resolve the outer node ID exactly once;
2. verify the requested operation matches the outer node's advertised capability;
3. read immutable H8 routing evidence;
4. verify the full member-chain still exists uniquely in a fresh root parse;
5. verify each archive-level member digest/size authority on the path;
6. obtain exact fresh bytes of the terminal typed member;
7. classify the terminal member again and require the same adapter key;
8. construct a fresh inner `DocumentIR` using the selected adapter;
9. resolve the original inner owner uniquely using stored inner identity/evidence;
10. require the fresh inner node to advertise the requested operation;
11. construct the delegated inner edit against the fresh inner node.

H8 never delegates an edit to an inner node merely because the old imported node ID happened to exist.

### Preconditions

H8 validates archive/member-chain authority itself. The inner writer validates its own source/native/semantic preconditions against the fresh inner document.

Operation-specific payload and expected-old-value semantics are preserved. H8 must not weaken or drop a precondition solely to make delegation succeed.

If a precondition references outer archive routing metadata rather than inner native semantics, H8 validates that precondition before delegation rather than forwarding an invalid transformed precondition to the inner writer.

### Multiple edits

Before any mutation, H8 preflights the **entire** edit set.

Edits are grouped by terminal typed member chain. Multiple edits in the same terminal member are delegated together in one inner transaction when the inner writer supports that operation set.

Duplicate logical targets, contradictory edits, two adapter claims for one member, or edits that would require incompatible writers fail before candidate construction.

## Recursive transaction algorithm

For a root ZIP source and a complete edit set:

1. validate outer `DocumentIR`;
2. read exact root source bytes;
3. verify root SHA-256/size/format authority;
4. fresh-parse the complete root ZIP recursively under shared budgets;
5. compare immutable recursive evidence required by the document;
6. preflight every caller edit and resolve terminal member chains;
7. group edits by terminal typed member;
8. for each affected terminal member, invoke the existing inner writer into an internal buffer;
9. require the inner writer/verifier to succeed completely;
10. propagate replacement bytes upward one archive level at a time;
11. at each affected archive level, build a sparse candidate preserving ordered inventory and untouched member content;
12. after all replacements reach the root, obtain one root ZIP candidate;
13. fresh-parse the complete recursive candidate under the same limits;
14. run H8 recursive preservation and semantic verification;
15. write caller output only after all checks pass.

If any step fails, caller output remains empty.

## Sparse ZIP writer contract

### Zero edits

If no edits are requested, output must be byte-for-byte identical to the original root ZIP.

### Mutated archives

For every affected archive level:

- no member may be added, deleted, renamed or reordered;
- directory entries remain unchanged;
- archive comment remains unchanged;
- each untouched immediate member's uncompressed bytes remain exactly identical;
- each touched immediate member may differ only because it is the authorized child candidate produced by the next inner transaction layer;
- per-entry supported ZIP metadata is preserved where Python's ZIP writer can reproduce it safely;
- compression method is preserved and remains Stored/Deflate;
- unknown replacement member names are rejected;
- directory members cannot be replacement targets;
- replacement size/global-budget limits are rechecked before writing.

H8 mutation fidelity is **high source preservation**, not exact compressed-bitstream preservation. Recompressing an affected archive may change raw compressed bytes even when an untouched member's uncompressed content and ZIP metadata are preserved. The fidelity report must not claim exact archive-byte preservation for mutated output.

## Recursive candidate verification

After building the root candidate, H8 reparses it recursively and verifies:

### Root/container invariants

- root candidate is a valid safe H8 ZIP;
- root ordered member inventory is unchanged;
- every nested affected archive retains its ordered member inventory;
- archive comments are unchanged at every affected level;
- member names and directory structure are unchanged;
- no encryption/symlink/unsupported compression appears;
- recursion remains within configured budgets.

### Untouched member invariants

For every immediate member not on an authorized changed path:

- uncompressed SHA-256 is identical;
- uncompressed size is identical;
- compression method and required preserved metadata match the original evidence.

For siblings inside an affected nested archive, the same invariant applies recursively.

### Touched typed-member invariants

For each terminal typed member:

- adapter classification remains the same;
- fresh inner read succeeds;
- requested semantic values are exact;
- all unrequested semantics/native regions are preserved according to the inner adapter's own verifier;
- H8 member-chain evidence still resolves uniquely.

H8 does not reimplement format-specific semantic verification; it relies on the inner writer's proof and then independently confirms routing/classification/member-chain preservation in the final recursive reread.

## Identity Markdown

Identity Markdown for ZIP-backed nested content is inspection-only in H8 tranche one.

Rationale:

- a reversible Markdown importer would need to preserve member-chain routing in addition to the inner adapter's identity comments;
- nested archives introduce another stale-routing boundary;
- direct typed edits already provide the authoritative mutation path.

Therefore:

- imported nested semantic text may appear in identity/inspection projections if the existing projection layer can display it deterministically;
- H8 must advertise `identity_markdown=false` for ZIP routing;
- Markdown import must not synthesize nested ZIP write operations in H8 tranche one.

A later tranche may add reversible archive-aware Markdown only with its own routing/provenance proof.

## One-way ZIP compatibility

`packages/markitdown/src/markitdown/converters/_zip_converter.py` is protected and remains unchanged in H8.

The existing one-way behavior—reading ZIP members, delegating each member through `MarkItDown.convert_stream`, skipping unsupported/file-conversion failures, and combining Markdown—is regression-locked by H8 tests.

The two-way H8 adapter must not be registered in a way that changes the one-way converter dispatch order or output.

## Protected formats and format-confusion rules

H8 must include explicit tests ensuring ordinary ZIP recursion does not steal package files from stronger adapters.

At minimum:

- EPUB bytes inside `.zip` classify as EPUB, not generic ZIP;
- DOCX bytes classify as DOCX, not generic ZIP;
- PPTX bytes classify as PPTX, not generic ZIP;
- XLSX bytes classify as XLSX, not generic ZIP;
- an ordinary ZIP with a misleading `.epub`/`.docx` name is not accepted by a strong adapter unless package evidence matches;
- a member with ambiguous strong evidence is read-only rather than guessed;
- nested ordinary ZIP only activates after strong package probes decline.

## Security boundaries

H8 must fail closed against at least:

- path traversal names at any recursion level;
- absolute/drive-qualified/backslash names;
- duplicate names;
- symlink members;
- encrypted members;
- unsupported compression methods;
- malformed central directories;
- excessive member count;
- excessive per-member size;
- excessive per-archive expanded size;
- excessive global recursive expanded size;
- excessive compression ratio;
- depth exhaustion;
- recursive ZIP bombs;
- stale member-chain SHA/size;
- stale adapter classification;
- forged imported node routing metadata;
- duplicate logical edit targets;
- conflicting edits in one nested member;
- a changed sibling member not authorized by the edit set;
- inner writer failure after partial candidate construction;
- final recursive verification failure.

Every mutation failure must leave caller output empty.

## Read-only / unsupported H8 tranche-one surface

H8 intentionally does not support:

- member insertion/deletion/rename/reorder;
- directory mutation;
- arbitrary opaque member replacement;
- archive comment/metadata editing;
- compression-method conversion;
- password/encryption support;
- split/multi-volume ZIP;
- filesystem extraction/writeback;
- symlink/hardlink semantics;
- archive repair;
- TAR/7z/RAR or other container formats;
- remote URLs as native archive members;
- reversible archive-aware Markdown;
- native mutation of PDF/image/audio/MSG/legacy XLS members before their own format tranches;
- bypassing inner capability/read-only decisions.

## Initial production structure

H8 should remain isolated under:

```text
packages/markitdown/src/markitdown/twoways/formats/zip/
    __init__.py
    limits.py
    model.py
    package.py
    registry.py
    parser.py
    reader.py
    routing.py
    verification.py
    writer.py
    writer_adapter.py
```

The implementation plan may merge very small modules if that lowers complexity without weakening boundaries. It should not spread ZIP logic into unrelated H1-H7 adapters unless a failing test demonstrates a minimal shared helper is necessary.

No changes are expected in the one-way ZIP converter.

## Public H8 surface

Expected format-level API:

- `read_zip_ir(...)`
- `patch_zip(...)`
- `ZipIRReader`
- `ZipPatchWriter`
- `ZipRecursiveLimits`
- `ZipParseError`

The public surface must not expose an arbitrary member-bytes replacement function.

## Test strategy

H8 follows strict TDD. Production code for a behavior is added only after the corresponding RED test is committed and the intended failure is observed.

Required test families:

### Package safety

- deterministic ordered inventory;
- source/member SHA evidence;
- path traversal rejection;
- duplicates;
- symlink rejection;
- encryption rejection;
- unsupported compression rejection;
- member/size/ratio limits;
- zero-edit exact byte identity.

### Classification

- strong package format priority;
- ordinary ZIP fallback;
- extension/content disagreement;
- ambiguous strong adapter read-only behavior;
- opaque unsupported member behavior;
- protected one-way converter regression.

### Recursive reading

- one-level typed members;
- two-plus nested ZIP levels;
- deterministic namespaced node IDs;
- deterministic namespaced canvas IDs and preserved inner canvas/root ordering;
- global depth/member/byte budget enforcement;
- nested capability propagation;
- no writable ZIP structural nodes.

### Routing/lowering

- direct typed edit to nested JSON/XML/HTML/IPYNB/EPUB/text member;
- nested OOXML routing where existing writer contracts permit;
- stale outer SHA;
- stale intermediate member digest;
- stale inner owner;
- adapter reclassification drift;
- duplicate/conflicting target rejection.

### Transaction/preservation

- multiple edits in one member;
- edits in two sibling members;
- edits across two nested branches;
- rollback on one inner failure;
- untouched sibling content identity;
- inventory/order preservation at every affected archive level;
- final recursive verification catches unauthorized drift;
- caller output remains empty on failure.

### Adversarial recursion

- nested ZIP bomb under reduced test limits;
- maximum-depth boundary;
- global member-budget exhaustion;
- global expanded-byte exhaustion;
- misleading package extensions;
- forged routing metadata;
- ambiguous member format.

### Public/projection/regression

- public imports;
- `ZipIRReader` acceptance/probe behavior;
- `ZipPatchWriter` adapter behavior;
- identity Markdown inspection-only;
- one-way `ZipConverter` unchanged.

## CI and completion gate

H8 is complete only when its **exact final branch head** passes:

1. pre-commit;
2. package tests Python 3.10;
3. package tests Python 3.11;
4. package tests Python 3.12;
5. package tests Python 3.13;
6. OCR tests Python 3.10;
7. OCR tests Python 3.11;
8. OCR tests Python 3.12;
9. OCR tests Python 3.13.

No source/docs commit is allowed after the exact-head 9/9 completion proof.

## Completion authority and next tranche

The H8 completion SHA becomes the only valid base for subsequent v0.6+/v0.7 work.

PDF native-safe editing remains a separate tranche. H8 must not absorb PDF mutation, media mutation, archive UI, remote writeback or unrelated format work merely because those files can appear inside ZIP containers.

## Design decisions frozen by approval

- recursive composition, not arbitrary member replacement;
- typed inner operations remain authoritative;
- specific package adapters outrank generic ZIP recursion;
- shared global recursion budgets prevent nested bomb evasion;
- imported nested canvases and nodes use deterministic member-chain namespacing;
- ZIP structure remains read-only in tranche one;
- identity Markdown remains inspection-only;
- one-way `ZipConverter` remains unchanged;
- zero-edit output is exact source bytes;
- mutated output preserves archive inventory and untouched member content but does not claim exact compressed-bitstream identity;
- exact final-head 9/9 CI is mandatory before H8 completion.
