# MarkItDown 2Ways Phase H5 HTML Source Preservation Design

## Status

Approved continuation of the v0.5 structured-text parity program after exact-head-green H4 XML `9c927af2ca964864ecad0c186c44e34525f04de0`.

H5 is deliberately not an XML clone. HTML tokenization, optional end tags, void elements, raw-text states and parser recovery mean that a DOM produced from source text is not automatically authoritative evidence for source mutation. H5 therefore treats exact lexical ownership and recovery stability as separate proofs.

## Goal

Add source-preserving two-way support for ordinary HTML source while preserving the existing one-way `HtmlConverter` unchanged.

The first H5 writable tranche supports only:

- replacement of existing normal HTML text owners through `replace_html_text`;
- replacement of existing quoted, non-duplicate attribute values through `replace_html_attribute`;
- exact zero-edit byte reuse;
- exact preservation of every encoded byte segment outside authorized target spans;
- strict candidate re-read and recovery-topology verification before destination emission.

Everything else remains read-only or fails closed.

## Non-goals

H5 does not add:

- element insertion/deletion/reorder/rename;
- attribute insertion/deletion/rename;
- unquoted-attribute rewriting;
- boolean-attribute mutation;
- DOM serialization, pretty-printing or formatter-based HTML rewriting;
- script/style/raw-text mutation;
- `textarea`/`title` RCDATA mutation in the first tranche;
- `<template>` content mutation;
- SVG/MathML/foreign-content mutation;
- table-structure mutation or mutation in recovery-sensitive table insertion modes;
- browser execution, JavaScript evaluation, CSS evaluation, resource loading or network access;
- XHTML mutation through the HTML writer;
- any change to the existing one-way HTML converter registry/API/CLI path.

## Architectural choice

### Chosen approach: lexical authority plus recovery-stability oracle

H5 uses three independent layers:

1. **Exact lexical scanner** — owns source character spans, raw tokens, normalized tag/attribute identities and source hierarchy where explicit source syntax is unambiguous.
2. **Recovery-stability oracle** — parses the same source using the existing base `beautifulsoup4` dependency with Python's `html.parser` backend and produces a normalized structural signature. The lexical model is writable only when its source hierarchy maps one-to-one to the recovered structure and no known recovery-sensitive construct is present.
3. **Transactional span patcher** — renders only the requested text/attribute value token, replaces only the exact owned spans, verifies untouched encoded bytes, re-reads the candidate and compares recovery/lexical topology before writing output.

BeautifulSoup is never the source-span authority and never serializes production output.

### Rejected approach: DOM parse and serializer writeback

A DOM serializer can normalize case, quote style, entities, optional tags, whitespace, attribute order and implied structure unrelated to the requested edit. That violates the v0.5 source-preservation contract.

### Rejected approach: parser object positions as native authority

Parser libraries are allowed to recover malformed input and do not provide the complete exact source ownership proof required by H5. Parser-derived locations can be diagnostics but cannot authorize native mutation.

## Accepted source surface

The H5 native reader accepts only:

- `.html`;
- `.htm`;
- `text/html`.

It explicitly rejects XHTML/XML surfaces including:

- `application/xhtml+xml`;
- `application/xhtml`;
- `application/xml`;
- `text/xml`;
- generic `+xml` MIME types.

XHTML belongs to the XML-style well-formedness model, not the HTML recovery model.

## Representation and encoding authority

HTML writeback must preserve the source byte representation.

`decode_html_source(source: bytes, *, encoding: str | None = None)` resolves decoding authority conservatively in this order:

1. explicit caller encoding when supplied;
2. Unicode BOM/signature evidence;
3. a single unambiguous HTML `<meta charset=...>` or equivalent `http-equiv="content-type"` declaration found in the initial source prefix;
4. the existing H1 text decoder fallback for readable-only ingestion.

For mutation, all of the following are required:

- decoded text can be encoded back to the exact original bytes;
- BOM/signature remains exact;
- all discovered encoding declarations are mutually compatible with the selected codec;
- candidate encoding declaration evidence is byte/semantic identical to the source;
- the replacement itself is representable by the source codec.

If any condition cannot be proven, the source remains readable but all H5 mutation capabilities are read-only with `html.encoding.not_roundtrippable` or a more specific encoding reason.

H5 does not attempt to implement the complete browser encoding-sniffing algorithm. Ambiguous transport/meta evidence fails closed for native mutation.

## Lexical model

Create immutable HTML lexical types under `markitdown.twoways.formats.html`.

### Owner kinds

The scanner records at minimum:

- `element`;
- `attribute`;
- `text`;
- `comment`;
- `doctype`;
- `rawtext`;
- `rcdata`.

Each owner records:

- deterministic native path;
- exact character start/end;
- exact raw source and SHA-256 raw digest;
- lexical kind;
- explicit parent path where authoritative;
- direct child paths where authoritative;
- original qname and normalized lowercase HTML name when applicable;
- semantic text/attribute value;
- exact value span for attributes;
- quote style for attributes (`'` or `"`, otherwise `None`);
- start-tag/end-tag evidence for element owners;
- recovery/read-only reason when ownership is not writable.

### HTML name semantics

ASCII HTML tag and attribute names are normalized case-insensitively for semantic identity while original source spelling remains preserved as lexical evidence.

Duplicate normalized attribute names make the owning start tag recovery-ambiguous for H5 mutation and therefore read-only/fail-closed for fine-grained mutation.

### Void elements

The scanner recognizes the HTML void-element set:

`area`, `base`, `br`, `col`, `embed`, `hr`, `img`, `input`, `link`, `meta`, `param`, `source`, `track`, `wbr`.

Void elements never acquire lexical child ownership and a source end tag for a void element is recovery-sensitive.

### Raw-text and RCDATA

`script` and `style` content is represented as `rawtext` and is read-only in H5.

`textarea` and `title` content is represented as `rcdata` and is read-only in H5 because their character-reference/end-tag behavior is context-specific and not needed for the first writable tranche.

### Comments and doctype

Comments and the document doctype are retained as exact lexical owners but are read-only.

Bogus declarations, conditional-comment-like constructs or malformed comment states that cannot be assigned one exact token boundary fail closed for fine-grained ownership.

## Recovery stability

Fine-grained H5 writes require `recovery_stable=True` for the document and target owner.

The stability proof has two parts.

### Lexical structural rules

The first tranche is writable only when the relevant source avoids constructs whose browser/parser recovery can change ownership independently of source-span replacement. H5 therefore rejects or marks read-only:

- mismatched or unclosed non-void elements;
- non-void self-closing syntax whose slash would be ignored by HTML parsing;
- explicit end tags for void elements;
- omitted-end-tag patterns that require implied closes for writable ancestry;
- nested `<p>` recovery;
- recovery-sensitive `li`, `dt`, `dd`, `option`, `optgroup`, `rt`, `rp` omission patterns;
- table insertion-mode structures where implied containers/foster parenting can change ancestry;
- `<template>`;
- SVG/MathML/foreign content;
- duplicate normalized attributes;
- malformed start/end tags;
- ambiguous character-reference boundaries in a writable owner.

These inputs may still be represented through a document-level read-only fallback rather than being advertised writable.

### Independent recovered-tree signature

For lexically stable input, BeautifulSoup with the built-in `html.parser` backend produces a normalized recovery signature containing:

- node kind sequence;
- normalized element names;
- parent/child order;
- normalized attribute-name sets;
- text-owner positions in the recovered tree, excluding text values;
- comment/doctype positions where represented.

The lexical model must map one-to-one to this signature for write capability to be exposed. A mismatch yields `html.recovery.unstable`.

The signature is structural only; BeautifulSoup output is never serialized.

## Read-only fallback

H5 must still give deterministic IR representation to readable HTML that cannot prove fine-grained ownership.

When tokenization/recovery mapping is readable but not authoritative, `read_html_ir` returns a single document-level `unknown_native` root carrying:

- source SHA-256/size;
- decoded text;
- encoding/BOM evidence;
- `html.recovery_stable=False`;
- the reason code that disabled native mutation;
- no writable H5 capability.

This fallback prevents false native locators while preserving parity for inspection.

If even safe deterministic source decoding/token boundaries cannot be established, the native H5 reader fails closed rather than fabricating ownership.

## Deterministic native paths

For stable fine-grained input, paths are based on normalized HTML names and one-based sibling indexes under the authoritative lexical parent, for example:

```text
/html[1]
/html[1]/body[1]
/html[1]/body[1]/p[1]
/html[1]/body[1]/p[1]/#text[1]
/html[1]/body[1]/p[1]/@class
```

Names are percent-encoded where necessary. Attribute paths are normalized by HTML attribute identity while metadata preserves original spelling.

Node IDs are derived deterministically from source SHA-256 + lexical kind + native path.

## IR and capability model

Stable owners map to `Node(kind="unknown_native")` with semantic roles such as:

- `html-element`;
- `html-attribute`;
- `html-text`;
- `html-comment`;
- `html-doctype`;
- `html-rawtext`;
- `html-rcdata`.

Writable capabilities:

- normal `text` -> `replace_html_text`;
- quoted, non-duplicate normal `attribute` -> `replace_html_attribute`.

Representative read-only reasons:

- `html.element.structural_edit_unsupported`;
- `html.attribute.unquoted_edit_unsupported`;
- `html.attribute.boolean_edit_unsupported`;
- `html.attribute.duplicate_name`;
- `html.rawtext.edit_unsupported`;
- `html.rcdata.edit_unsupported`;
- `html.template.recovery_sensitive`;
- `html.foreign_content.unsupported`;
- `html.table.recovery_sensitive`;
- `html.recovery.unstable`;
- `html.encoding.not_roundtrippable`.

Capability constraints for writable owners include:

```json
{
  "identity_markdown": false,
  "source_preservation": "lexical-source-span",
  "structural_edits": false,
  "target_only": true,
  "recovery_stable": true
}
```

## Typed edit contracts

Register exactly two H5 edit types:

- `replace_html_text`;
- `replace_html_attribute`.

Payload for both operations is exactly:

```json
{"value": "replacement text"}
```

The writer rejects:

- missing/extra payload fields;
- non-string values;
- wrong operation/kind pair;
- duplicate targets in one transaction;
- target paths absent from source authority;
- stale source digest/size;
- stale semantic/native locator/expected-old-value preconditions;
- semantic no-ops;
- values containing code points invalid for the selected source representation;
- writes to any read-only owner.

## Rendering

### Normal text

H5 renders requested normal text without changing parser state:

- `&` -> `&amp;`;
- `<` -> `&lt;`;
- `>` may be emitted as `&gt;` conservatively;
- requested carriage return -> `&#13;` so HTML input preprocessing cannot silently turn it into LF;
- other representable characters remain literal when safe.

A synthetic safe-wrapper parse validates that the rendered token decodes to exactly the requested semantic value before it is inserted.

### Quoted attributes

The original quote style is preserved.

The renderer escapes:

- `&`;
- `<`;
- the active quote;
- `>` conservatively;
- tab/LF/CR using numeric references `&#9;`, `&#10;`, `&#13;`.

The renderer never converts a quoted attribute to unquoted or vice versa in H5.

## Transaction and preservation proof

The writer performs all preflight before destination output.

For each edit it resolves the exact owned source span and builds one candidate string by applying non-overlapping replacements in source order.

The candidate is encoded using the recorded source representation.

The H5 writer then proves:

- original BOM/signature bytes are unchanged;
- strict whole-text encoding agrees with incremental character-to-byte boundaries;
- every source/candidate byte segment outside authorized target spans is exactly identical;
- encoding declaration evidence remains unchanged;
- no target span overlap occurred.

Only after this proof does candidate re-read begin.

## Candidate re-read verifier

`_verify_candidate(...)` re-reads the candidate through `read_html_ir` using recorded encoding authority.

It requires:

- source and candidate are both recovery-stable;
- ownership path sets are identical;
- lexical kinds are identical by path;
- normalized tag/attribute identities are identical;
- parent/child order is identical;
- recovery signatures are identical except requested scalar values;
- requested text/attribute semantic values equal typed requested values;
- every unrequested scalar/comment/doctype/rawtext/rcdata owner retains raw digest and semantic payload;
- original quote style for requested attributes is retained;
- encoding/BOM/meta-charset evidence is unchanged.

Ancestor element raw digest is not required to remain identical when a legitimate descendant value changes, but ancestor identity/topology/start/end-tag evidence must remain authoritative.

Destination bytes are written only after candidate verification succeeds.

## Zero-edit behavior

Zero edits require only source authority/native evidence verification and then write the original source bytes directly.

Zero-edit output is byte-for-byte identical.

## Identity Markdown

H5 identity Markdown is inspection-only.

HTML native lexical fidelity includes tag spelling, entities, quoting, comments, raw-text boundaries, optional/recovery-sensitive syntax and exact source spans. Generic Markdown cannot reconstruct that evidence.

HTML manifest blocks therefore expose no editable capabilities and the identity importer must not synthesize H5 edits.

Direct typed H5 operations are the only native mutation path in this tranche.

## One-way compatibility

The existing `HtmlConverter` remains untouched.

H5 tests lock current one-way behavior for `.html`/`.htm` and `text/html` inputs. The two-way reader/writer is additive and is not registered into the one-way converter machinery.

## Safety and I/O

H5 core behavior performs no network or subprocess I/O.

Parsing HTML must not fetch resources, execute scripts, evaluate CSS or follow links.

`script`, `style`, URLs and event-handler attributes are inert source text to the parser. Their existence does not authorize execution.

## Public API

The stable H5 surface is:

- `HtmlIRReader`;
- `HtmlPatchWriter`;
- `read_html_ir`;
- `patch_html`.

The writer adapter accepts only HTML-backed documents with target format `html` or extension `.html`/`.htm`.

`write(...)` requires `source_stream=` and `edits=` and rejects unknown writer options.

## Test strategy

H5 requires TDD RED evidence before every production seam.

Required tests cover:

- stable nested HTML with mixed tag/attribute case;
- comments, doctype and void elements;
- quoted attributes with both quote styles;
- named/numeric character references;
- UTF-8/BOM and reversible legacy encodings;
- ambiguous/conflicting meta charset evidence;
- malformed/unclosed/mismatched tags;
- optional-end-tag recovery cases;
- nested `<p>` recovery;
- table recovery-sensitive markup;
- template/foreign content;
- duplicate attributes;
- rawtext/RCDATA read-only boundaries;
- zero-edit byte identity;
- source/native-evidence forgery rejection;
- edit preconditions and semantic no-op rejection;
- exact text/attribute rendering;
- multiple longer/shorter replacements;
- unencodable replacements;
- untouched encoded-byte proof;
- candidate topology/recovery drift fault injection;
- requested semantic mismatch;
- unrequested raw drift;
- public imports/writer adapter;
- identity-Markdown inspection-only behavior;
- one-way `HtmlConverter` regression;
- full package/OCR regressions Python 3.10-3.13;
- pre-commit exact-head gate.

## Completion gate

H5 is complete only when the exact final H5 branch head passes all nine required checks:

1. pre-commit;
2. package Python 3.10;
3. package Python 3.11;
4. package Python 3.12;
5. package Python 3.13;
6. OCR Python 3.10;
7. OCR Python 3.11;
8. OCR Python 3.12;
9. OCR Python 3.13.

No documentation-only/status-only commit may be added after the observed exact-head green gate.

After H5, v0.5 structured-text parity is complete and the roadmap proceeds to v0.6 notebook/publication/container parity on a new stacked branch.