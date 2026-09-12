# MarkItDown 2Ways Phase H1 Text Source Preservation Design

## Status

Execution design for the first v0.5.0 tranche, derived from the approved `2026-09-11-markitdown-2ways-full-parity-program-design.md`. This tranche is intentionally limited to native plain-text and Markdown files. CSV, JSON, XML and HTML remain follow-on tranches after the textual preservation substrate is proven.

## Goal

Add deterministic two-way support for authoritative textual source files without weakening the project’s preservation contract. A supported source must round-trip through `DocumentIR`, advertise direct `replace_text` only when source representation can be reproduced safely, apply edits transactionally against the original bytes, and verify the written result by reopening it.

## Non-goals

- no generic document framework;
- no arbitrary source-span editing API in H1;
- no CSV/JSON/XML/HTML structured mutation yet;
- no automatic charset transcoding;
- no automatic line-ending normalization across ambiguous mixed-newline files;
- no lossy fallback writer;
- no lossless raw-source identity-Markdown editing protocol in H1;
- no changes to the existing one-way `MarkItDown` converter API or CLI;
- no network, subprocess, database or editor features.

## Public surface

Create `markitdown.twoways.formats.text` with the same focused public pattern used by the other native adapters:

- `read_text_ir(source, *, filename=None, mimetype=None, encoding=None) -> DocumentIR`
- `patch_text(document, source, destination, *, edits=()) -> WriterResult`
- `TextIRReader`
- `TextPatchWriter`
- `TextRepresentation`
- `decode_text_source`
- `encode_text_source`
- `normalize_newlines`

The reader represents one authoritative source file as one `Canvas(kind="text")` containing one `Node(kind="text", semantic_role="document-body")` with a `TextPayload` carrying the exact decoded text. Plain text and Markdown use the same native textual adapter because source bytes, not Markdown syntax, are authoritative in H1.

## Source representation contract

The reader records source SHA-256 and size in `SourceDescriptor`, and records deterministic text representation metadata on the root text node:

- `text.encoding`: canonical Python codec name used for payload bytes after any BOM;
- `text.bom`: stable symbolic BOM name or `none`;
- `text.newline`: `lf`, `crlf`, `cr`, `none`, or `mixed`;
- `text.byte_roundtrip`: whether decode then encode recreates the payload bytes exactly;
- `text.format`: `text` or `markdown`;
- `text.native_source`: `true`, marking the text payload as authoritative lexical source rather than semantic text reconstructed from another native format.

The native locator uses `backend="text"`, `part_uri="/"`, `object_id="document-body"`.

### Encoding resolution

1. Explicit `encoding=` is validated by strict decoding and exact re-encoding.
2. Known Unicode BOMs are authoritative and removed before strict decode while being preserved separately for writeback.
3. Without an explicit encoding or BOM, strict UTF-8 is attempted first.
4. A non-UTF-8 fallback may use `charset-normalizer`, but it is writable only if strict re-encoding with the resolved codec recreates the original payload bytes exactly.
5. If no exact reversible decoding exists, the reader may still fail closed rather than manufacture semantic text.

The writer never silently changes encoding. If edited text cannot be encoded in the recorded source encoding, the edit is rejected before any destination bytes are returned.

### BOM preservation

A detected BOM is stored separately from the decoded text and reproduced byte-for-byte before encoded payload bytes. No edit operation may add, remove or change the BOM in H1.

### Newline preservation

Newline classification is performed on decoded source text without universal-newline normalization. A source containing only LF, only CRLF, only CR, or no newline is directly writable when all other conditions hold. Mixed newline conventions are readable but `replace_text` is read-only with `text.newline.mixed` because whole-document replacement cannot prove where each original convention should survive.

For writable sources, replacement text is canonicalized only at the line-separator boundary: logical CRLF/CR/LF sequences in the requested replacement are converted to the source convention before encoding. Files with `newline=none` accept replacement text only when it contains no line break; otherwise the edit fails closed rather than selecting a convention that did not exist in the source.

## Capability contract

The root text node advertises exactly one H1 native mutation capability: `replace_text`.

Writable constraints include:

```json
{
  "source_preservation": "encoding-bom-newline",
  "identity_markdown": false,
  "whole_document": true
}
```

`identity_markdown=false` is deliberate. The existing identity-Markdown text importer is semantic-text oriented: it normalizes whitespace and interprets supported inline Markdown formatting. Those semantics are correct for Office-derived text but are not a proof-preserving edit channel for lexical `.txt` or `.md` source. Native text remains directly writable through typed `EditOperation` objects, while identity-Markdown projections of `text.native_source=true` nodes remain read-only until a dedicated raw-source lossless protocol exists.

Read-only reason codes for the direct native writer include:

- `text.encoding.not_roundtrippable`
- `text.newline.mixed`

Unknown operations remain read-only through the capability kernel.

## Edit contract

H1 reuses the existing `EditOperation(type="replace_text")`; no new edit type or schema-version bump is needed.

The payload is exactly:

```json
{"text": "replacement text"}
```

Unknown payload keys, non-string values, wrong target nodes, missing capabilities, duplicate `replace_text` edits targeting the same node, or edits targeting non-text nodes are rejected during preflight.

Existing `EditPrecondition` checks remain authoritative. Writers validate semantic digest, native-locator digest and expected old value before mutation. The source bytes passed to the writer must match `document.source.sha256` and `size_bytes`.

## Transactional writer

`TextPatchWriter` follows the existing format-writer contract:

1. read source bytes fully;
2. verify source identity against `DocumentIR`;
3. preflight the complete edit set without producing destination bytes;
4. validate node capability, authoritative text locator and edit preconditions;
5. revalidate source representation against the original bytes;
6. compute the exact replacement text under the preserved newline convention;
7. encode strictly with the recorded codec and prepend the original BOM;
8. reopen the candidate bytes with the text reader;
9. verify semantic text equals the requested normalized result;
10. verify format, encoding, BOM and newline metadata remain within the H1 contract;
11. write destination only after verification succeeds.

With zero edits, `patch_text` writes the original source bytes unchanged. A semantic no-op replacement also returns the original bytes unchanged rather than re-encoding them.

## Markdown integration boundary

H1 does not add a second Markdown parser. Native `.md`/`.markdown` files are authoritative lexical text sources; their exact decoded bytes become the text-node semantics and can be changed through direct typed `replace_text` operations.

The existing clean/identity Markdown projection machinery may still render a native source node for inspection, but identity projection must publish no editable capability for `text.native_source=true`. Unchanged identity projection/import is allowed and produces no edit. Edited native-source blocks fail closed as read-only instead of passing through the semantic text parser and silently normalizing source syntax or whitespace.

A later tranche may add a dedicated raw-source identity protocol only if it can preserve arbitrary Markdown/plain-text characters, marker-like content, trailing spaces, repeated blank lines and other lexical details without guessing.

## Verification requirements

Focused tests must prove:

- deterministic IR for repeated reads;
- UTF-8, UTF-8 BOM and a reversible non-UTF-8 source retain encoding representation;
- LF/CRLF/CR conventions are preserved;
- mixed-newline source is readable but direct `replace_text` is read-only;
- no-op output is byte-identical;
- one valid direct replacement changes only authoritative text bytes while preserving BOM/encoding/newline policy;
- stale source digest, stale semantic old value and forged locator fail before destination output;
- duplicate/unknown/malformed edits fail closed;
- unencodable replacement fails closed;
- re-read verification catches mismatched output representation;
- native Markdown follows the same source-preservation contract;
- native plain-text/Markdown identity projection advertises no editable capability;
- unchanged native-source identity projection imports to zero edits;
- public imports are stable;
- existing full suite and Python 3.10–3.13 CI remain green.

## Follow-on boundary

Phase H2 may reuse only the proven low-level encoding/BOM/newline helpers. CSV must add dialect/quoting/source-span proof rather than route through whole-document text replacement. JSON/XML/HTML must add syntax-aware lexical/subtree locators and must not pretty-print or serialize unrelated content merely because parsing succeeded.
