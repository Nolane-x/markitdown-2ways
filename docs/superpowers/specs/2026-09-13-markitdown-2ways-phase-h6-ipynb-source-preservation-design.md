# MarkItDown 2Ways Phase H6 IPYNB Source Preservation Design

## Status

Approved execution design for the first v0.6.0 notebook/publication/container tranche. H6 starts from exact-green H5 HTML `f1b7076ba66aa0d15710f262ea1effd3b3192b38` and remains isolated on `phase-h6-ipynb-source-preservation`.

The parent program is `docs/superpowers/specs/2026-09-11-markitdown-2ways-full-parity-program-design.md`. H6 covers IPYNB only. EPUB and recursive ZIP remain separate later tranches.

## Goal

Add deterministic two-way Jupyter Notebook support without using a whole-document notebook serializer as the production write path. H6 exposes direct typed replacement of markdown/code/raw cell source text while preserving notebook JSON structure, notebook metadata, cell metadata, outputs, execution counts, attachments, unrelated source bytes and existing JSON lexical form outside the authorized source-string tokens.

The design prioritizes:

1. no silent corruption;
2. exact source authority and target ownership;
3. target-only source-span mutation;
4. preservation of every unrelated notebook JSON token;
5. candidate re-read at both strict JSON and notebook-semantic layers;
6. unchanged one-way `IpynbConverter` behavior.

## Scope

### Writable in H6

One operation is writable:

- `replace_ipynb_cell_source`

It replaces the logical source text of an existing nbformat-4 cell when all of the following hold:

- cell type is `markdown`, `code` or `raw`;
- `source` is either one JSON string or a non-empty JSON array containing only strings;
- source bytes are reversibly decodable/encodable under the recorded representation;
- the target cell/source locator resolves uniquely;
- the edit passes typed semantic/native/old-value preconditions;
- the logical replacement is not a semantic no-op;
- no notebook or JSON structural mutation is required.

### Read-only / unsupported in H6

H6 does not mutate:

- cell insertion, deletion, reorder or type;
- notebook-level metadata;
- cell metadata;
- cell ids;
- code outputs;
- execution counts;
- markdown attachments;
- kernelspec/language info;
- nbformat/nbformat_minor;
- empty `source: []` arrays, because populating them requires structural array growth;
- unknown cell types;
- nbformat versions other than 4;
- malformed notebook shapes;
- arbitrary JSON values unrelated to cell source.

H6 does not execute code, kernels, JavaScript or notebooks and does not call network or subprocess paths.

## Core architecture

H6 is a notebook-semantic layer over the already exact-green H3 JSON source-preservation engine.

```text
IPYNB source bytes
      |
      +--> H3 reversible text decode + strict JSON lexical ownership
      |
      v
H6 notebook shape validation
      |
      v
DocumentIR: notebook group -> cell groups -> native-source text nodes
      |
      v
replace_ipynb_cell_source edits
      |
      v
H6 source authority + fresh notebook evidence + edit preflight
      |
      v
Deterministic lowering to internal replace_json_scalar edits
      |
      v
H3 patch_json on a fresh shadow JSON IR
      |
      +--> exact JSON scalar span patching
      +--> encoded untouched-byte proof
      +--> strict JSON candidate re-read/topology proof
      |
      v
H6 notebook-semantic candidate re-read
      |
      v
output.write(candidate)
```

H6 must not modify H3 JSON production behavior. It consumes H3 public/internal contracts as an already verified lower layer.

## Source and notebook model

### Strict JSON authority

H6 decodes with the H1/H3 reversible text codec and scans with H3 `scan_json_text`. Duplicate object keys, malformed strings/numbers, non-standard constants and trailing data therefore fail closed before notebook interpretation.

The notebook semantic parser then validates:

- JSON root is an object;
- `nbformat` is an integer and not a boolean;
- `nbformat_minor` is an integer and not a boolean;
- for writable fine-grained H6, `nbformat == 4`;
- `cells` exists and is an array;
- each cell is an object;
- each cell has string `cell_type`;
- each cell has `source` represented as a string or an array of strings.

Invalid nbformat-4 shape is rejected as malformed input. A syntactically valid notebook with `nbformat != 4` is readable only as one document-level read-only native node with reason `ipynb.nbformat.unsupported_version`; it never publishes forged cell locators.

### Representation model

Internal immutable notebook evidence records:

- `nbformat` / `nbformat_minor`;
- notebook top-level non-`cells` digest;
- ordered cells;
- cell index and type;
- optional cell id;
- digest of the cell object excluding `source`;
- source JSON pointer;
- source representation: `string` or `string-array`;
- ordered source-segment JSON pointers;
- ordered source-segment raw digests;
- logical source text (`''.join(segments)` for array form);
- source lexical span.

The non-source digests use deterministic `stable_digest` and exist specifically for candidate verification.

## DocumentIR mapping

One notebook maps to one `Canvas(kind="notebook")`.

### Notebook root

- node kind: `group`
- semantic role: `ipynb-notebook`
- parent: none
- children: ordered cell node ids
- native locator: backend `ipynb`, part `/`, object `notebook`, path `` (root)
- payload/metadata: nbformat, nbformat_minor, cell count and top-level non-cells digest

### Cell node

- node kind: `group`
- semantic role: `ipynb-<cell_type>-cell` for supported types, otherwise `ipynb-cell`
- parent: notebook root
- child: one source node
- native locator: backend `ipynb`, object `cell`, path `/cells/<index>`
- metadata: index, type, optional id, non-source digest

### Cell source node

- node kind: `text`
- payload: `TextPayload(text=<logical source>)`
- semantic role:
  - markdown: `ipynb-markdown-source`
  - code: `code`
  - raw: `ipynb-raw-source`
  - unsupported type: `ipynb-cell-source`
- parent: cell node
- native locator: backend `ipynb`, object `cell-source`, path `/cells/<index>/source`
- provenance char span: exact lexical span of the source JSON value
- metadata includes source representation, segment pointers/raw digests, encoding/BOM/byte-roundtrip and `text.native_source=True`.

`text.native_source=True` is critical: identity Markdown may display the source text but the shared renderer advertises no generic `replace_text` capability. Direct notebook typed edits remain authoritative.

Node ids are deterministic functions of source SHA-256 plus notebook role/index/pointer.

## Capability contract

Add exactly one edit type to `INITIAL_EDIT_TYPES`:

```text
replace_ipynb_cell_source
```

Writable source nodes publish:

```json
{
  "operation": "replace_ipynb_cell_source",
  "state": "writable",
  "reason_code": null,
  "constraints": {
    "identity_markdown": false,
    "source_preservation": "json-scalar-source-segments",
    "structural_edits": false,
    "target_only": true,
    "outputs_preserved": true
  }
}
```

Read-only reason codes include:

- `ipynb.nbformat.unsupported_version`
- `ipynb.cell.unsupported_type`
- `ipynb.cell.source.empty_array_requires_structure`
- `ipynb.encoding.not_roundtrippable`
- `ipynb.cell.structure_read_only`

Malformed notebook shapes fail parsing rather than masquerading as read-only writable evidence.

## Edit contract

`replace_ipynb_cell_source` requires:

- `target_node_id`: an H6 cell-source text node;
- payload exactly `{ "value": <str> }`;
- optional standard `EditPrecondition`.

The writer validates standard semantic/native/old-value preconditions against the H6 text node before any lowering. Duplicate logical targets and semantic no-ops are rejected.

## Deterministic source repartition

Notebook cell `source` may be one string or an array of strings. H6 must never change that representation or array cardinality.

### String source

A logical replacement lowers to one internal H3 scalar replacement at:

```text
/cells/<index>/source
```

### Non-empty string-array source

For an existing array of `N > 0` strings, H6 converts the requested logical text into exactly `N` strings:

1. compute `chunks = value.splitlines(keepends=True)`;
2. for empty text, use `[]` before normalization;
3. if `len(chunks) < N`, pad with empty strings;
4. if `len(chunks) == N`, use them unchanged;
5. if `len(chunks) > N`, keep the first `N-1` chunks and concatenate the remainder into the final segment;
6. if `chunks` is empty, emit `N` empty strings.

The invariant is mandatory:

```text
len(segments) == N
''.join(segments) == requested logical text
```

Only segments whose scalar value actually changes become internal H3 edits. The source array, commas, whitespace and element count remain untouched.

Empty arrays are read-only because no scalar token exists to own a new value.

## Shadow JSON lowering

After H6 source authority and notebook-native evidence pass, the writer builds a fresh H3 JSON IR from the exact source bytes. This shadow document is internal and never replaces the public H6 `DocumentIR`.

Each authorized H6 logical edit lowers to one or more internal `replace_json_scalar` edits targeting the shadow JSON string nodes for the source pointer(s). These internal edits do not need caller-supplied stale preconditions because:

1. H6 already validated caller preconditions against the public notebook node;
2. H6 has already matched source SHA/size and freshly re-read notebook evidence;
3. the shadow JSON IR is constructed immediately from those exact source bytes;
4. H3 independently re-validates that shadow IR against the same bytes before mutation.

H3 remains responsible for scalar rendering, encoding, target-span overlap checks, encoded untouched-byte verification and strict JSON candidate re-read.

H3 writes into an in-memory `BytesIO`, never directly to the caller destination in H6.

## Notebook candidate verification

Before caller output receives any byte, H6 re-reads the H3 candidate through `read_ipynb_ir` using the recorded encoding and requires:

- candidate remains nbformat 4 and structurally valid;
- nbformat and nbformat_minor unchanged;
- notebook top-level non-cells digest unchanged;
- cell count and ordering unchanged;
- every cell type and id unchanged;
- every cell non-source digest unchanged;
- every source representation (`string` vs `string-array`) unchanged;
- every source-array cardinality unchanged;
- every requested logical source equals its requested value;
- every unrequested logical source is unchanged;
- every unrequested source segment raw digest is unchanged.

This notebook-semantic verifier complements H3. It does not weaken or replace H3 JSON lexical/topology/byte verification.

Only after both layers pass does H6 call `output.write(candidate)`.

## Zero-edit identity

With no edits, H6 writes the exact input bytes and returns exact-preserve fidelity evidence. It does not parse/serialize/re-encode the source for output.

Source SHA-256 and byte size are still checked before zero-edit emission.

## Fidelity evidence

Zero-edit results include:

- `ipynb.source_authority`
- `ipynb.zero_edit_identity`

Mutating results include:

- `ipynb.source_authority`
- `ipynb.native_evidence`
- `ipynb.json_scalar_lowering`
- `ipynb.untouched_bytes`
- `ipynb.candidate_reread`

Mutating H6 claims `high` fidelity because target source-array segment distribution may change while logical cell source and every unrelated byte remain protected.

## Public surface

Package:

```text
markitdown.twoways.formats.ipynb
```

Public names:

- `IpynbIRReader`
- `IpynbPatchWriter`
- `read_ipynb_ir`
- `patch_ipynb`

Reader acceptance:

- `.ipynb`;
- `application/x-ipynb+json`;
- `application/json` only when a non-destructive probe identifies notebook shape.

Writer acceptance requires `document.source.format == "ipynb"` and target format `ipynb` or extension `.ipynb`.

The writer requires `source_stream=` and `edits=` and rejects unknown options.

## Markdown boundary

Identity Markdown is inspection-only in H6.

Cell-source text nodes are visible through the generic text renderer, but `text.native_source=True` forces `editable_capabilities == ()`. The identity importer may round-trip an unchanged projection but must not manufacture generic `replace_text` edits for notebook source.

H6 does not introduce notebook-specific Markdown import syntax in this tranche.

## One-way compatibility

`packages/markitdown/src/markitdown/converters/_ipynb_converter.py` is protected and must not be modified.

Regression tests lock current one-way behavior for:

- `.ipynb` acceptance;
- JSON MIME notebook probing;
- markdown/code/raw cell conversion;
- title extraction behavior.

H6 is additive only to the two-way namespace.

## Failure model

H6 fails closed with existing 2Ways error families plus an internal notebook parse error translated at reader/writer boundaries.

Examples:

- changed source SHA/size -> `SourcePackageMismatchError`;
- forged H6 IR/native evidence -> `PatchPreconditionError`;
- stale caller precondition -> `PatchPreconditionError`;
- read-only source representation/type -> `UnsupportedEditError`;
- duplicate/no-op/invalid payload -> `UnsupportedEditError`;
- H3 lowering or untouched-byte proof failure -> existing H3 error propagated;
- candidate notebook semantic drift -> `RoundTripVerificationError`.

No failure after preflight may leave partial caller output.

## Testing strategy

H6 follows full TDD and exact-head gating.

Required tests cover:

- deterministic nbformat-4 IR;
- strict malformed shape rejection;
- unsupported nbformat read-only fallback;
- string source and list-of-strings source;
- empty source-array read-only boundary;
- unknown cell type read-only boundary;
- reversible/non-roundtrippable representation behavior;
- reader accepts/probe behavior;
- source authority mismatch;
- forged root/cell/source metadata and topology;
- stale semantic/native/old-value preconditions;
- payload/type/target/duplicate/no-op rejection;
- deterministic repartition for 1/N/fewer/more/empty line chunks;
- multi-cell edits;
- outputs/metadata/execution counts/attachments byte preservation;
- candidate requested-source mismatch fault injection;
- candidate non-source drift fault injection;
- zero-edit byte identity;
- identity Markdown inspection-only;
- public imports/adapter behavior;
- unchanged one-way IPYNB converter behavior;
- full package + OCR Python 3.10-3.13 regression;
- standard pre-commit.

## Completion gate

H6 is complete only when one exact final H6 branch head passes:

1. standard pre-commit;
2. package tests Python 3.10;
3. package tests Python 3.11;
4. package tests Python 3.12;
5. package tests Python 3.13;
6. OCR tests Python 3.10;
7. OCR tests Python 3.11;
8. OCR tests Python 3.12;
9. OCR tests Python 3.13.

No status-only commit is added after that exact-green head. EPUB and recursive ZIP work begin only on later branches.