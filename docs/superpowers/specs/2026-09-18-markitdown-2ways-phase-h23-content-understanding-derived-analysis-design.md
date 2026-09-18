# MarkItDown 2Ways Phase H23 — Azure Content Understanding derived-analysis parity

Date: 2026-09-18
Status: frozen design
Base: `main@b4d926d153f54b4db15989310311a907131bf895`

## Purpose

H23 closes the remaining Class-D Azure Content Understanding input-parity gap identified
by the full-parity program. It does this without turning MarkItDown 2Ways into a Content
Understanding client.

The caller supplies:

1. the exact source bytes that were analyzed; and
2. a caller-materialized `ContentUnderstandingAnalysisSnapshot` containing the exact
   string produced by the one-way converter's `to_llm_input(result)` stage plus the
   analyzer/content-type descriptors that were used.

H23 never constructs `ContentUnderstandingClient`, resolves Azure credentials, submits
analysis, polls, retries, sleeps, resolves DNS, opens sockets, calls analyzer metadata
APIs, or invokes `to_llm_input()` in production.

## Protected one-way authority

The protected converter is:

- file: `packages/markitdown/src/markitdown/converters/_cu_converter.py`
- Git blob at H23 base: `230e3d86bf533241b68dfc3d023e48b3effdc788`
- converter: `ContentUnderstandingConverter`

Default one-way semantics relevant to H23 are:

- every `ContentUnderstandingFileType` is accepted by default;
- extension routing takes precedence over MIME routing;
- MIME parameters are stripped and aliases are canonicalized;
- default analyzer selection is modality-based:
  - document -> `prebuilt-documentSearch`
  - image -> `prebuilt-documentSearch`
  - video -> `prebuilt-videoSearch`
  - audio -> `prebuilt-audioSearch`
- content type is derived from the resolved file type, preserving a supplied MIME subtype
  only when it is consistent with that file type;
- visible one-way Markdown is exactly `to_llm_input(result)`.

H23 protects these semantics but does not import this converter in its production module.

## Scope: default auto-routing only

H23 proves parity for the default converter path where no custom `analyzer_id` is
configured.

Custom analyzers remain outside H23 because determining their base modality may require
the one-way converter to call `get_analyzer()`, which is a remote SDK operation. H23
must not accept a caller assertion as if it were independently verified native authority.

The default accepted extension surface is:

- documents: PDF, DOCX, PPTX, XLSX, HTML, TXT, MD, RTF, XML;
- email: EML, MSG;
- images: JPG/JPEG/JPE, PNG, BMP, TIFF, HEIF/HEIC;
- video: MP4, M4V, MOV, AVI, MKV, WEBM, FLV, WMV;
- audio: WAV, MP3, M4A, FLAC, OGG, AAC, WMA.

Equivalent one-way MIME routing is mirrored, including the current aliases.

## Analysis snapshot contract

H23 introduces `ContentUnderstandingAnalysisSnapshot` with:

- `content: str` — exact caller-materialized `to_llm_input(result)` output;
- `provider: str` — non-empty materialization identity;
- `analyzer_id: str` — must equal H23's independently derived default analyzer;
- `content_type: str` — must equal H23's independently derived canonical payload type;
- optional `api_version: str`;
- optional `analysis_id: str`.

The content may be empty. No Azure SDK result object, credential, endpoint token, client,
poller, or analyzer metadata object is accepted.

## Independent routing authority

The H23 production reader owns a frozen pure-Python routing table matching the current
one-way default surface. It independently computes:

- resolved file type;
- modality;
- expected default analyzer;
- canonical content type.

The snapshot is rejected unless its `analyzer_id` and `content_type` exactly match
those independently computed values.

A regression court compares H23 routing against the unchanged one-way converter helpers
for the complete default surface and common MIME-conflict cases. The converter Git blob
is frozen so an upstream semantic change cannot silently invalidate the duplicated table.

## Derived projection

H23 performs no semantic transformation of `snapshot.content`. Visible Markdown is the
exact supplied `to_llm_input` output.

Source identity and analysis identity are separate authorities. Changing either exact
source bytes or analysis content/descriptors changes deterministic document identity.

## Capability boundary

The sole root is a text node with no native locator.

`replace_text` is `CapabilityState.DERIVED` with reason
`analysis.output.not_native_writable` and constraints:

- `identity_markdown=False`
- `remote_writeback=False`
- `native_owner=False`
- `materialization="explicit-local-only"`

No CU writer, native mutation operation, remote writeback API, or identity-Markdown
writeback path is added.

## Provenance envelope

H23 records `twoways.content_understanding_analysis.v1` including:

- source SHA-256 and byte size;
- filename/MIME/extension when supplied;
- resolved file type and modality;
- verified analyzer ID and canonical content type;
- analysis provider;
- optional API version and analysis ID;
- exact analysis-content SHA-256 and UTF-8 size;
- converter identity and frozen Git blob;
- `network_performed_by_twoways=False`;
- `azure_sdk_used_by_twoways=False`;
- `credentials_used_by_twoways=False`;
- `to_llm_input_called_by_twoways=False`.

## Resource budgets

`ContentUnderstandingDerivedLimits` independently bounds:

- source bytes;
- materialized analysis UTF-8 bytes.

Source capture uses bounded reads of at most 64 KiB. Limits must be positive integers;
booleans and non-integers fail closed.

## Dependency and import discipline

The production reader must not import or reference executable dependency paths for:

- `azure.ai.contentunderstanding`
- `azure.identity`
- `azure.core.credentials`
- requests/httpx/urllib network clients
- socket
- subprocess
- sleep/retry machinery

Importing `markitdown.twoways` must remain independent of the Azure CU SDK.

## Required courts

H23 completion requires:

1. complete default extension acceptance parity;
2. representative and alias MIME acceptance parity;
3. extension-over-MIME conflict routing parity;
4. file type -> modality -> default analyzer parity;
5. canonical content-type parity;
6. exact materialized Markdown preservation;
7. independent source/analysis deterministic identity;
8. source and analysis budgets with exact-boundary behavior;
9. bounded source reads;
10. invalid descriptor fail-closed behavior;
11. DERIVED/no-native capability state;
12. canonical serialization determinism;
13. public read-only exports with no writer symbols;
14. production Azure/network/process import firewall;
15. frozen `_cu_converter.py` Git blob;
16. offline differential conversion using an in-memory fake client and patched
    `to_llm_input`.

## Closure rule

The exact final H23 head must pass:

- pre-commit;
- package Python 3.10, 3.11, 3.12, 3.13;
- OCR Python 3.10, 3.11, 3.12, 3.13.

Only after exact 9/9 GREEN may H23 freeze head/tree, prove a two-parent synthetic merge
against the exact H23 base, verify tree equality, mark the PR ready, perform an
expected-head guarded merge, and re-verify main plus the protected converter blob.
