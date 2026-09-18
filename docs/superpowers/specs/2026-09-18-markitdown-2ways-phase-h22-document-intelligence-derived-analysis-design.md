# MarkItDown 2Ways Phase H22 — Azure Document Intelligence derived-analysis snapshot parity

Date: 2026-09-18
Status: frozen design
Base: `main@dfd340565f6cf6df850e89dc60f8688d98d6848a`

## Purpose

H22 extends the v0.9 Class-D derived-content program to the existing one-way
`DocumentIntelligenceConverter` without turning MarkItDown 2Ways into an Azure client.

The caller supplies two already-materialized authorities:

1. the exact source bytes that were analyzed; and
2. an explicit analysis snapshot containing the Azure-produced Markdown content plus
   descriptive analysis metadata.

2Ways does not authenticate, construct an Azure client, submit a document, poll an
operation, retry, sleep, resolve DNS, open sockets, or infer remote service availability.
It only binds the supplied evidence into deterministic `DocumentIR`.

## Existing one-way authority

The protected one-way converter is:

- file: `packages/markitdown/src/markitdown/converters/_doc_intel_converter.py`
- Git blob at H22 base: `f8a5c8e8c82638fc5186105679ff1af0175992c8`
- converter: `DocumentIntelligenceConverter`
- model requested by that converter: `prebuilt-layout`
- output content format: `markdown`
- final semantic transform: remove HTML comments with
  `re.sub(r"<!--.*?-->", "", result.content, flags=re.DOTALL)`

H22 must not edit this converter. A regression court freezes the blob and independently
checks H22's local projection against the converter with an in-memory fake Azure client.

## Source ownership boundary

H22 mirrors the *default* file-type surface of `DocumentIntelligenceConverter`:

- DOCX
- PPTX
- XLSX
- PDF
- JPEG
- PNG
- BMP
- TIFF

HTML is intentionally not included because it exists in the enum/helpers but is not in
the converter's default `file_types` constructor argument.

Ownership is accepted by extension or MIME prefix exactly in the same broad style as the
one-way converter. H22 does not claim that the bytes are structurally valid for that
format; the snapshot is derived analysis evidence, not native format authority. Native
DOCX/PPTX/XLSX/PDF/PNG/JPEG authorities remain owned by their existing 2Ways readers.

## Analysis snapshot contract

H22 introduces `DocumentIntelligenceAnalysisSnapshot` with:

- `content: str` — the already-materialized Document Intelligence content;
- `provider: str` — non-empty caller/provider identity;
- `model_id: str` — must be `prebuilt-layout` for H22 parity;
- `content_format: str` — must be `markdown`;
- optional `api_version: str`;
- optional `analysis_id: str`.

No credential, token, API key, SDK client, poller, endpoint secret, or live result object
is accepted. The contract is intentionally serializable and detached from the Azure SDK.

The analysis content may be empty because the one-way converter can legitimately return
empty Markdown for a blank analysis result. H22 binds the exact UTF-8 bytes and digest.

## Deterministic derived projection

H22 computes visible Markdown only by applying the one-way converter's final local
comment-removal transform to the supplied analysis content. It performs no additional
normalization.

The deterministic document identity binds:

- source SHA-256;
- source size and accepted stream identity;
- analysis-content SHA-256;
- provider/model/content-format/api-version/analysis-id descriptors;
- derived Markdown SHA-256;
- protected one-way converter identity.

Changing either source bytes or analysis evidence changes document identity.

## Capability boundary

The sole semantic root is a text node with no native locator.

`replace_text` is `CapabilityState.DERIVED` with reason
`analysis.output.not_native_writable`.

Constraints state:

- `identity_markdown=False`
- `remote_writeback=False`
- `native_owner=False`
- `materialization="explicit-local-only"`

No writer, edit operation, remote writeback API, Azure mutation API, or identity-Markdown
writeback path is added.

## Provenance envelope

H22 records `twoways.document_intelligence_analysis.v1` including:

- source SHA-256 and byte size;
- filename, MIME and extension when supplied;
- analysis provider/model/content format;
- optional API version and analysis ID;
- exact analysis-content SHA-256 and UTF-8 size;
- derived Markdown SHA-256 and UTF-8 size;
- converter name and frozen Git blob;
- `network_performed_by_twoways=False`;
- `azure_sdk_used_by_twoways=False`;
- `credentials_used_by_twoways=False`.

The source descriptor binds the caller-supplied source bytes. The analysis snapshot is
separate provenance and never masquerades as native source ownership.

## Resource budgets

`DocumentIntelligenceDerivedLimits` independently bounds:

- source bytes;
- analysis-content UTF-8 bytes;
- derived Markdown UTF-8 bytes.

Source capture uses bounded reads only. All limits are positive integers; booleans and
non-integers fail closed. Exact boundary sizes are accepted and one byte over is rejected.

## Import and dependency discipline

Importing `markitdown.twoways` must not import Azure SDK modules. The H22 production
reader contains no imports or calls for:

- `azure.ai.documentintelligence`
- `azure.identity`
- `azure.core.credentials`
- requests/httpx/urllib network clients
- socket
- subprocess
- sleep/retry machinery

The existing one-way converter remains optional and is imported only by the dedicated
regression tests.

## Failure model

H22 fails closed before producing a document when:

- analysis is not `DocumentIntelligenceAnalysisSnapshot`;
- provider/model/content-format authority is invalid;
- optional metadata is blank when present;
- source stream returns non-bytes;
- source exceeds its budget;
- analysis content exceeds its UTF-8 budget;
- derived Markdown exceeds its UTF-8 budget;
- StreamInfo is outside the default one-way converter file-type surface.

No partial writer output exists because H22 has no writer.

## Required tests

H22 completion requires courts for:

1. default converter StreamInfo ownership parity;
2. exact source and analysis evidence binding;
3. comment-removal semantic parity;
4. deterministic repeated reads and canonical JSON round-trip;
5. derived/no-native capability state;
6. source/analysis/Markdown exact-boundary budgets;
7. bounded source reads;
8. invalid snapshot metadata;
9. import/network/Azure-SDK firewall;
10. public read-only exports with no writer symbols;
11. frozen `_doc_intel_converter.py` Git blob;
12. offline differential parity against the unchanged one-way converter.

## Closure rule

H22 is complete only when the exact final branch head passes:

- pre-commit;
- package tests on Python 3.10, 3.11, 3.12 and 3.13;
- OCR tests on Python 3.10, 3.11, 3.12 and 3.13.

That is the repository's exact 9/9 gate. After GREEN, freeze head/tree, prove a synthetic
merge against the exact H22 base, verify tree equality, then perform a guarded exact-head
merge and re-verify `main` plus the protected converter blob.
