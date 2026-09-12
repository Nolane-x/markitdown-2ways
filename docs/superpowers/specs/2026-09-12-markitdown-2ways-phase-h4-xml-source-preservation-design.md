# MarkItDown 2Ways Phase H4 XML Source Preservation Design

## Status

Execution design for the XML tranche of v0.5.0, stacked only on exact-head-green H3 JSON `4501f087d0f46072246a9d88bbf05c85d0108fe7`.

H4 is deliberately narrower than a general XML editor. It replaces character data in existing normal text segments and values of existing non-namespace attributes while preserving all unrelated lexical source exactly. Element structure, namespace declarations, prefixes, comments, processing instructions, CDATA boundaries, declarations and all other syntax remain immutable.

## Goal

Add deterministic two-way XML support that can safely replace an existing text or attribute value by exact source spans while preserving every byte outside authorized targets.

A successful mutation must prove all of the following before destination emission:

1. the input bytes are exactly the source bound into `DocumentIR`;
2. the XML is strict, well-formed XML 1.0 with no DTD/entity-declaration surface;
3. every writable value has unique lexical and namespace-aware ownership;
4. the complete edit set passes semantic/native preconditions;
5. only authorized value spans change;
6. bytes outside those spans remain exact after encoding;
7. a strict candidate re-read preserves XML paths, namespace-expanded identities and topology;
8. requested values re-read to the requested semantics and unrequested native evidence stays unchanged.

## Public surface

Create `markitdown.twoways.formats.xml` with:

- `read_xml_ir(source, *, filename=None, mimetype=None, encoding=None) -> DocumentIR`
- `patch_xml(document, source, destination, *, edits=()) -> WriterResult`
- `XmlIRReader`
- `XmlPatchWriter`

The H4 reader accepts only:

- `.xml`
- `application/xml`
- `text/xml`

H4 deliberately does not claim generic `+xml`, SVG, XHTML, RSS/Atom or other XML-derived media types. Those formats can reuse proven XML primitives later only under their own semantic contracts.

## Dependencies and parser architecture

H4 must work with the base `markitdown` installation. `defusedxml` is already a required dependency; `lxml` is optional and therefore must not become part of the H4 runtime contract.

The XML reader uses two independent layers:

1. a custom source scanner owns exact decoded character spans, qnames, namespace declarations, attribute quoting and lexical evidence;
2. `defusedxml.ElementTree` performs an independent well-formedness/security cross-check with DTD, entity and external-reference processing forbidden.

The lexical scanner is not allowed to fetch network resources or invoke subprocesses.

## Security boundary

H4 rejects rather than expands the dangerous XML surface.

The following fail closed before an editable `DocumentIR` is returned:

- `<!DOCTYPE ...>` in any form;
- internal or external entity declarations;
- entity declarations reached through a DTD;
- external parsed entities;
- external parameter entities;
- XML 1.1 declarations;
- malformed XML declarations;
- duplicate attributes;
- undeclared prefixes;
- namespace binding violations;
- malformed comments, processing instructions, CDATA sections or element nesting;
- multiple root elements or non-whitespace character data outside the root element;
- unsupported markup declarations.

Normal predefined entities (`amp`, `lt`, `gt`, `apos`, `quot`) and numeric character references are source syntax, not entity declarations, and remain supported.

## Source encoding authority

XML encoding is part of native ownership and must be proved independently of semantic parsing.

Resolution order:

1. explicit caller encoding, if supplied;
2. Unicode BOM or XML byte-order signature;
3. XML declaration encoding for ASCII-compatible sources;
4. H1 reversible text detection only when the prior XML-specific evidence is absent.

Supported Unicode signatures include UTF-8 BOM and UTF-16/UTF-32 endian BOM/signature forms. The XML declaration, when present, records its exact raw source and declared `version`, `encoding` and `standalone` values.

The resolved codec and XML declaration must be compatible. Examples:

- `encoding="UTF-8"` must resolve to UTF-8;
- generic `UTF-16` may resolve to UTF-16LE/BE only when BOM/signature evidence establishes endianness;
- generic `UTF-32` follows the equivalent rule;
- an explicit codec that contradicts a BOM/signature or declaration is rejected.

The source representation records at minimum:

- resolved encoding;
- BOM kind;
- byte-roundtrip proof;
- XML version;
- declared encoding, if present;
- declared standalone value, if present;
- exact XML declaration raw source and raw digest, if present.

A representation that cannot reproduce the original bytes exactly is readable only if safe parsing is possible, but writable text/attribute capabilities are disabled with `xml.encoding.not_roundtrippable`.

## Lexical model

The decoded XML source is scanned deterministically. Every owned native region is represented by an immutable lexical node with:

- stable native path;
- lexical kind;
- exact `[start, end)` character span;
- exact raw source and SHA-256 raw digest;
- parent path and ordered child paths;
- lexical qname when applicable;
- namespace-expanded name when applicable;
- decoded semantic value when applicable;
- exact value span for writable attributes;
- quote character for attributes;
- namespace binding data where applicable.

Required lexical kinds:

- `element`
- `attribute`
- `namespace`
- `text`
- `cdata`
- `comment`
- `processing_instruction`

### Element ownership

Start and end tags are parsed without normalizing source. Self-closing syntax is preserved as source evidence.

Each element records its lexical qname and expanded name `{namespace-uri}local-name` (or an empty namespace URI). Namespace declarations on the start tag are applied to that element and its attributes according to XML Namespaces rules:

- the default namespace applies to unprefixed element names;
- the default namespace does not apply to unprefixed attribute names;
- the built-in `xml` prefix is permanently bound to `http://www.w3.org/XML/1998/namespace`;
- namespace declaration attributes themselves are native read-only namespace nodes, not writable attributes.

### Deterministic native paths

H4 paths are ownership paths, not a complete XPath implementation.

Element paths use namespace-expanded names plus a one-based sibling index among siblings having the same expanded name. Expanded-name components are percent-encoded so `/`, `%`, braces and arbitrary Unicode cannot create path ambiguity.

Conceptual examples:

```text
/{urn:example}root[1]
/{urn:example}root[1]/{urn:example}item[2]
/{urn:example}root[1]/@{urn:meta}id
/{urn:example}root[1]/#text[1]
/{urn:example}root[1]/#cdata[1]
/{urn:example}root[1]/#comment[1]
/{urn:example}root[1]/#pi[1]
```

Attribute expanded names must be unique on one element. Text/comment/CDATA/PI indices are one-based within their lexical kind under the parent.

### Character and reference semantics

With DTDs forbidden, named references are limited to XML's five predefined entities. Numeric decimal and hexadecimal character references are decoded strictly and must resolve to XML 1.0-valid characters.

Semantic normalization follows XML 1.0 rules relevant to H4:

- physical CRLF and CR in parsed character data normalize to LF;
- attribute literal whitespace normalization is applied as required for attributes without DTD type information;
- numeric character references retain the referenced character semantics (for example a referenced tab remains a tab).

H4 never rewrites an unrequested reference spelling. `&amp;`, `&#38;` and `&#x26;` are semantically equivalent but lexically distinct evidence.

## IR mapping

One XML file maps to one `Canvas(kind="xml")`. Every lexical owner maps to `Node(kind="unknown_native")`, preventing generic Markdown text semantics from inventing editable XML ownership.

Semantic roles are:

- `xml-element`
- `xml-attribute`
- `xml-namespace`
- `xml-text`
- `xml-cdata`
- `xml-comment`
- `xml-processing-instruction`

The document root element is the canvas/root node. Child ordering follows lexical source order. Attributes/namespaces are represented as owned nodes but do not alter element-child document order; metadata explicitly distinguishes attribute ownership from element/text child topology.

Node IDs are deterministic from source SHA-256 plus lexical kind plus native path.

Native locators use:

```text
backend="xml"
part_uri="/"
object_id=<lexical kind>
path=<native ownership path>
```

Provenance `char_span` binds the exact owned lexical region.

Metadata records native path, kind, qname/expanded name when applicable, raw source/digest, source representation proof and `xml.native_source=true`, `xml.identity_markdown=false`.

## Capability contract

H4 adds exactly two operations:

```text
replace_xml_text
replace_xml_attribute
```

A normal character-data `xml-text` node advertises `replace_xml_text` as writable only when representation proof is byte-roundtrippable.

A normal non-namespace `xml-attribute` node advertises `replace_xml_attribute` as writable only when representation proof is byte-roundtrippable.

Writable constraints are:

```json
{
  "identity_markdown": false,
  "source_preservation": "lexical-source-span",
  "structural_edits": false,
  "target_only": true
}
```

Read-only boundaries include:

- element structure: `xml.element.structural_edit_unsupported`;
- namespace declaration: `xml.namespace.structural_edit_unsupported`;
- CDATA: `xml.cdata.lexical_edit_unsupported`;
- representation not byte-roundtrippable: `xml.encoding.not_roundtrippable`.

Comments and processing instructions have no writable H4 operation. They are preserved native evidence only.

## Edit contract

Both H4 operations use exactly:

```json
{"value": "replacement string"}
```

Only Python strings are accepted. Structural values and additional payload keys are rejected.

The writer rejects:

- operation/node-kind mismatch;
- missing or stale target;
- stale semantic/native locator/expected-old-value preconditions;
- duplicate edit targets;
- semantic no-ops;
- values containing XML 1.0-invalid characters;
- values that cannot be represented in the recorded source encoding.

## Target rendering

H4 renders only the requested value token. It never serializes a containing element or complete XML document.

### Text rendering

For normal text nodes:

- `&` -> `&amp;`
- `<` -> `&lt;`
- `>` may be escaped conservatively as `&gt;`
- literal carriage return is emitted as `&#13;` so re-read semantics remain a carriage return rather than XML newline-normalized LF;
- other XML 1.0-valid characters remain literal if representable in the source encoding.

### Attribute rendering

The original quote character is retained. Attribute values escape:

- `&`
- `<`
- the active quote character
- `>` conservatively

Literal tab, LF and CR requested semantics are emitted as numeric character references `&#9;`, `&#10;`, `&#13;` so they survive XML attribute whitespace normalization.

## Transactional writer

`XmlPatchWriter` performs this sequence:

1. validate `DocumentIR`;
2. read source bytes and verify SHA-256 and byte size;
3. resolve and verify the recorded XML representation/declaration;
4. re-scan/re-parse the actual source strictly;
5. prove every native path, kind, expanded name, parent/child relation, source span and raw digest against IR evidence;
6. preflight the complete edit set and typed preconditions;
7. render only requested text/attribute value tokens;
8. replace exact character spans in source order without rebuilding surrounding markup;
9. encode through the original representation;
10. prove BOM and every encoded byte segment outside authorized target spans remain exact, including stateful-codec boundaries;
11. strict re-read candidate through `read_xml_ir`;
12. verify native path set, namespace-expanded identities and topology;
13. verify each requested semantic value;
14. verify every unrequested leaf/native region retains its raw digest and semantic payload where applicable;
15. verify representation/declaration evidence remains unchanged;
16. write destination only after all verification passes.

Ancestor element raw digests naturally cover edited descendants and therefore are not required to remain equal. Structural identity is instead proven through paths/topology plus the independent untouched-byte proof.

Zero edits return the original source bytes exactly.

## Encoded untouched-byte proof

H4 reuses the proven H3 concept but keeps the XML implementation local until a shared abstraction has two independently stable consumers.

For source and candidate decoded text, an incremental encoder builds character-to-byte boundaries. The incremental output must equal strict whole-text encoding. The writer then compares every untouched source/candidate encoded segment exactly, plus BOM/payload boundaries. A stateful codec whose replacement changes encoder state outside the target is rejected before output.

## Candidate verification

Candidate verification re-reads through the public XML reader using the recorded encoding. Verification compares native ownership by path rather than node ID because source SHA changes after a legitimate edit.

Required checks:

- identical path set;
- identical lexical kinds for all paths;
- identical element/attribute expanded names;
- identical namespace bindings and declaration ownership;
- identical parent/child topology and element order;
- requested text/attribute semantics equal requested values;
- unrequested leaf/native raw digests remain equal;
- representation and XML declaration metadata remain equal.

## Markdown boundary

All XML nodes are `unknown_native`. Identity Markdown may expose inspection placeholders when explicitly requested, but every manifest block has `editable_capabilities=()`.

Generic text or table Markdown importers must never synthesize `replace_xml_text` or `replace_xml_attribute`. Typed native edits are the only H4 mutation path.

## Existing one-way behavior

H4 must not modify the existing one-way converter registry, CLI or `MarkItDown` API.

There is no dedicated one-way XML writer/serializer requirement in this tranche. A regression test will prove that existing `PlainTextConverter` behavior with an explicitly textual XML `StreamInfo` remains unchanged.

## Verification requirements

Focused tests must prove:

- nested elements and same-name sibling indexing;
- default and prefixed namespace resolution;
- unprefixed attribute namespace semantics;
- exact start/end/value spans and quote style;
- predefined/numeric reference semantics;
- comments, processing instructions, CDATA and self-closing elements are preserved;
- XML declaration parsing and encoding authority;
- malformed nesting, duplicate attributes and undeclared prefixes fail closed;
- XML 1.1, DTDs, entity declarations and external entity forms fail closed;
- deterministic IR and capability decisions;
- zero-edit byte identity;
- text and attribute target-only replacement;
- escaping and whitespace/reference preservation;
- semantic no-op and stale evidence rejection;
- UTF-8 BOM, UTF-16LE/BE and reversible legacy encoding preservation;
- unencodable replacement failure before output;
- stateful encoding leakage rejection;
- candidate verifier catches path/topology/namespace/representation/unrequested drift;
- public imports are stable;
- identity Markdown stays inspection-only;
- existing one-way XML-as-text behavior remains unchanged;
- exact final head passes pre-commit and package/OCR Python 3.10-3.13 matrices.

## Follow-on boundary

After H4 is exact-head green, H5 HTML must not inherit XML well-formedness assumptions. HTML has parser recovery, optional tags, case-insensitive syntax in HTML mode, raw-text elements, character-reference differences and DOM/source divergence. H5 therefore requires a separate parser-recovery-aware ownership contract rather than treating HTML as XML.