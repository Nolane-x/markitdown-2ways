# MarkItDown 2Ways

MarkItDown 2Ways is the focused two-way layer in this fork. It keeps the existing
one-way `MarkItDown` API and CLI intact while adding bounded, evidence-driven round
trips:

```text
native document -> DocumentIR -> Markdown / typed edits -> native document
```

The production scope is intentionally narrow: Core IR, capability reporting,
identity/clean Markdown projection, PPTX, DOCX, conservative XLSX mutation, native
text/Markdown source preservation, target-only CSV cell mutation, target-only JSON
scalar mutation, target-only XML text/attribute mutation, and recovery-aware target-only
HTML text/quoted-attribute mutation. It is not an Office automation platform, workflow
engine, document-management service, browser automation layer, or general application
framework.

## Install this fork

```bash
git clone https://github.com/Nolane-x/markitdown-2ways.git
cd markitdown-2ways
pip install -e 'packages/markitdown[pptx,docx,xlsx]'
```

The original one-way API remains unchanged:

```python
from markitdown import MarkItDown

result = MarkItDown().convert("report.pdf")
print(result.markdown)
```

## Safety model

2Ways does not treat successful parsing as proof that mutation is safe. Readers expose
capability decisions; writers revalidate source authority, native ownership and edit
preconditions before constructing a candidate; format-specific preservation proofs and
semantic re-read verification run before destination bytes are emitted.

Core rules are:

- source SHA-256 and byte size are bound to `DocumentIR` and checked again by writers;
- unknown or unadvertised operations default to read-only;
- typed edits may carry semantic, native-locator and expected-old-value preconditions;
- complete edit sets are preflighted before output is written;
- zero-edit writes preserve exact source bytes where the format contract permits it;
- untouched native members, subtrees or encoded byte segments are verified according to
  the format's preservation model;
- malformed, ambiguous or unsupported ownership fails closed;
- the 2Ways core performs no network or subprocess I/O.

```python
from markitdown.twoways import build_capability_report, capabilities_for_node
from markitdown.twoways.formats.xlsx import read_xlsx_ir

with open("workbook.xlsx", "rb") as source_file:
    document = read_xlsx_ir(source_file)

report = build_capability_report(document)
node = document.nodes[document.canvases[0].root_node_ids[0]]
print(report.writable_by_operation)
print(capabilities_for_node(node).for_operation("update_sheet_cells"))
```

## Native text and Markdown source round trips

Phase H1 / v0.5 adds a native source-preserving adapter for `.txt`, `.text`, `.md`, and
`.markdown`. Plain text and Markdown share the same adapter because lexical source
bytes, rather than parsed Markdown structure, are authoritative in this tranche.

```python
from io import BytesIO

from markitdown.twoways import EditOperation
from markitdown.twoways.formats.text import patch_text, read_text_ir

with open("README.md", "rb") as source_file:
    source = source_file.read()

document = read_text_ir(BytesIO(source), filename="README.md", mimetype="text/markdown")
node_id = document.canvases[0].root_node_ids[0]
edit = EditOperation(
    operation_id="replace-source",
    type="replace_text",
    target_node_id=node_id,
    payload={"text": "# New title\n\nPreserved source representation.\n"},
)

with open("README-edited.md", "wb") as output_file:
    patch_text(document, BytesIO(source), output_file, edits=(edit,))
```

The reader records source SHA-256/size plus encoding, BOM, newline convention and
byte-roundtrip evidence. Mixed-newline or non-roundtrippable representations become
read-only where choosing a writable representation would require guessing. Native text
identity Markdown remains inspection-only; direct typed `replace_text` is authoritative.

## CSV source-preserving cell edits

Phase H2 adds direct `update_csv_cells` edits without regenerating the document through
`csv.writer`, pandas or another table serializer. Each materialized field has exact
lexical ownership, raw evidence and native coordinates.

```python
from io import BytesIO

from markitdown.twoways import EditOperation
from markitdown.twoways.formats.csv import patch_csv, read_csv_ir

with open("people.csv", "rb") as source_file:
    source = source_file.read()

document = read_csv_ir(BytesIO(source), filename="people.csv")
table_id = document.canvases[0].root_node_ids[0]
edit = EditOperation(
    operation_id="move-city",
    type="update_csv_cells",
    target_node_id=table_id,
    payload={
        "cells": [
            {"row": 1, "column": 1, "old_text": "North", "text": "South"},
        ]
    },
)

with open("people-edited.csv", "wb") as output_file:
    patch_csv(document, BytesIO(source), output_file, edits=(edit,))
```

Supported auto-detected delimiters are comma, semicolon, tab and pipe. Ambiguous
dialects fail closed. The writer patches only requested field spans, preserves physical
row terminators and neighboring lexical form, proves untouched encoded byte segments,
and strictly re-reads the candidate before output. CSV identity Markdown is
inspection-only in H2.

## JSON source-preserving scalar edits

Phase H3 adds strict JSON lexical ownership and direct `replace_json_scalar` edits. Each
JSON value receives an RFC 6901 pointer, exact span, native locator, raw-token digest and
deterministic hierarchy evidence.

```python
from io import BytesIO

from markitdown.twoways import EditOperation
from markitdown.twoways.formats.json import patch_json, read_json_ir

with open("config.json", "rb") as source_file:
    source = source_file.read()

document = read_json_ir(BytesIO(source), filename="config.json")
name_node = next(
    node
    for node in document.nodes.values()
    if node.metadata.get("json.pointer") == "/name"
)
edit = EditOperation(
    operation_id="rename",
    type="replace_json_scalar",
    target_node_id=name_node.node_id,
    payload={"value": "Nolane"},
)

with open("config-edited.json", "wb") as output_file:
    patch_json(document, BytesIO(source), output_file, edits=(edit,))
```

H3 never serializes an object, array or whole document. It patches only requested scalar
tokens, proves untouched encoded byte segments, then re-reads the candidate and verifies
pointer topology, requested semantics and unrequested scalar raw evidence. Structural
object/array mutation, JSON5, comments, trailing commas, duplicate decoded keys,
JSONL/NDJSON and non-finite numbers are outside H3. JSON identity Markdown is
inspection-only.

## XML source-preserving text and attribute edits

Phase H4 adds strict XML 1.0 lexical ownership with namespace-aware native paths. Direct
mutation is intentionally limited to **existing text owners** and **existing ordinary
attribute values** through `replace_xml_text` and `replace_xml_attribute`.

```python
from io import BytesIO

from markitdown.twoways import EditOperation
from markitdown.twoways.formats.xml import patch_xml, read_xml_ir

with open("config.xml", "rb") as source_file:
    source = source_file.read()

document = read_xml_ir(BytesIO(source), filename="config.xml")
name_node = next(
    node
    for node in document.nodes.values()
    if node.metadata.get("xml.kind") == "text"
    and node.payload.get("value") == "Ada"
)
edit = EditOperation(
    operation_id="rename",
    type="replace_xml_text",
    target_node_id=name_node.node_id,
    payload={"value": "Nolane"},
)

with open("config-edited.xml", "wb") as output_file:
    patch_xml(document, BytesIO(source), output_file, edits=(edit,))
```

H4 does not serialize or pretty-print the XML document. The lexical scanner records
exact owner/value spans, QName and expanded-name identity, in-scope namespace bindings,
quote style, raw digests, XML declaration evidence and source representation. The writer
renders only a requested scalar token, patches its exact span, re-encodes using the
recorded representation, proves every encoded byte segment outside authorized spans,
and performs a strict candidate re-read before destination output.

The candidate verifier compares the complete ownership path set, parent/child and sibling
order, namespace bindings, qualified and expanded names, XML declaration, representation,
requested semantics, and raw/semantic evidence for every unrequested leaf/native owner.
Ancestor element raw digests are not required to remain equal when a legitimate
descendant edit changes bytes inside that element.

H4 security is fail-closed: XML 1.1, DTDs, entity declarations, external entities and
unsupported markup declarations are rejected. The base runtime uses `defusedxml` as an
independent security/semantic cross-check and does not require `lxml`.

Element structure, element/attribute insertion or deletion, namespace declaration
mutation, prefix rewrite, CDATA mutation, comments and processing-instruction mutation
are not writable in H4. These regions remain preserved/read-only. Sources that can be
read safely but cannot prove byte-roundtrip representation are also read-only. XML
identity Markdown remains inspection-only; direct typed XML edits are authoritative.
Existing one-way plain-text conversion behavior is unchanged.

## HTML recovery-aware source-preserving edits

Phase H5 treats HTML as a separate recovery-aware format rather than reusing XML
well-formedness assumptions. The writable entry points accept `.html`, `.htm`, and
`text/html`; XHTML, XML, SVG, MathML and generic XML-like surfaces are not accepted as
writable HTML targets.

Direct mutation is intentionally limited to normal data-state text and existing quoted,
non-duplicate attribute values through `replace_html_text` and
`replace_html_attribute`.

```python
from io import BytesIO

from markitdown.twoways import EditOperation
from markitdown.twoways.formats.html import patch_html, read_html_ir

with open("page.html", "rb") as source_file:
    source = source_file.read()

document = read_html_ir(BytesIO(source), filename="page.html", mimetype="text/html")
text_node = next(
    node
    for node in document.nodes.values()
    if node.metadata.get("html.kind") == "text"
    and node.payload.get("value") == "Ada"
)
edit = EditOperation(
    operation_id="rename",
    type="replace_html_text",
    target_node_id=text_node.node_id,
    payload={"value": "Nolane"},
)

with open("page-edited.html", "wb") as output_file:
    patch_html(document, BytesIO(source), output_file, edits=(edit,))
```

H5 separates **lexical source authority** from an independent parser-recovery oracle. A
pure-Python scanner owns exact source spans, names, quote style, raw digests and native
paths. BeautifulSoup with Python's `html.parser` is used only to build an independent
recovery signature; DOM serialization is never a production write path.

Before mutation, the writer revalidates source SHA/size, source representation, fresh
native ownership, capability metadata and typed edit preconditions. It patches only the
recorded text/value spans, preserves the original attribute quote style, re-encodes using
the source representation, and proves every encoded byte segment outside authorized
spans remains exact. Immediately before destination output, the candidate is re-read and
must preserve lexical path/kind/name/topology, attribute quote shape, encoding/meta
declaration evidence, and the independent recovery signature. Requested owners must have
the requested semantic values; unrequested scalar/comment/doctype/rawtext/RCDATA owners
must retain their raw and semantic evidence.

H5 fails closed on recovery-sensitive or structurally ambiguous sources. Unquoted and
boolean attributes, duplicate normalized attributes, script/style raw text,
title/textarea RCDATA, comments, doctypes, encoding declarations, template content,
table-recovery-sensitive cases, foreign SVG/MathML content, structural edits, tag rename,
insertion/deletion/reordering and any source whose byte-roundtrip or recovery stability
cannot be proven are read-only. Identity Markdown is inspection-only; direct typed HTML
edits are authoritative. The existing one-way `HtmlConverter`, including its current
XHTML acceptance behavior, remains unchanged.

## PPTX and DOCX round trips

PPTX and DOCX use identity Markdown where the projection/importer can prove a semantic
edit maps back to one native owner. Supported text edits patch only the native XML part
that owns the target. Unsupported or ambiguous structures fail closed instead of being
silently rebuilt.

Both formats expose bounded deep edits through the same capability kernel:

- `set_text_style` on safe existing native runs, including bounded direct formatting;
- PPTX `move_resize` on safe non-group slide shapes using integer EMUs;
- picture alt-text edits where native carriers are unambiguous;
- simple table-cell text updates bound to expected old text.

Inherited/theme style synthesis, group-coordinate rewriting, structural table editing,
theme/master/SmartArt/macros/OLE mutation, DOCX numbering/field/tracked-change mutation
and other ambiguous surfaces remain outside the writable boundary.

## XLSX tranche-one round trip

The XLSX adapter reads worksheets and typed scalar cells into `DocumentIR` and supports
`update_sheet_cells` only where a conservative native patch can be proven.

```python
from io import BytesIO

from markitdown.twoways import EditOperation
from markitdown.twoways.formats.xlsx import patch_xlsx, read_xlsx_ir

with open("workbook.xlsx", "rb") as source_file:
    source = source_file.read()

document = read_xlsx_ir(BytesIO(source))
sheet_id = document.canvases[0].root_node_ids[0]
edit = EditOperation(
    operation_id="update-q3",
    type="update_sheet_cells",
    target_node_id=sheet_id,
    payload={
        "cells": [
            {"row": 1, "column": 2, "old_value": 38, "value": 42},
        ]
    },
)

with open("workbook-edited.xlsx", "wb") as output_file:
    patch_xlsx(document, BytesIO(source), output_file, edits=(edit,))
```

Formula cells, merged cells, rich inline/shared strings, unsupported cell types and
ambiguous/lossy regions remain read-only. Row/column/sheet structural edits, formula
mutation, merge/unmerge, chart/drawing mutation and style mutation are outside tranche
one. The production writer patches the original package rather than using `openpyxl` as
a serializer; `openpyxl` is an independent regression oracle.

## Current capability boundary

| Area | Text / Markdown H1 | CSV H2 | JSON H3 | XML H4 | HTML H5 | PPTX | DOCX | XLSX tranche one |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Read into `DocumentIR` | exact decoded lexical source + representation | lexical field spans + table semantics | strict spans + RFC 6901 hierarchy | strict XML owners + namespace identity | lexical owners + independent recovery signature | slides/groups/notes/text/media/tables | body/headers/footers/text/media/tables | worksheets and typed cells |
| Primary patch | `replace_text` | `update_csv_cells` | `replace_json_scalar` | `replace_xml_text` / `replace_xml_attribute` | `replace_html_text` / `replace_html_attribute` | bounded native text/style/geometry/media/table | bounded native text/style/media/table | scalar non-formula, non-merged cells |
| Identity Markdown edit | inspection-only | inspection-only | inspection-only | inspection-only | inspection-only | supported safe semantic regions | supported safe semantic regions | supported safe simple cell regions |
| Representation proof | encoding/BOM/newline | encoding/BOM + dialect/spans/terminators | encoding/BOM + pointer/span/raw token | encoding/BOM/declaration + lexical spans/namespaces | encoding/BOM/meta + lexical spans + recovery signature | OPC/XML ownership | OPC/XML ownership | OPC/XML + typed cell ownership |
| Structural edits | unsupported | unsupported | unsupported | unsupported | unsupported | bounded; ambiguous structures fail closed | bounded; ambiguous structures fail closed | row/column/sheet changes unsupported |

H1-H5 together form the v0.5 text/structured-text parity tranche. Later notebook,
publication and container work belongs to a separate v0.6 branch rather than extending
H5's writable boundary.

## Fidelity details

Format-specific proof strengthens the common safety model:

- native text binds source size, encoding, BOM and newline policy;
- CSV binds delimiter, field spans/raw digests and physical row terminators;
- JSON binds RFC 6901 paths, hierarchy, lexical value spans and raw-token digests;
- XML binds namespace-aware ownership paths, exact lexical/value spans, QName and
  expanded-name identity, declaration and representation evidence;
- HTML binds recovery-aware native paths, exact lexical/value spans, original/normalized
  names, quote shape, encoding/meta declarations and an independent recovery signature;
- CSV, JSON, XML and HTML prove every encoded byte segment outside requested targets
  remains exact;
- text, CSV, JSON, XML and HTML candidates are re-read before destination emission;
- XML additionally rejects DTD/entity/external-resolution surfaces before mutation;
- HTML additionally rejects recovery-sensitive/foreign/template/table/rawtext/RCDATA
  mutation surfaces before mutation;
- OOXML writers start from the original package and restrict mutation to authorized
  parts/subtrees, with unrelated package members verified after writes.

## Clean Markdown vs identity Markdown

Use clean mode when Markdown is the final projection. Use identity mode only where the
format adapter advertises a reversible semantic Markdown path. Do not remove or forge
`m2w` identity comments: the importer validates projection manifest, document/node
identity, semantic digests and native locator evidence before emitting typed edits.

Native lexical text/Markdown, CSV, JSON, XML and HTML are explicit v0.5 inspection-only
identity projections. Their direct typed native paths remain writable only where native
source evidence is sufficient.

## Scope discipline and roadmap

New work should improve fidelity, compatibility, safety, tests, or reduce complexity.
The project deliberately avoids broad platform features and keeps a soft production-size
ceiling around roughly twice the upstream MarkItDown implementation.

The approved broader parity program is in
`docs/superpowers/specs/2026-09-11-markitdown-2ways-full-parity-program-design.md`.
Current v0.5 execution documents include:

- `docs/superpowers/specs/2026-09-12-markitdown-2ways-phase-h1-text-source-preservation-design.md`
- `docs/superpowers/plans/2026-09-12-phase-h1-text-source-preservation-implementation.md`
- `docs/superpowers/specs/2026-09-12-markitdown-2ways-phase-h2-csv-source-preservation-design.md`
- `docs/superpowers/plans/2026-09-12-phase-h2-csv-source-preservation-implementation.md`
- `docs/superpowers/specs/2026-09-12-markitdown-2ways-phase-h3-json-source-preservation-design.md`
- `docs/superpowers/plans/2026-09-12-phase-h3-json-source-preservation-implementation.md`
- `docs/superpowers/specs/2026-09-12-markitdown-2ways-phase-h4-xml-source-preservation-design.md`
- `docs/superpowers/plans/2026-09-12-phase-h4-xml-source-preservation-implementation.md`
- `docs/superpowers/specs/2026-09-12-markitdown-2ways-phase-h5-html-source-preservation-design.md`
- `docs/superpowers/plans/2026-09-12-phase-h5-html-source-preservation-implementation.md`

Each tranche is complete only after its exact final branch head passes pre-commit plus
the package and OCR matrices on Python 3.10-3.13. H5 uses a separate recovery-aware
contract and does not change the existing one-way HTML converter, API or CLI. After the
H5 exact-head gate, v0.6 notebook/publication/container work must start on a new branch.
