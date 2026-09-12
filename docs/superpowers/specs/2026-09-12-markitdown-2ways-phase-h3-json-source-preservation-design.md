# MarkItDown 2Ways Phase H3 JSON Source Preservation Design

## Status

Execution design for the JSON tranche of v0.5.0, stacked only on exact-head-green H2 CSV (`1824ec26945af2aa924b8fe9699d70ae711187ee`). H3 is deliberately limited to replacing existing JSON scalar values. Object/array structure, object keys, member ordering and all unrelated lexical source remain immutable.

## Goal

Add deterministic two-way JSON support that can safely replace an existing scalar token while preserving every byte outside authorized target spans. Parsing is never treated as proof of write safety: the reader must bind each value to an unambiguous JSON Pointer and exact lexical span, the writer must revalidate those bindings against the original bytes, and candidate output must pass untouched-byte and strict semantic re-read verification before destination emission.

## Non-goals

- no whole-document `json.dumps`/pretty-print writer;
- no object member insertion/deletion/reordering;
- no object-key rename;
- no array insertion/deletion/reordering;
- no object/array replacement through a scalar edit;
- no JSON Patch/merge-patch engine in H3;
- no comments, trailing commas, single-quoted strings, NaN/Infinity or JSON5 extensions;
- no duplicate object keys: they make JSON Pointer ownership ambiguous and fail closed;
- no editable identity-Markdown bridge in H3;
- no change to one-way `PlainTextConverter`, `MarkItDown` API or CLI.

## Public surface

Create `markitdown.twoways.formats.json`:

- `read_json_ir(source, *, filename=None, mimetype=None, encoding=None) -> DocumentIR`
- `patch_json(document, source, destination, *, edits=()) -> WriterResult`
- `JsonIRReader`
- `JsonPatchWriter`
- lexical parser/model helpers remain internal except where focused tests require direct access.

H3 accepts `.json`, `application/json`, and `text/json`. JSONL/NDJSON is not H3 JSON because it is a sequence of independent JSON texts and requires its own ownership contract.

## Lexical model

The decoded JSON source is parsed with a strict recursive-descent lexical parser. Every JSON value records:

- RFC 6901 JSON Pointer (`""` for root);
- value kind: `object`, `array`, `string`, `number`, `boolean`, `null`;
- exact character `[start, end)` span of the complete value token/subtree;
- exact raw lexical text and SHA-256 raw digest;
- parent pointer and ordered child pointers;
- scalar semantic payload where lossless in existing IR JSON-compatible types.

Object key strings are decoded strictly for pointer construction but are not writable H3 nodes. Pointer escaping uses `~0` and `~1`. Duplicate decoded keys in one object fail with `json.object.duplicate_key_ambiguous`; this prevents two native values from sharing one semantic pointer.

The parser accepts only JSON whitespace (space, tab, CR, LF), strict double-quoted strings/escapes, strict JSON number grammar and exact `true`/`false`/`null` literals. It validates the complete text and cross-checks acceptance with Python's strict JSON decoder configured to reject non-standard constants and duplicate keys.

## IR mapping

One JSON file maps to one `Canvas(kind="json")`. Every lexical value maps to one `Node(kind="unknown_native")` so generic Markdown projection never invents editable text semantics.

Container nodes use semantic roles `json-object` or `json-array`, ordered `children`, and mapping payloads describing only native JSON type/size. Scalar nodes use semantic roles `json-string`, `json-number`, `json-boolean`, `json-null` and mapping payloads:

- string: `{"json_type": "string", "value": <decoded string>}`;
- number: `{"json_type": "number", "raw": <exact number token>}`;
- boolean: `{"json_type": "boolean", "value": true|false}`;
- null: `{"json_type": "null", "value": null}`.

Node IDs are deterministic from source SHA-256 + pointer and remain path-stable across scalar type changes. Native locator uses `backend="json"`, `part_uri="/"`, `object_id="value"`, `path=<JSON Pointer>`. Provenance `char_span` binds the exact lexical value span.

Node metadata records `json.pointer`, `json.kind`, `json.char_start`, `json.char_end`, `json.raw_digest`, source encoding/BOM proof and `json.native_source=true`.

## Capability contract

Container nodes advertise `replace_json_scalar` as read-only with `json.container.structural_edit_unsupported`.

Scalar nodes advertise `replace_json_scalar` as writable only when source decoding is byte-roundtrippable. Writable constraints:

```json
{
  "identity_markdown": false,
  "source_preservation": "lexical-value-span",
  "structural_edits": false,
  "target_only": true
}
```

Non-roundtrippable source representation is read-only with `json.encoding.not_roundtrippable`.

## Edit contract

Register one H3 operation:

```text
replace_json_scalar
```

Payload is exactly:

```json
{"value": <string | number | boolean | null>}
```

Mappings/lists are rejected because they are structural values. Booleans are kept distinct from integers. Floats must be finite. Existing edit preconditions remain authoritative, and the writer independently revalidates source digest/size, native pointer/span/raw digest and current scalar token before rendering any candidate.

A replacement that is semantically equal to the existing scalar is rejected as a no-op even if it would change lexical spelling (for example `1e2` to `100`). H3 is a semantic scalar editor, not a lexical cosmetics editor.

## Target scalar rendering

Using the standard JSON serializer is permitted only for one requested scalar token, never for a container or complete document:

- strings are JSON-escaped as one target token;
- integers are emitted exactly from the requested integer;
- finite floats use strict standard JSON scalar rendering with `allow_nan=false`;
- booleans emit `true`/`false`;
- null emits `null`.

The resulting target token is parsed independently before insertion. If its characters cannot be encoded in the source representation, mutation fails before destination output.

## Transactional writer

`JsonPatchWriter`:

1. validates `DocumentIR`;
2. reads source bytes and verifies SHA-256/size;
3. re-decodes using the recorded representation and proves exact byte reproduction;
4. re-parses source with the strict lexical parser;
5. proves pointer set, parent/child topology, source spans and raw digests still match IR;
6. preflights the complete edit set and existing edit preconditions;
7. renders each requested scalar token and validates semantic non-noop/type constraints;
8. replaces exact spans without rebuilding surrounding text;
9. encodes candidate using the original encoding/BOM;
10. proves every encoded byte segment outside authorized scalar spans remains exact, including stateful-codec boundaries;
11. re-reads candidate through `read_json_ir`;
12. verifies the complete pointer/topology set, requested target semantics and every unrequested raw digest/semantic payload;
13. verifies encoding/BOM representation is unchanged;
14. writes destination only after all verification passes.

Zero-edit output is byte-identical.

## Markdown boundary

JSON nodes are `unknown_native`; identity Markdown may show read-only placeholders when requested, but no H3 block advertises an editable capability. JSON Pointer/token ownership is richer than Markdown text semantics, so no generic text/table importer may generate `replace_json_scalar`.

## Verification requirements

Focused tests prove:

- strict lexical spans for nested objects/arrays and every scalar type;
- pointer escaping for `/` and `~` keys;
- strict string escapes and JSON number grammar;
- duplicate keys, comments, trailing commas, malformed strings/numbers and NaN/Infinity fail closed;
- deterministic IR, hierarchy and canonical digest;
- scalar capability vs container/read-only capability;
- UTF-8 BOM, UTF-16 LE/BE BOM and reversible legacy encoding preservation where strict JSON text remains valid;
- zero-edit byte identity;
- one and multiple scalar target-only replacements;
- string escaping and scalar type changes;
- structural replacement rejection;
- semantic no-op rejection including numerically equivalent number spellings;
- stale source/precondition/pointer/span/raw-digest rejection before output;
- unencodable replacement failure before output;
- stateful encoding leakage outside target rejection;
- candidate verifier catches unrequested scalar/raw/topology/representation drift;
- identity-Markdown stays read-only;
- existing one-way `.json` PlainTextConverter output remains unchanged;
- exact-head pre-commit and package/OCR Python 3.10-3.13 matrices are green.

## Follow-on boundary

After H3 is exact-head green, H4 XML may reuse only proven reversible-text and encoded untouched-byte primitives. XML must add namespace-aware element/attribute/text ownership while preserving prolog, prefixes, comments, whitespace and unrelated lexical source. H5 HTML must separately account for HTML parsing/recovery semantics rather than treating it as XML.
