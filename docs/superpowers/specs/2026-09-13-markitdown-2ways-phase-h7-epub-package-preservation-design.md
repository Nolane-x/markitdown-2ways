# MarkItDown 2Ways Phase H7 — EPUB Package Preservation Design

## Status

Approved architectural direction for the EPUB tranche of v0.6. H7 is isolated on `phase-h7-epub-package-preservation` from H6 candidate head `f8930911e643fdaef718f1f0cb701e2b8c8b9bcf`.

H7 is lineage-valid only if that H6 head satisfies the H6 exact-head completion gate: standard pre-commit plus package and OCR matrices on Python 3.10–3.13. If H6 requires a repair, H7 must be rebased/restarted from the repaired exact-green H6 head before H7 completion is claimed.

## Goal

Add conservative source-preserving two-way editing for EPUB publications without turning MarkItDown 2Ways into an EPUB authoring suite and without serializing the publication through an EPUB library.

The first writable EPUB boundary is deliberately narrow but useful:

1. edit existing human-readable XHTML body text owners in existing manifest resources;
2. edit selected existing OPF metadata text owners;
3. preserve the EPUB package graph, archive inventory, untouched member bytes and all unrelated lexical content;
4. fail closed when package/container/OPF/resource ownership is ambiguous or unsafe.

The existing one-way `EpubConverter` remains unchanged.

## Why package/member preservation

EPUB is an OCF ZIP container whose package document describes publication metadata, the resource manifest and default reading order through the spine. A safe writer therefore needs two preservation layers:

- **container authority:** the ZIP inventory, OCF `mimetype`, `META-INF/container.xml`, package-document location and member bytes;
- **member authority:** exact lexical ownership inside the OPF or an XHTML member being edited.

A whole-publication serializer is rejected because it can rewrite unrelated ZIP members, XML lexical form, namespace spelling, metadata ordering, compression metadata or resource layout. H7 instead composes an EPUB-specific package graph with the already-proven H4 XML scalar writer for eligible XML/XHTML text owners.

## Normative EPUB boundary used by H7

H7 follows the EPUB 3.x OCF/package model:

- the publication is an OCF ZIP container;
- the root `mimetype` member identifies `application/epub+zip` and must satisfy EPUB OCF placement/storage requirements;
- `META-INF/container.xml` identifies one or more package documents;
- a package document carries metadata, an exhaustive publication-resource manifest and the default reading order in its spine;
- XHTML content documents use XML syntax and are addressed from manifest items;
- manifest/spine/container relationships are semantic authority, not incidental filenames.

H7 does not attempt to repair a non-conforming publication. Ambiguous or unsupported package relationships become read-only or fail parsing according to the boundary below.

## Architectural principles

### 1. No EPUB serializer

Production mutation never calls an EPUB save/serialize API and never reconstructs OPF/XHTML through a DOM serializer.

A mutated publication is produced by sparse member replacement inside the original ZIP inventory. Only explicitly authorized members are replaced. Zero-edit output reuses the exact original EPUB bytes.

### 2. H4 remains the lexical mutation authority inside XML members

Eligible OPF and XHTML edits are lowered to fresh H4 XML `DocumentIR` instances created from the exact member bytes, then to `replace_xml_text` operations.

H7 does not copy caller H7 preconditions into H4 edits. H7 validates its own fresh EPUB evidence first; H4 independently validates the freshly constructed member IR against the same member bytes.

### 3. H7 owns publication semantics

H4 proves XML lexical/source preservation inside a member. H7 additionally proves publication semantics:

- OCF identity and package-document discovery;
- package-document path;
- manifest item IDs, hrefs, media types and properties;
- spine order and idrefs;
- resource-to-member resolution;
- target resource identity;
- requested text semantics;
- untouched member content identity.

### 4. Fail closed rather than normalize

H7 never guesses through duplicate members, unsafe paths, ambiguous rootfiles, duplicate manifest IDs, colliding resolved hrefs, broken spine references or unsupported XML ownership.

### 5. No execution or remote resolution

The 2Ways EPUB core performs no network access, JavaScript execution, CSS execution, media decoding, font loading, external entity resolution, subprocess launch or remote-resource fetching.

Remote manifest resources may be represented as read-only evidence, but H7 never dereferences or mutates them.

## Package safety model

H7 introduces EPUB-specific package evidence rather than reusing OOXML-named errors/contracts directly.

### Archive validation

Before semantic parsing, validate:

- valid ZIP structure;
- configured member-count, per-member size, total-uncompressed-size and compression-ratio limits;
- no encrypted members;
- no duplicate member names;
- no empty names, backslashes, absolute paths, drive-qualified paths, `.` or `..` path segments;
- exact ordered member inventory;
- per-member uncompressed SHA-256, sizes, compression method, CRC, flags and relevant ZIP metadata;
- archive comment;
- OCF `mimetype` existence, placement and storage method;
- exact `mimetype` payload `application/epub+zip`.

Directories may exist but are never writable targets.

### OCF container validation

`META-INF/container.xml` is mandatory. Parse it without DTDs, entity declarations or external resolution.

Record all declared rootfiles, their normalized package paths and media types. The H7 writable boundary requires exactly one authoritative local package document. Multiple package documents may be represented at document level, but H7 advertises no writable capabilities because selecting one representation would require policy/guessing.

A package-document path must resolve to exactly one existing safe archive member.

### Package document validation

The writable package document must be strict XML and have an EPUB OPF package root.

Record deterministic evidence for:

- package version and unique-identifier reference;
- ordered metadata children;
- ordered manifest items;
- each item ID, href, resolved local/remote identity, media type, properties and fallback;
- ordered spine itemrefs and attributes;
- all collections/legacy structural regions as read-only evidence.

Reject writable authority for:

- duplicate manifest IDs;
- duplicate/ambiguous local resolved member ownership;
- malformed/unsafe href resolution;
- spine `idref` values that do not resolve uniquely;
- duplicate spine references where the EPUB contract disallows them;
- package XML that cannot establish exact decode/encode authority;
- structural package relationships requiring repair or inference.

Remote URLs remain read-only and are not fetched.

## Deterministic EPUB model

Add immutable evidence types under `markitdown.twoways.formats.epub`.

Suggested internal contracts:

- `EpubPackageEntry`
- `EpubPackageSnapshot`
- `EpubRootfileEvidence`
- `EpubManifestItemEvidence`
- `EpubSpineItemEvidence`
- `EpubMetadataOwnerEvidence`
- `EpubXhtmlTextEvidence`
- `ParsedEpubSource`
- `EpubParseError`

Every writable owner binds both publication identity and member-local lexical identity.

## `DocumentIR` mapping

### Document and canvas

- `SourceDescriptor(format="epub")` binds source SHA-256 and size.
- One `Canvas(kind="publication")` represents the publication.
- Root node semantic role: `epub-publication`.

### Package structure nodes

Create deterministic read-only group/native nodes for:

- OCF container authority;
- package document;
- metadata group;
- manifest group;
- spine group;
- manifest resources in manifest order;
- spine references in reading order.

These nodes expose enough metadata for inspection and capability reporting but do not authorize structural edits.

### Selected metadata text nodes

Existing lexical text owners for the following OPF/Dublin Core fields may become writable if they have unique H4 ownership and exact byte-roundtrip authority:

- `dc:title`
- `dc:creator`
- `dc:language`
- `dc:publisher`
- `dc:date`
- `dc:description`
- `dc:subject`

The following remain read-only in H7 tranche one:

- unique identifier value and `unique-identifier` linkage;
- `meta` properties that affect rendering/package semantics;
- links;
- manifest/spine/collection data;
- metadata insertion/deletion/reordering;
- attributes on metadata nodes.

### XHTML text nodes

For a local manifest item with media type `application/xhtml+xml`, H7 may expose existing XML text owners as writable when all of these hold:

- member path resolves uniquely and safely;
- member bytes are exact-roundtrippable under H4 XML parsing;
- the document is well-formed XHTML/XML under the conservative H4 security boundary;
- the owner is ordinary text, not CDATA/comment/PI;
- the owner is under XHTML body content;
- the owner is not inside `script`, `style`, `template`, SVG, MathML or another excluded executable/foreign subtree;
- the owner does not participate in package/navigation structure that H7 treats as read-only;
- the edit requires no element/attribute insertion, deletion or reordering.

XHTML documents that contain constructs H4 intentionally rejects, including DTD/entity surfaces, remain readable through the existing one-way converter but are read-only in this first H7 mutation boundary. H7 does not weaken H4 globally to gain coverage.

Navigation documents are parsed as publication evidence. Their structural navigation semantics and link attributes remain read-only. Ordinary visible text may be enabled only if the same XHTML text-owner rules prove it is independent of link/structure mutation; the implementation may conservatively leave navigation-document text read-only in the first GREEN tranche and enable it only behind dedicated tests.

## H7 edit types

Register exactly two EPUB-specific edit types in tranche one:

### `replace_epub_xhtml_text`

Targets one advertised XHTML text node.

Payload:

```json
{
  "value": "Updated paragraph text"
}
```

The target node carries member path, manifest item ID, member SHA-256, XML path, raw digest and native-locator evidence.

### `replace_epub_metadata_text`

Targets one advertised selected OPF metadata text owner.

Payload:

```json
{
  "value": "Updated title"
}
```

Both edit types require the shared semantic/native/expected-old-value precondition discipline. Duplicate logical targets and semantic no-ops fail before candidate construction.

No generic `replace_epub_member` escape hatch exists in H7. Whole-member arbitrary replacement would bypass the semantic preservation model.

## Lowering model

### XHTML lowering

For each touched XHTML member:

1. re-read exact member bytes through H4 `read_xml_ir`;
2. resolve the H7 text owner to exactly one fresh H4 text node by recorded lexical path/evidence;
3. lower to `replace_xml_text`;
4. call H4 `patch_xml` into an internal `BytesIO`;
5. H4 must verify the member candidate before H7 receives the replacement bytes.

Multiple edits in the same member are lowered together so the member is parsed/patched once transactionally.

### OPF metadata lowering

Apply the same composition model to the package-document member, but only for H7-advertised selected metadata text owners.

Manifest, spine, package attributes and identifier linkage are never lowered from H7 edits.

## Sparse EPUB writer

The H7 archive writer receives:

- immutable package snapshot;
- exact source bytes;
- mapping of touched member name → verified replacement bytes.

It must:

- reject unknown/additional member names;
- reject removal or renaming;
- preserve member order;
- preserve the `mimetype` first/stored contract;
- preserve archive comment and supported per-entry ZIP metadata;
- copy unchanged member payload bytes exactly at the uncompressed-content level;
- retain original compression method for every entry;
- enforce output size/compression safety limits;
- write only to an internal candidate buffer until H7 verification completes.

Zero edits write the original EPUB bytes byte-for-byte.

Because Python ZIP rewriting may recompress unchanged members, mutated-output fidelity is defined as exact **member-content** preservation plus preserved inventory/order/ZIP metadata evidence, not exact compressed-stream byte identity. This distinction must be explicit in fidelity reporting.

## Candidate verification

After sparse package construction, H7 re-reads the entire candidate through the strict EPUB parser before caller output.

Verification requires:

### Container invariants

- candidate opens as valid safe ZIP;
- exact ordered member inventory remains unchanged;
- OCF `mimetype` payload/placement/storage remains valid;
- `container.xml` member content is byte-identical;
- package-document path/rootfile evidence is unchanged;
- archive-level supported metadata invariants remain unchanged.

### Package graph invariants

Except selected requested metadata text values, require unchanged:

- package version;
- unique-identifier linkage and identifier value;
- manifest item count/order/IDs/hrefs/resolution/media types/properties/fallbacks;
- spine count/order/idrefs/attributes;
- collections/legacy structural evidence;
- all non-requested OPF lexical owner evidence required by H4/H7.

### Resource invariants

- every untouched member has the same uncompressed SHA-256 as source;
- every requested XHTML member preserves its XML topology/namespace/owner paths under H4 verification;
- unrequested lexical owners inside a touched member retain H4 raw/semantic evidence;
- requested text owners contain exactly requested values;
- resource-to-manifest identity remains unchanged.

Any candidate verification failure leaves caller output empty.

## Transaction model

`patch_epub` follows this order:

1. validate `DocumentIR`;
2. read exact source bytes;
3. verify source SHA-256/size/format;
4. re-parse source and compare fresh EPUB native evidence with recorded IR;
5. preflight the complete H7 edit set;
6. group edits by target member;
7. lower each group to fresh H4 XML edits and patch to internal member buffers;
8. build an internal EPUB candidate through sparse package replacement;
9. run full H7 candidate verification;
10. write candidate bytes to caller output only after every proof passes.

No partial destination output is permitted.

## Fidelity evidence

### Zero edit — `exact-preserve`

Required evidence:

- `epub.source_authority`
- `epub.package_authority`
- `epub.zero_edit_identity`

### Mutation — `high`

Required evidence:

- `epub.source_authority`
- `epub.package_authority`
- `epub.native_evidence`
- `epub.xml_member_lowering`
- `epub.member_target_only`
- `epub.untouched_member_content`
- `epub.ocf_invariants`
- `epub.package_graph_reread`
- `epub.candidate_reread`

Do not call mutated output `exact-preserve` because the ZIP container may be recompressed even when untouched member content is identical.

## Reader acceptance

`EpubIRReader.accepts` accepts:

- `.epub` case-insensitively;
- `application/epub+zip`;
- compatibility MIME aliases already recognized by the one-way converter only when a non-destructive OCF probe confirms an EPUB container.

A generic ZIP must not be claimed as EPUB solely from ZIP structure.

Probing restores the stream position.

## Identity Markdown boundary

EPUB identity Markdown is inspection-only in H7.

The projection may expose publication metadata and ordered spine-readable text, but all EPUB-derived identity blocks advertise no reversible Markdown edit capability. Direct typed H7 edits are authoritative.

This avoids pretending that a flattened Markdown projection can uniquely preserve XHTML element ownership, member identity, OPF ordering or package topology.

## Existing one-way behavior

H7 must not modify:

- `packages/markitdown/src/markitdown/converters/_epub_converter.py`;
- the one-way converter registry;
- one-way CLI behavior;
- existing one-way EPUB metadata/spine rendering semantics.

Add regression tests that lock current one-way behavior around representative EPUBs.

## Explicitly unsupported in H7 tranche one

- member insertion/deletion/rename/reorder;
- manifest/spine/container structural mutation;
- OPF identifier changes;
- cover replacement;
- image/audio/video/font replacement;
- CSS edits;
- SVG/MathML edits;
- script/style/template mutation;
- link/href/src attribute mutation;
- navigation-structure mutation;
- encryption/DRM/obfuscation mutation;
- signatures;
- multiple-package representation selection;
- remote resource fetching/writeback;
- malformed-publication repair;
- arbitrary whole-member replacement;
- EPUB2/legacy special handling beyond what the strict parser can safely represent;
- recursive ZIP/container editing outside EPUB semantics.

Recursive generic ZIP remains the next independent v0.6 tranche after exact-green H7.

## Security requirements

Tests must cover at minimum:

- ZIP path traversal/absolute/drive/backslash paths;
- duplicate members;
- encrypted members;
- ZIP bombs/compression ratio/size limits;
- missing/invalid/misplaced/compressed `mimetype`;
- missing/malformed `container.xml`;
- unsafe package-document paths;
- multiple rootfiles writable fail-closed;
- DTD/entity/external-entity surfaces in container/OPF/XHTML;
- duplicate manifest IDs;
- href collisions/path escapes;
- broken/duplicate spine references;
- remote resources not fetched;
- forged H7 native evidence;
- stale member/source authority;
- target member drift;
- H4 failure propagation;
- candidate package verifier failure with empty caller output.

## Test strategy

Use strict TDD for every production tranche.

Required suites:

1. package snapshot and OCF validation;
2. container/package graph parsing;
3. deterministic EPUB `DocumentIR` and capabilities;
4. selected OPF metadata ownership;
5. XHTML body text ownership and exclusion boundaries;
6. edit registration/preconditions;
7. H4 lowering and grouped member mutation;
8. sparse archive reconstruction;
9. package graph candidate verification;
10. target-only preservation/integration;
11. public adapter/imports;
12. identity-Markdown inspection-only behavior;
13. one-way `EpubConverter` regression;
14. malformed/adversarial corpus;
15. standard pre-commit;
16. package tests Python 3.10–3.13;
17. OCR tests Python 3.10–3.13.

Property/fuzz tests should target safe path normalization, manifest resolution and parser invariants where deterministic bounded generators are practical.

## Scope audit

The final H6→H7 diff must contain only:

- H7 design/implementation documentation;
- `twoways/formats/epub` production code;
- H7 tests/fixtures generated in test code where practical;
- exactly the shared edit-registry additions required for the two H7 edit names;
- bounded shared helpers only if a failing H7 test proves they are necessary and they do not alter prior-format behavior.

No changes to H1–H6 format production code are allowed merely for convenience.

## Completion gate

H7 is complete only when all of the following are true on one exact final branch head:

1. H7 branch lineage starts from the exact-green H6 completion SHA;
2. focused H7 suites are GREEN;
3. full existing package regression is GREEN;
4. existing one-way EPUB regression is GREEN;
5. standard pre-commit is GREEN;
6. package tests are GREEN on Python 3.10, 3.11, 3.12 and 3.13;
7. OCR tests are GREEN on Python 3.10, 3.11, 3.12 and 3.13;
8. scope audit proves no H1–H6 or one-way EPUB behavior drift;
9. no commit is added after the exact-head gate is satisfied.

After exact-green H7, recursive generic ZIP preservation starts on a new branch from that exact H7 completion point.