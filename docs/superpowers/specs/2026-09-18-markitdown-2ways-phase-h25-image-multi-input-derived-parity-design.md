# MarkItDown 2Ways Phase H25 — ImageConverter multi-input derived parity

Date: 2026-09-18
Status: frozen design
Base: `main@68cf686404328158b8e87e8ff00ad0c03734157e`

## Purpose

H25 closes the one-way `ImageConverter` derived-semantic parity gap without weakening
the native PNG/JPEG mutation boundaries already proven by H12-H14.

The caller supplies the exact source image bytes plus zero, one, or both explicit
materializations:

1. `ImageMetadataSnapshot` — selected ExifTool values already materialized by the caller;
2. `ImageDescriptionSnapshot` — an already materialized multimodal-model description.

2Ways reconstructs the exact visible Markdown that the unchanged one-way ImageConverter
would produce from those materializations. Production H25 performs no ExifTool process,
no LLM/API request, no image upload, no network action and no remote writeback.

## Protected one-way authority

Protected file:
`packages/markitdown/src/markitdown/converters/_image_converter.py`

Frozen Git blob at H25 base:
`cd49b96d29f50861625cecfb6cee7bdd1eb30b54`

H25 must not modify that file.

The one-way converter currently accepts:

- extensions: `.jpg`, `.jpeg`, `.png`;
- MIME prefixes: `image/jpeg`, `image/png`.

Extension acceptance precedes MIME acceptance.

## Metadata projection

The one-way converter emits only these metadata fields and always in this order:

1. ImageSize
2. Title
3. Caption
4. Description
5. Keywords
6. Artist
7. Author
8. DateTimeOriginal
9. CreateDate
10. GPSPosition

Each present field is rendered exactly as:

`<field>: <string-value>\n`

H25 accepts only those keys. Values are explicit strings representing the caller's
already-materialized post-stringification value. Unknown metadata keys fail closed rather
than being silently ignored.

Metadata is provenance only. Even when a line corresponds to a native PNG/JPEG metadata
field, it never grants H25 a native locator or writer. H12-H14 remain authoritative.

## LLM description projection

If a description snapshot exists, H25 appends exactly:

`\n# Description:\n` + `description.content.strip()` + `\n`

The snapshot binds:

- exact raw description content;
- provider;
- model;
- effective prompt;
- optional materialization ID;
- independently derived image content type.

The effective default prompt is:

`Write a detailed caption for this image.`

H25 does not call a model and does not reproduce an OpenAI-compatible request. It only
records enough evidence to prove how the caller materialization relates to current
ImageConverter semantics.

## Image content-type authority

For an LLM-description snapshot H25 independently derives the content type exactly like
the current one-way converter:

1. use `stream_info.mimetype` verbatim when non-empty;
2. otherwise use Python `mimetypes.guess_type("_dummy" + extension)`;
3. otherwise use `application/octet-stream`.

The supplied description snapshot content type must equal that derived value.

This content-type rule is separate from the converter's acceptance check, which lowercases
extension/MIME only for acceptance.

## Deterministic identity

Document identity binds independently:

- source SHA-256 and size;
- filename, MIME, extension and URI;
- acceptance authority (extension or MIME);
- ordered metadata snapshot digest;
- raw description digest and stripped-output digest;
- description provider/model/prompt/content type/materialization ID;
- final Markdown SHA-256;
- protected converter identity.

Changing source, metadata, description, routing descriptors or final Markdown changes
document identity.

## Capability boundary

H25 creates one derived text root with no native locator.

`replace_text` is `CapabilityState.DERIVED` with reason
`image.output.not_native_writable`.

Constraints:

- `identity_markdown=False`
- `native_owner=False`
- `remote_writeback=False`
- `materialization="explicit-local-only"`

No H25 writer exists.

## Provenance envelope

H25 records `twoways.image_converter_snapshot.v1` with:

- source SHA-256/size and StreamInfo descriptors;
- accepted-by authority;
- metadata field count and ordered metadata digest;
- raw/stripped description digests and UTF-8 sizes when present;
- provider/model/effective prompt/content type/materialization ID when present;
- final Markdown SHA-256/size;
- converter identity/blob;
- `exiftool_executed_by_twoways=False`;
- `llm_called_by_twoways=False`;
- `network_performed_by_twoways=False`;
- `subprocess_performed_by_twoways=False`.

## Resource budgets

`ImageDerivedLimits` independently bounds:

- source bytes;
- aggregate metadata UTF-8 bytes;
- raw description UTF-8 bytes;
- final Markdown UTF-8 bytes.

Source reads are bounded to <=64 KiB. Limits are positive integers; booleans and
non-integers fail closed. Exact boundary values pass and one byte over fails.

## Dependency discipline

Production H25 must not import or invoke:

- `exiftool_metadata`;
- `subprocess`;
- OpenAI/LLM clients;
- requests/httpx/urllib network clients;
- socket;
- browser/process/retry/sleep machinery.

Importing `markitdown.twoways` must remain independent from these optional/runtime paths.

## Required courts

H25 completion requires courts for:

1. exact accepted extension/MIME surface and precedence;
2. exact metadata field order and formatting;
3. unknown metadata-key rejection;
4. metadata-only, description-only, combined and empty projections;
5. description `.strip()` semantics;
6. independent description content-type derivation;
7. default/effective prompt provenance;
8. independent source/metadata/description identity;
9. exact resource-boundary behavior;
10. bounded source reads;
11. DERIVED/no-native capabilities;
12. deterministic canonical serialization;
13. public read-only exports and absence of writer symbols;
14. production ExifTool/LLM/network/process firewall;
15. frozen ImageConverter blob;
16. offline differential parity by monkeypatching the unchanged one-way converter's
    ExifTool and description materializations.

## Closure

The exact final H25 head must pass the repository's 9/9 gate:

- pre-commit;
- package tests on Python 3.10, 3.11, 3.12, 3.13;
- OCR tests on Python 3.10, 3.11, 3.12, 3.13.

Only then freeze head/tree, prove exact synthetic merge tree equality against the frozen
base, mark the PR ready, merge with expected-head guard and verify post-merge main plus
the protected ImageConverter blob.
