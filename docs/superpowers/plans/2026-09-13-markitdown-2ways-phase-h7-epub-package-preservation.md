# MarkItDown 2Ways Phase H7 EPUB Package Preservation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox task state and strict test-first sequencing.

**Goal:** Implement conservative source-preserving two-way editing for EPUB 3 publications, allowing selected OPF metadata text and ordinary XHTML body text replacement while preserving OCF/package structure, untouched member content, and existing one-way behavior.

**Architecture:** H7 owns EPUB OCF/package-graph authority and sparse ZIP orchestration. Existing H4 XML remains the lexical mutation authority inside OPF/XHTML members. Every mutation follows source authority -> fresh EPUB evidence -> edit preflight -> H4 lowering -> internal sparse ZIP candidate -> full H7 re-read verification -> caller output. Zero-edit output is byte-identical to the source.

**Tech Stack:** Python stdlib `zipfile`, `hashlib`, `posixpath`, `urllib.parse`; existing `markitdown.twoways.formats.xml` H4 reader/writer; existing DocumentIR/capability/edit/fidelity contracts; pytest; GitHub Actions Python 3.10-3.13 package/OCR matrices.

**Spec:** `docs/superpowers/specs/2026-09-13-markitdown-2ways-phase-h7-epub-package-preservation-design.md`

## Global Constraints

- H7 starts from exact-green H6 `f8930911e643fdaef718f1f0cb701e2b8c8b9bcf`.
- Do not modify `packages/markitdown/src/markitdown/converters/_epub_converter.py`.
- Do not modify the one-way converter registry or one-way CLI behavior.
- Do not weaken H4 XML parsing/writing/security contracts for EPUB coverage.
- No EPUB serializer, DOM save path, network access, external entity resolution, JavaScript execution, media decoding, subprocesses, or remote writeback.
- Writable publication version is EPUB 3.x only. Earlier package versions are inspection-only/read-only.
- Navigation-document text is read-only in H7 tranche one.
- No member insertion/deletion/rename/reorder, no manifest/spine/container structural mutation, no identifier-linkage mutation, no CSS/SVG/MathML/media/link mutation, and no arbitrary whole-member replacement.
- Exactly two H7 edit types are registered: `replace_epub_metadata_text` and `replace_epub_xhtml_text`.
- Production code must not be added before the corresponding tests have been committed and observed RED for the intended missing H7 behavior.
- Caller output remains empty on any mutation/preflight/lowering/package/verification failure.
- Before H7 completion, exact final head must pass pre-commit + package tests Python 3.10/3.11/3.12/3.13 + OCR tests Python 3.10/3.11/3.12/3.13 = 9/9 GREEN.

---

### Task 1: Freeze RED contracts and deterministic EPUB fixtures

**Files:**
- Create: `packages/markitdown/tests/twoways/_epub_fixtures.py`
- Create: `packages/markitdown/tests/twoways/test_epub_package.py`
- Create: `packages/markitdown/tests/twoways/test_epub_parser.py`
- Create: `packages/markitdown/tests/twoways/test_epub_reader.py`
- Create: `packages/markitdown/tests/twoways/test_epub_writer.py`
- Create: `packages/markitdown/tests/twoways/test_epub_verification.py`
- Create: `packages/markitdown/tests/twoways/test_epub_public_imports.py`
- Create: `packages/markitdown/tests/twoways/test_epub_markdown.py`
- Create: `packages/markitdown/tests/twoways/test_epub_oneway_regression.py`

- [ ] **Step 1: Add in-memory EPUB fixture builder.** Build deterministic EPUB 3 ZIPs with `mimetype` first/stored/no-extra, `META-INF/container.xml`, `OEBPS/content.opf`, one normal XHTML spine document, one navigation document, stylesheet and image payload. Allow controlled malformed variants without introducing disk fixtures.
- [ ] **Step 2: Encode OCF/package RED tests.** Cover malformed ZIP, unsafe/absolute/backslash/traversal member names, duplicate names, encrypted flag evidence where constructible, count/size/ratio limits, missing/wrong/not-first/compressed/extra-field `mimetype`, missing/malformed container, multiple rootfiles, unsafe/missing OPF path, DTD/entity surfaces, duplicate manifest IDs, colliding local member ownership, broken spine idrefs, and EPUB 2 read-only behavior.
- [ ] **Step 3: Encode reader/capability RED tests.** Require deterministic root/metadata/manifest/spine/text nodes, source SHA/size authority, writable selected DC metadata owners, writable ordinary XHTML body text, read-only identifier/navigation/script/style/template/foreign SVG/MathML owners, exact H7 capability operation names, and stream-position-restoring MIME probe behavior.
- [ ] **Step 4: Encode writer/verification RED tests.** Require zero-edit byte identity; metadata and XHTML mutations; multiple edits in one member; multi-member edits; semantic no-op/duplicate/invalid payload/read-only target/source-digest/native-evidence/precondition failures; exact untouched-member content preservation; unchanged container/package graph; transactional empty destination on failure; fidelity evidence/tier.
- [ ] **Step 5: Encode identity Markdown and one-way regression RED tests.** Require EPUB projection to be inspection-only for H7 native blocks and lock representative existing one-way EPUB Markdown/title output without editing `_epub_converter.py`.
- [ ] **Step 6: Run focused H7 tests and confirm RED for missing `markitdown.twoways.formats.epub` behavior.** Expected: import/contract failures attributable only to unimplemented H7 production code, not fixture syntax or unrelated tests.
- [ ] **Step 7: Commit RED contracts only.** Commit message: `test: freeze H7 EPUB source-preservation contracts`.

### Task 2: Implement safe OCF ZIP snapshot and EPUB semantic parser

**Files:**
- Create: `packages/markitdown/src/markitdown/twoways/formats/epub/limits.py`
- Create: `packages/markitdown/src/markitdown/twoways/formats/epub/model.py`
- Create: `packages/markitdown/src/markitdown/twoways/formats/epub/package.py`
- Create: `packages/markitdown/src/markitdown/twoways/formats/epub/parser.py`

**Interfaces:**
- `EpubPackageLimits`
- `EpubPackageEntry`, `EpubPackageSnapshot`
- `EpubRootfileEvidence`, `EpubManifestItemEvidence`, `EpubSpineItemEvidence`, `EpubMetadataOwnerEvidence`, `EpubXhtmlTextEvidence`, `ParsedEpubSource`
- `EpubParseError`
- `snapshot_epub_package(source: bytes, *, limits: EpubPackageLimits | None = None) -> EpubPackageSnapshot`
- `parse_epub_source(source: bytes, *, limits: EpubPackageLimits | None = None) -> ParsedEpubSource`

- [ ] **Step 1: Implement `EpubPackageLimits`.** Mirror proven OOXML defaults: 10,000 members, 64 MiB/member, 512 MiB total, ratio 200, 64 MiB XML member; validate positive values.
- [ ] **Step 2: Implement ZIP snapshot fail-closed validation.** Reject malformed ZIP, duplicate names, encrypted entries, unsafe member paths and Unix symlink entries; enforce limits; record ordered inventory, uncompressed SHA-256, sizes, compression method, CRC, flags, timestamps/comments/extra/attributes needed for preservation verification, plus archive comment.
- [ ] **Step 3: Enforce OCF `mimetype`.** Require first member named exactly `mimetype`, `ZIP_STORED`, empty extra field, exact bytes `application/epub+zip`.
- [ ] **Step 4: Parse `container.xml` through H4 XML authority.** Never bypass H4 security. Discover rootfiles from the OCF container namespace. One local safe rootfile permits writable authority; multiple rootfiles remain parseable but mark the publication read-only.
- [ ] **Step 5: Parse OPF package graph through H4 XML evidence.** Validate package root/namespace, version, metadata, manifest and spine. Reject ambiguous duplicate manifest IDs/local ownership and unresolved spine idrefs. Resolve local hrefs with POSIX path rules; preserve remote resources as read-only evidence without dereferencing.
- [ ] **Step 6: Extract selected metadata text owners and XHTML text owners from H4 node ancestry.** Bind every owner to member path + member SHA + XML path + raw digest. Exclude navigation documents and script/style/template/SVG/MathML/foreign namespaces from writable XHTML ownership.
- [ ] **Step 7: Run focused package/parser tests.** Expected: Task 1 package/parser contracts GREEN; reader/writer tests still RED because those modules do not exist.
- [ ] **Step 8: Commit.** Commit message: `feat: add safe EPUB package parser`.

### Task 3: Build deterministic EPUB DocumentIR and capabilities

**Files:**
- Create: `packages/markitdown/src/markitdown/twoways/formats/epub/reader.py`

**Interfaces:**
- `read_epub_ir(source: BinaryIO, *, filename: str | None = None, mimetype: str | None = None, limits: EpubPackageLimits | None = None) -> DocumentIR`
- `EpubIRReader(DocumentIRReader)`

- [ ] **Step 1: Map deterministic publication structure.** Create one `Canvas(kind="publication")`, root `epub-publication`, metadata/manifest/spine groups, ordered manifest resource nodes and spine-reference nodes using IDs derived from source SHA + stable native labels.
- [ ] **Step 2: Add selected metadata text nodes.** Use `TextPayload`; provenance/member URI/native locator bind OPF XML path; advertise `replace_epub_metadata_text` writable only for EPUB 3 exact-roundtrippable selected owners.
- [ ] **Step 3: Add XHTML text nodes.** Bind manifest ID/member/XML path/raw digest and advertise `replace_epub_xhtml_text` only for normal eligible body owners. All H7 identity Markdown constraints are false/inspection-only.
- [ ] **Step 4: Represent read-only publications.** EPUB 2, multiple rootfiles, ambiguous/unsupported writable conditions remain inspectable with explicit read-only reason codes rather than guessed ownership.
- [ ] **Step 5: Implement acceptance/probe.** Accept `.epub` and canonical `application/epub+zip`; probe one-way compatibility MIME prefixes (`application/epub*`, `application/x-epub+zip`) before claiming noncanonical MIME. Probe must restore stream position.
- [ ] **Step 6: Run reader tests.** Expected: package/parser/reader contracts GREEN; writer/public tests remain RED.
- [ ] **Step 7: Commit.** Commit message: `feat: expose EPUB native IR capabilities`.

### Task 4: Register H7 edits and lower authorized owners to H4 XML

**Files:**
- Modify: `packages/markitdown/src/markitdown/twoways/ir/edits.py`
- Create: `packages/markitdown/src/markitdown/twoways/formats/epub/lowering.py`

**Interfaces:**
- Register `replace_epub_metadata_text`
- Register `replace_epub_xhtml_text`
- `lower_epub_member_edits(member_bytes: bytes, member_path: str, requested: Sequence[...]) -> tuple[DocumentIR, tuple[EditOperation, ...]]`

- [ ] **Step 1: Add exactly the two H7 edit types to `INITIAL_EDIT_TYPES`.** Do not add generic member/structural edit types.
- [ ] **Step 2: Build fresh H4 XML IR per touched member.** Resolve H7 recorded XML path to exactly one current H4 text owner and verify recorded member digest/path/kind before lowering.
- [ ] **Step 3: Lower to `replace_xml_text`.** Do not forward caller H7 preconditions into H4. H7 validates caller preconditions first; H4 independently validates fresh XML authority against member bytes.
- [ ] **Step 4: Group all edits for the same member into one H4 transaction.** Duplicate logical XML paths must fail before H4 output.
- [ ] **Step 5: Run lowering/preflight-focused writer tests.** Expected: edit registry/lowering contracts GREEN; package output verification still RED until writer/verifier exists.
- [ ] **Step 6: Commit.** Commit message: `feat: lower EPUB text edits to H4 XML`.

### Task 5: Implement transactional sparse EPUB writer and full candidate verifier

**Files:**
- Extend: `packages/markitdown/src/markitdown/twoways/formats/epub/package.py`
- Create: `packages/markitdown/src/markitdown/twoways/formats/epub/verification.py`
- Create: `packages/markitdown/src/markitdown/twoways/formats/epub/writer.py`

**Interfaces:**
- `build_epub_candidate(snapshot, source_bytes, *, replacements: Mapping[str, bytes], limits=None) -> bytes`
- `verify_epub_candidate(original: ParsedEpubSource, candidate: bytes, *, requested: Mapping[...], touched_members: frozenset[str], limits=None) -> ParsedEpubSource`
- `patch_epub(document: DocumentIR, source_stream: BinaryIO, output: BinaryIO, *, edits: Sequence[EditOperation] = (), limits: EpubPackageLimits | None = None) -> WriterResult`

- [ ] **Step 1: Validate document/source/fresh native authority.** Check format/SHA/size, re-read exact source with H7 reader and require canonical IR equality before mutation.
- [ ] **Step 2: Preflight complete edit set before constructing candidates.** Validate target existence, exact operation-owner match, writable capability, payload `{value: str}`, shared semantic/native/old-value preconditions, no semantic no-op, no duplicate logical owner.
- [ ] **Step 3: Patch touched members only into internal buffers using H4 `patch_xml`.** No caller output yet. If H4 rejects any member, abort with empty destination.
- [ ] **Step 4: Build sparse EPUB candidate.** Reject unknown/additional/deleted/reordered members; preserve member order, OCF mimetype invariant, archive comment, supported ZipInfo metadata and original compression method. Untouched member uncompressed bytes must be exact.
- [ ] **Step 5: Re-read and verify complete candidate.** Require exact inventory/order, exact `container.xml`, same package path/version/identifier linkage/manifest/spine/remote mapping/navigation identity, exact untouched member SHA, requested owner values, and unchanged unrequested H7 owner identities. Rely on H4 proof for lexical target-only preservation inside touched XML members.
- [ ] **Step 6: Write caller destination only after successful verification.** Zero edits write original bytes exactly and claim `exact-preserve`; mutations claim `high` with H7 source/package/native/H4-lowering/member-target-only/untouched-member/OCF/package-graph/candidate-reread evidence.
- [ ] **Step 7: Run writer/preservation/verification tests.** Expected: all core H7 mutation contracts GREEN.
- [ ] **Step 8: Commit.** Commit message: `feat: add transactional EPUB sparse writer`.

### Task 6: Public adapter, projection boundary, and one-way regression lock

**Files:**
- Create: `packages/markitdown/src/markitdown/twoways/formats/epub/writer_adapter.py`
- Create: `packages/markitdown/src/markitdown/twoways/formats/epub/__init__.py`
- Modify only if required by existing projection dispatch: the smallest existing Markdown projection surface needed to mark EPUB identity blocks inspection-only
- Do not modify: `packages/markitdown/src/markitdown/converters/_epub_converter.py`

- [ ] **Step 1: Export the H7 format surface.** Export limits/model/parser/reader/writer/writer adapter from `markitdown.twoways.formats.epub` without polluting the root stable namespace.
- [ ] **Step 2: Add `EpubPatchWriter`.** Accept source `epub` with target format/ext EPUB; require `source_stream=` and `edits=`; pass optional H7 limits only through explicit supported kwargs.
- [ ] **Step 3: Lock Markdown inspection-only behavior.** Ensure projection exposes useful text/metadata but no reversible identity edit authority for EPUB native nodes.
- [ ] **Step 4: Lock existing one-way EPUB conversion.** Run generated representative EPUB through current one-way converter and assert title/metadata/spine Markdown. Confirm `_epub_converter.py` SHA remains unchanged from H6 (`2ba0b0800934f36b9f8e26d9b5f0a3beb91ab6d2`).
- [ ] **Step 5: Run H7 public/import/Markdown/one-way tests.** Expected: GREEN.
- [ ] **Step 6: Commit.** Commit message: `feat: expose EPUB two-way adapter`.

### Task 7: Security hardening, scope audit, and documentation closure

**Files:**
- Modify: `TWOWAYS.md`
- Modify/add H7 tests only where the implementation exposed an uncovered security/preservation boundary

- [ ] **Step 1: Re-run full H7 focused suite.** `pytest -q tests/twoways/test_epub_*.py` must pass.
- [ ] **Step 2: Audit security failure paths.** Confirm malicious paths, duplicate names, mimetype violations, DTD/entity surfaces, rootfile ambiguity, manifest collisions, spine breakage, remote resources, legacy EPUB, excluded XHTML subtrees and output-on-failure are all explicitly tested fail-closed/read-only as designed.
- [ ] **Step 3: Audit production diff against H6.** Allowed production scope: `twoways/formats/epub/**` plus two edit registry entries and only minimal projection integration if empirically required. Forbidden changes: one-way EPUB converter/registry/CLI, H4 XML production behavior, H6 IPYNB production behavior.
- [ ] **Step 4: Update `TWOWAYS.md`.** Document H7 two edit types, EPUB 3-only writable scope, OCF/package/member authority, exact zero edit, high mutation fidelity, H4 composition, unsupported boundaries and security model. Mark recursive ZIP as next v0.6 tranche.
- [ ] **Step 5: Run full package tests locally where available.** `cd packages/markitdown && hatch test -py=3.10` plus focused H7 suite. If the current environment cannot run them, do not substitute claims; rely on the exact-head GitHub matrix below.
- [ ] **Step 6: Commit docs/test closure.** Commit message: `docs: close H7 EPUB preservation scope`.

### Task 8: Exact-head completion gate and handoff to recursive ZIP

**Files:** No production changes after the final candidate SHA is chosen.

- [ ] **Step 1: Record the final H7 head SHA.** Any later commit invalidates this gate and requires a fresh complete matrix.
- [ ] **Step 2: Require pre-commit GREEN on exact final SHA.** One required check.
- [ ] **Step 3: Require package matrix GREEN on exact final SHA.** Python 3.10, 3.11, 3.12, 3.13 = four checks.
- [ ] **Step 4: Require OCR matrix GREEN on exact final SHA.** Python 3.10, 3.11, 3.12, 3.13 = four checks.
- [ ] **Step 5: Confirm 9/9 GREEN and scope audit.** Do not call H7 complete if any job is queued/in-progress/skipped/cancelled/failing or if the branch moved.
- [ ] **Step 6: Leave H7 immutable and start recursive generic ZIP on a new branch from this exact-green H7 SHA.** No recursive ZIP code belongs in H7.

## Plan Self-Review

- Every approved design requirement has an implementation/test task: OCF mimetype, package graph, EPUB 3 writability, two typed edit operations, H4 XML composition, sparse ZIP writing, candidate re-read, untouched-member content, navigation/read-only boundaries, security, identity Markdown, one-way regression, and 9/9 exact-head gate.
- No task asks for a whole-publication serializer or broad structural editing.
- Production interfaces use existing project types (`DocumentIR`, `EditOperation`, `WriterResult`, H4 `read_xml_ir`/`patch_xml`) rather than introducing parallel contracts.
- RED tests precede all H7 production implementation.
- No placeholder/TODO/pseudocode step is accepted as completion.
