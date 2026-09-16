# MarkItDown 2Ways Phase H7 — EPUB Package Preservation Design

## Status

Approved architectural direction for the EPUB tranche of v0.6. H7 is isolated on `phase-h7-epub-package-preservation` from H6 candidate head `f8930911e643fdaef718f1f0cb701e2b8c8b9bcf`.

H7 is lineage-valid only if that H6 head satisfies the H6 exact-head completion gate: standard pre-commit plus package and OCR matrices on Python 3.10–3.13. If H6 requires a repair, H7 must restart from the repaired exact-green H6 head before H7 completion is claimed.

## Goal

Add conservative source-preserving two-way editing for EPUB 3 publications without turning MarkItDown 2Ways into an EPUB authoring suite and without serializing the publication through an EPUB library.

The first writable EPUB boundary is deliberately narrow but useful:

1. edit existing human-readable XHTML body text owners in existing local manifest resources;
2. edit selected existing OPF metadata text owners;
3. preserve the EPUB package graph, archive inventory, untouched member content and all unrelated lexical content;
4. fail closed when package/container/OPF/resource ownership is ambiguous or unsafe.

The existing one-way `EpubConverter` remains unchanged.

## Why package/member preservation

EPUB is an OCF ZIP container whose package document describes publication metadata, the resource manifest and default reading order through the spine. A safe writer therefore needs two preservation layers:

- **container authority:** ZIP inventory, OCF `mimetype`, `META-INF/container.xml`, package-document location and member content;
- **member authority:** exact lexical ownership inside the OPF or XHTML member being edited.

A whole-publication serializer is rejected because it can rewrite unrelated ZIP members, XML lexical form, namespace spelling, metadata ordering, compression metadata or resource layout. H7 instead composes an EPUB-specific package graph with the already-proven H4 XML scalar writer for eligible XML/XHTML text owners.

## Normative EPUB boundary used by H7

H7 follows the EPUB 3 OCF/package model:

- an EPUB publication is an OCF ZIP container;
- the root `mimetype` entry is the first archive member, is stored uncompressed and unencrypted, has no ZIP extra field, and contains exactly the US-ASCII bytes `application/epub+zip` with no BOM or surrounding whitespace;
- OCF ZIP members use only stored or Deflate compression;
- `META-INF/container.xml` identifies one or more package documents;
- a package document carries metadata, an exhaustive publication-resource manifest and the default reading order in its spine;
- XHTML content documents use XML syntax and are addressed from manifest items;
- manifest/spine/container relationships are semantic authority, not incidental filenames.

H7 does not repair a non-conforming publication. Unsupported package relationships become read-only or fail parsing according to the boundary below.

## Architectural principles

### 1. No EPUB serializer

Production mutation never calls an EPUB save/serialize API and never reconstructs OPF/XHTML through a DOM serializer.

A mutated publication is produced by sparse member replacement inside the original ZIP inventory. Only explicitly authorized members are replaced. Zero-edit output reuses the exact original EPUB bytes.

### 2. H4 remains the lexical mutation authority inside XML members

Eligible OPF and XHTML edits are lowered to fresh H4 XML `DocumentIR` instances created from the exact member bytes, then to `replace_xml_text` operations.

H7 does not copy caller H7 preconditions into H4 edits. H7 validates its own fresh EPUB evidence first; H4 independently validates the freshly constructed member IR against the same member bytes.

### 3. H7 owns publication semantics

H4 proves XML lexical/source preservation inside a member. H7 additionally proves:

- OCF identity and package-document discovery;
- package-document path;
- manifest item IDs, hrefs, media types, properties and fallback relations;
- spine order and idrefs;
- resource-to-member resolution;
- target resource identity;
- requested text semantics;
- untouched member-content identity.

### 4. Fail closed rather than normalize

H7 never guesses through duplicate members, unsafe paths, ambiguous rootfiles, duplicate manifest IDs, colliding resolved hrefs, broken spine references or unsupported XML ownership.

### 5. No execution or remote resolution

The 2Ways EPUB core performs no network access, JavaScript execution, CSS execution, media decoding, font loading, external entity resolution, subprocess launch or remote-resource fetching.

Remote manifest resources may be represented as read-only evidence, but H7 never dereferences or mutates them.

## Package safety model

H7 introduces EPUB-specific package evidence rather than exposing OOXML-named package errors/contracts.

### Archive validation

Before semantic parsing, validate:

- valid ZIP structure;
- configured member-count, per-member size, total-uncompressed-size and compression-ratio limits;
- no ZIP encryption;
- no duplicate member names;
- no empty names, backslashes, absolute paths, drive-qualified paths, `.` or `..` path segments;
- OCF filename/path restrictions needed for safe deterministic addressing;
- exact ordered member inventory;
- per-member uncompressed SHA-256, sizes, compression method, CRC, flags and supported ZIP metadata;
- archive comment;
- only stored/Deflate compression methods;
- `mimetype` exists as member zero, is stored, unencrypted, has no extra field and contains exactly `application/epub+zip`.

Directories may exist but are never writable targets.

### OCF container validation

`META-INF/container.xml` is mandatory. Parse it without DTDs, entity declarations or external resolution.

Record all declared rootfiles, their normalized package paths and media types. The H7 writable boundary requires exactly one authoritative local package document. Multiple package documents are represented at document level but make the entire EPUB read-only because H7 does not choose a rendition by policy.

A package-document path must resolve to exactly one existing safe archive member.

### Package document validation

The writable package document must be strict XML, have an EPUB OPF package root and declare EPUB major version 3. EPUB 2 or unknown/unsupported package versions may be inspected but advertise no H7 writable capabilities.

Record deterministic evidence for:

- package version and unique-identifier reference;
- ordered metadata children;
- ordered manifest items;
- each item ID, href, resolved local/remote identity, media type, properties and fallback;
- ordered spine itemrefs and attributes;
- collections/legacy structural regions as read-only evidence.

Reject writable authority for:

- duplicate manifest IDs;
- duplicate/ambiguous local resolved-member ownership;
- malformed/unsafe href resolution;
- spine `idref` values that do not resolve uniquely;
- repeated spine references when they violate the package contract;
- package XML that cannot establish exact decode/encode authority;
- structural package relationships requiring repair or inference.

Remote URLs remain read-only and are not fetched.

## Deterministic EPUB model

Add immutable evidence types under `markitdown.twoways.formats.epub`:

- `EpubPackageEntry`
- `EpubPackageSnapshot`
- `EpubRootfileEvidence`
- `EpubManifestItemEvidence`
- `EpubSpineItemEvidence`
- `EpubMetadataOwnerEvidence`
- `EpubXhtmlTextEvidence`
- `ParsedEpubSource`
- `EpubParseError`

Every writable owner binds publication identity and member-local lexical identity.

## `DocumentIR` mapping

### Document and canvas

- `SourceDescriptor(format="epub")` binds source SHA-256 and size.
- One `Canvas(kind="publication")` represents the publication.
- Root node semantic role is `epub-publication`.

### Package structure nodes

Create deterministic read-only nodes for:

- OCF container authority;
- package document;
- metadata group;
- manifest group;
- spine group;
- manifest resources in manifest order;
- spine references in reading order.

These nodes expose inspection/capability evidence but do not authorize structural edits.

### Selected metadata text nodes

Existing lexical text owners for these OPF/Dublin Core fields may be writable when unique H4 ownership and exact byte-roundtrip authority are proven:

- `dc:title`
- `dc:creator`
- `dc:language`
- `dc:publisher`
- `dc:date`
- `dc:description`
- `dc:subject`

The following remain read-only in H7 tranche one:

- unique identifier value and `unique-identifier` linkage;
- `meta` properties;
- links;
- manifest/spine/collection data;
- metadata insertion/deletion/reordering;
- attributes on metadata nodes.

### XHTML text nodes

For a local manifest item with media type `application/xhtml+xml`, H7 exposes an existing XML text owner as writable only when all of these hold:

- member path resolves uniquely and safely;
- member bytes are exact-roundtrippable under H4 XML parsing;
- document is well-formed XHTML/XML under the H4 security boundary;
- owner is ordinary text, not CDATA/comment/PI;
- owner is beneath the XHTML `body` element;
- owner is not inside `script`, `style`, `template`, SVG, MathML or another foreign/executable subtree;
- item is not the EPUB navigation document;
- edit requires no element/attribute insertion, deletion or reordering.

XHTML documents containing constructs H4 intentionally rejects, including DTD/entity surfaces, remain readable through the existing one-way converter but are read-only in H7. H7 does not weaken H4 globally to gain coverage.

The EPUB navigation document is fully read-only in H7 tranche one. Its visible text, hierarchy and link attributes are publication-navigation authority and are not mixed into the first mutation tranche.

## H7 edit types

Register exactly two EPUB-specific edit types.

### `replace_epub_xhtml_text`

Targets one advertised XHTML body-text node.

Payload:

```json
{
  "value": "Updated paragraph text"
}
```

The target binds member path, manifest item ID, member SHA-256, XML path, raw digest and native-locator evidence.

### `replace_epub_metadata_text`

Targets one advertised selected OPF metadata text owner.

Payload:

```json
{
  "value": "Updated title"
}
```

Both edit types use the shared semantic/native/expected-old-value precondition discipline. Duplicate logical targets and semantic no-ops fail before candidate construction.

There is no generic `replace_epub_member` escape hatch. Whole-member arbitrary replacement would bypass the semantic preservation model.

## Lowering model

### XHTML lowering

For each touched XHTML member:

1. re-read exact member bytes through H4 `read_xml_ir`;
2. resolve each H7 owner to exactly one fresh H4 text node by recorded lexical path/evidence;
3. lower to `replace_xml_text`;
4. call H4 `patch_xml` into an internal `BytesIO`;
5. require H4 member verification before H7 accepts replacement bytes.

Multiple edits in one member are lowered together so the member is parsed/patched once transactionally.

### OPF metadata lowering

Use the same H4 composition model for the package-document member, but only for H7-advertised selected metadata text owners.

Manifest, spine, package attributes and identifier linkage are never lowered from H7 edits.

## Sparse EPUB writer

The H7 archive writer receives an immutable package snapshot, exact source bytes and a mapping of touched member name to verified replacement bytes.

It must:

- reject unknown/additional member names;
- reject member removal or rename;
- preserve member order;
- preserve the `mimetype` first/stored/no-extra-field contract;
- preserve archive comment and supported per-entry ZIP metadata;
- retain each original compression method;
- copy every unchanged member payload byte-for-byte at the uncompressed-content level;
- enforce output size/compression limits;
- write only to an internal candidate buffer until H7 verification completes.

Zero edits write the original EPUB bytes byte-for-byte.

Python ZIP rewriting may recompress unchanged members, so mutated-output fidelity is exact **member-content** preservation plus preserved inventory/order/ZIP metadata evidence, not exact compressed-stream byte identity.

## Candidate verification

After sparse package construction, H7 strictly re-reads the entire candidate before caller output.

### Container invariants

Require:

- valid safe ZIP;
- exact ordered member inventory;
- OCF `mimetype` payload/position/storage/no-extra-field invariant;
- byte-identical `META-INF/container.xml`;
- unchanged rootfile/package-document evidence;
- unchanged supported archive metadata invariants.

### Package graph invariants

Except explicitly requested selected metadata text values, require unchanged:

- package version;
- unique-identifier linkage and identifier value;
- manifest item count/order/IDs/hrefs/resolution/media types/properties/fallbacks;
- spine count/order/idrefs/attributes;
- collections/legacy structural evidence;
- all non-requested OPF lexical-owner evidence required by H4/H7.

### Resource invariants

Require:

- every untouched member has the same uncompressed SHA-256 as source;
- every requested XHTML member preserves XML topology/namespace/owner paths under H4 verification;
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

Mutated output is never reported as `exact-preserve` because ZIP compressed streams may be regenerated.

## Reader acceptance

`EpubIRReader.accepts` accepts:

- `.epub` case-insensitively;
- `application/epub+zip`;
- compatibility MIME aliases already recognized by the one-way converter only when a non-destructive OCF probe confirms an EPUB container.

A generic ZIP is never claimed as EPUB solely because it is a ZIP file. Probing restores the stream position.

## Identity Markdown boundary

EPUB identity Markdown is inspection-only in H7.

The projection may expose selected publication metadata and ordered spine-readable text, but EPUB-derived identity blocks advertise no reversible Markdown edit capability. Direct typed H7 edits are authoritative.

This avoids pretending a flattened Markdown projection can uniquely preserve XHTML owner identity, member identity, OPF ordering or package topology.

## Existing one-way behavior

H7 must not modify:

- `packages/markitdown/src/markitdown/converters/_epub_converter.py`;
- one-way converter registry;
- one-way CLI behavior;
- existing one-way EPUB metadata/spine rendering semantics.

Regression tests lock current one-way behavior around representative EPUBs.

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
- navigation-document mutation;
- encryption/DRM/font-obfuscation mutation;
- digital-signature mutation;
- multiple-package rendition selection;
- remote resource fetching/writeback;
- malformed-publication repair;
- arbitrary whole-member replacement;
- EPUB 2 writable behavior;
- recursive ZIP/container editing outside EPUB semantics.

Recursive generic ZIP remains the next independent v0.6 tranche after exact-green H7.

## Security requirements

Tests cover at minimum:

- ZIP path traversal/absolute/drive/backslash paths;
- duplicate members;
- unsupported compression methods;
- ZIP encryption;
- ZIP bombs/compression-ratio/size limits;
- missing/invalid/misplaced/compressed/extra-field `mimetype`;
- missing/malformed `container.xml`;
- unsafe package-document paths;
- multiple rootfiles writable fail-closed;
- DTD/entity/external-entity surfaces in container/OPF/XHTML;
- non-EPUB3 writable fail-closed;
- duplicate manifest IDs;
- href collisions/path escapes;
- broken/repeated spine references;
- remote resources not fetched;
- forged H7 native evidence;
- stale member/source authority;
- target-member drift;
- H4 failure propagation;
- candidate package-verifier failure with empty caller output.

## Test strategy

Use strict TDD for every production tranche.

Required suites:

1. package snapshot and OCF validation;
2. container/package graph parsing;
3. deterministic EPUB `DocumentIR` and capabilities;
4. selected OPF metadata ownership;
5. XHTML body-text ownership and exclusion boundaries;
6. edit registration/preconditions;
7. H4 lowering and grouped member mutation;
8. sparse archive reconstruction;
9. package-graph candidate verification;
10. target-only preservation/integration;
11. public adapter/imports;
12. identity-Markdown inspection-only behavior;
13. one-way `EpubConverter` regression;
14. malformed/adversarial corpus;
15. standard pre-commit;
16. package tests Python 3.10–3.13;
17. OCR tests Python 3.10–3.13.

Property/fuzz tests target safe path normalization, manifest resolution and parser invariants where bounded deterministic generators are practical.

## Scope audit

The final H6→H7 diff contains only:

- H7 design/implementation documentation;
- `twoways/formats/epub` production code;
- H7 tests/fixtures generated in test code where practical;
- exactly the shared edit-registry additions required for the two H7 edit names;
- bounded shared helpers only if a failing H7 test proves they are necessary and prior-format behavior remains unchanged.

No H1–H6 format production code changes are allowed merely for convenience.

## Completion gate

H7 is complete only when all of these hold on one exact final branch head:

1. H7 lineage starts from the exact-green H6 completion SHA;
2. focused H7 suites are GREEN;
3. full existing package regression is GREEN;
4. one-way EPUB regression is GREEN;
5. standard pre-commit is GREEN;
6. package tests are GREEN on Python 3.10, 3.11, 3.12 and 3.13;
7. OCR tests are GREEN on Python 3.10, 3.11, 3.12 and 3.13;
8. scope audit proves no H1–H6 or one-way EPUB behavior drift;
9. no commit is added after the exact-head gate is satisfied.

After exact-green H7, recursive generic ZIP preservation starts on a new branch from that exact H7 completion point.