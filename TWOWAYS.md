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
scalar mutation, target-only XML text/attribute mutation, recovery-aware target-only
HTML text/quoted-attribute mutation, target-only Jupyter Notebook cell-source mutation,
package-preserving EPUB 3 metadata/XHTML text mutation, bounded recursive ordinary ZIP
composition over supported typed inner formats, and conservative PDF Document Information
plus existing URI-link target incremental mutation. It is not an Office automation
platform, workflow engine, document-management service, browser automation layer,
archive authoring suite, or general application framework.

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

## Jupyter Notebook source-preserving cell-source edits

Phase H6 starts the v0.6 notebook tranche with a deliberately narrow writable boundary
for `.ipynb` documents. The reader binds the original notebook JSON bytes, encoding/BOM,
notebook format version, top-level metadata, cell order/type/id, per-cell non-source
state, and the exact lexical representation of each cell `source` value into
`DocumentIR` evidence.

The only H6 mutation is direct `replace_ipynb_cell_source` on an advertised cell-source
text node. A source encoded as one JSON string stays one string. A source encoded as a
JSON string array stays an array with the same element cardinality; the replacement is
deterministically repartitioned across those existing scalar owners. Empty source arrays
and representations that cannot prove a unique fixed-cardinality mapping remain
read-only rather than being normalized or structurally rewritten.

```python
from io import BytesIO

from markitdown.twoways import EditOperation
from markitdown.twoways.formats.ipynb import patch_ipynb, read_ipynb_ir

with open("analysis.ipynb", "rb") as source_file:
    source = source_file.read()

document = read_ipynb_ir(BytesIO(source), filename="analysis.ipynb")
source_node = next(
    node
    for node in document.nodes.values()
    if node.metadata.get("ipynb.role") == "source"
)
edit = EditOperation(
    operation_id="replace-cell-source",
    type="replace_ipynb_cell_source",
    target_node_id=source_node.node_id,
    payload={"value": "# Updated cell\n"},
)

with open("analysis-edited.ipynb", "wb") as output_file:
    patch_ipynb(document, BytesIO(source), output_file, edits=(edit,))
```

H6 does not introduce a notebook serializer. After complete H6 preflight, each authorized
cell source is lowered deterministically to the existing H3 `replace_json_scalar`
primitive against an internal candidate buffer. H3 therefore remains the lexical byte
patch authority and proves its ordinary untouched-token/byte contracts. The caller's
output receives no bytes until the complete H3 candidate exists and the H6 notebook
verifier has accepted it.

The H6 candidate verifier strictly re-reads the patched notebook and requires source
representation, `nbformat`/`nbformat_minor`, top-level non-cell state, cell count/order,
cell type/id, execution state, outputs, attachments and cell metadata to remain unchanged.
Requested cells must contain exactly the requested logical source. Unrequested cell
sources must preserve both semantics and raw source-token evidence. Any parse drift,
representation drift, ownership drift or unexpected semantic change fails closed with
empty caller output.

Notebook/cell insertion, deletion or reordering; cell-type/id mutation; notebook or cell
metadata mutation; output/attachment/execution-count mutation; arbitrary JSON structure
edits; notebook execution; kernels; network access; subprocesses; and source-array
cardinality changes are outside H6. Zero-edit writes are byte-for-byte identical.
Identity Markdown is inspection-only in H6: it exposes markdown/code/raw source text but
advertises no reversible Markdown edit capability. Direct typed cell-source edits are
the sole writable path. The existing one-way `IpynbConverter`, including `.ipynb` and
JSON-MIME notebook probing and its current markdown/code/raw rendering behavior, remains
unchanged.

## EPUB 3 package-preserving text edits

Phase H7 extends v0.6 to EPUB 3 without introducing a whole-publication serializer. The
reader treats the EPUB as an OCF ZIP package, validates the mandatory uncompressed first
`mimetype` member, safe ordered member inventory, resource limits, `container.xml`, the
OPF package graph, manifest/spine ownership and strict XML authority. Multiple renditions
and non-EPUB-3 packages remain inspectable but do not advertise H7 write capabilities.

H7 exposes exactly two writable operations: `replace_epub_metadata_text` for selected
existing OPF metadata text owners (`title`, `creator`, `language`, `publisher`, `date`,
`description`, `subject`) and `replace_epub_xhtml_text` for ordinary existing text below
`body` in local non-navigation XHTML resources. Navigation content, script/style/template,
SVG, MathML, remote resources, identifiers, manifest/spine structure, package inventory,
media and arbitrary member replacement remain read-only.

```python
from io import BytesIO

from markitdown.twoways import EditOperation
from markitdown.twoways.formats.epub import patch_epub, read_epub_ir

with open("book.epub", "rb") as source_file:
    source = source_file.read()

document = read_epub_ir(BytesIO(source), filename="book.epub")
text_node = next(
    node
    for node in document.nodes.values()
    if node.metadata.get("epub.owner_kind") == "xhtml-text"
    and node.payload.text == "world"
)
edit = EditOperation(
    operation_id="replace-xhtml-text",
    type="replace_epub_xhtml_text",
    target_node_id=text_node.node_id,
    payload={"value": "WORLD"},
)

with open("book-edited.epub", "wb") as output_file:
    patch_epub(document, BytesIO(source), output_file, edits=(edit,))
```

Each requested EPUB owner is re-resolved against fresh native evidence and lowered to
H4 `replace_xml_text` inside an internal member buffer. H4 remains the exact lexical XML
patch authority. Only after all touched members pass H4 verification does H7 build a
sparse EPUB candidate from the original package. Zero edits reuse the exact source bytes;
mutations preserve ordered inventory, protected OCF members, per-entry package metadata
where representable, and byte-identical content for every untouched member.

Before destination emission, H7 strictly re-reads the complete candidate and verifies OCF
invariants, package path/version/identifier linkage, manifest and spine semantics,
requested owner values, unrequested owner evidence and untouched member digests. Unsupported
ZIP compression methods, encrypted/symlink/unsafe/duplicate members, package resource
limit violations, ambiguous local ownership and malformed or unsafe XML/package graphs
fail closed. H7 never fetches remote resources and performs no network or subprocess I/O.

Identity Markdown is inspection-only for EPUB: it exposes selected metadata and readable
spine text but advertises no reversible Markdown edit capability. Direct typed EPUB
operations are authoritative. The existing one-way `EpubConverter` remains unchanged.

## Recursive ZIP package-preserving composition

Phase H8 adds bounded recursive ordinary ZIP support as a **preservation and routing
layer**, not as a generic binary archive editor. A ZIP-backed `DocumentIR` contains an
archive canvas, read-only archive/member structural nodes, and deterministic namespaced
copies of supported inner documents. Namespacing uses the complete member chain so nested
canvases and nodes preserve their original semantics without colliding across siblings.

Strong package formats are classified before generic ZIP recursion. EPUB and OOXML
DOCX/PPTX/XLSX therefore retain their package-specific authorities instead of being
mistaken for ordinary ZIPs. Ordinary typed members currently compose the existing H1-H7
writers for native text/Markdown, CSV, JSON, XML, HTML, IPYNB, EPUB, DOCX, PPTX and XLSX;
nested ordinary ZIPs recurse through the same H8 policy. Unsupported or ambiguous member
formats remain opaque/read-only and do not prevent unrelated safe typed siblings from
being used.

```python
from io import BytesIO

from markitdown.twoways import EditOperation
from markitdown.twoways.formats.zip import patch_zip, read_zip_ir

with open("bundle.zip", "rb") as source_file:
    source = source_file.read()

document = read_zip_ir(BytesIO(source), filename="bundle.zip")
name_node = next(
    node
    for node in document.nodes.values()
    if node.metadata.get("zip.member_chain") == ("data/config.json",)
    and node.metadata.get("json.pointer") == "/name"
)
edit = EditOperation(
    operation_id="rename-nested-json",
    type="replace_json_scalar",
    target_node_id=name_node.node_id,
    payload={"value": "Nolane"},
)

with open("bundle-edited.zip", "wb") as output_file:
    patch_zip(document, BytesIO(source), output_file, edits=(edit,))
```

Before any mutation H8 re-parses the root archive, validates SHA/size authority, proves
every intermediate member digest/size in the requested chain, reclassifies the terminal
member and reconstructs a fresh inner `DocumentIR`. The requested typed operation is then
delegated unchanged to the existing inner writer in an internal buffer. Complete edit
sets are preflighted before mutation; edits across multiple nested branches are prepared
as one transaction and propagated upward through sparse ZIP candidates. Caller output is
written only after the complete root candidate passes a fresh recursive verification.
One failing inner edit therefore rolls back all sibling edits.

H8 enforces global recursion limits for depth, per-archive and global member counts,
per-member/per-archive/global expanded bytes and compression ratio. Unsafe traversal or
absolute paths, drive/backslash forms, duplicate names, symlinks, encrypted entries,
malformed archives and compression methods outside Stored/Deflate fail closed. Nested ZIP
bombs are bounded by the same shared budgets. Archive/member add, delete, rename, reorder,
comment mutation, compression conversion, encryption, split archives and arbitrary opaque
member replacement are unsupported.

Zero-edit ZIP writes are exact source bytes. Mutated archives preserve ordered inventory,
archive comments, directory entries, required member metadata and byte-identical
uncompressed content for every untouched member. H8 claims high preservation rather than
exact compressed-bitstream identity for rebuilt touched archive chains. Identity Markdown
is inspection-only for every ZIP-backed imported node even when its inner typed capability
is directly writable; direct typed operations remain the only H8 mutation path. The
existing one-way `ZipConverter` remains unchanged and independent of the H8 registry.

## PDF Document Information incremental metadata edits

Phase H9 starts v0.7 with a deliberately narrow native-safe PDF mutation boundary. The
reader binds source SHA-256/size, strict PDF catalog and Document Information object
identity, page count and the existing text values of `/Title`, `/Author`, `/Subject` and
`/Keywords`. Only those existing owners may advertise `update_pdf_metadata`.

```python
from io import BytesIO

from markitdown.twoways import EditOperation
from markitdown.twoways.formats.pdf import patch_pdf, read_pdf_ir

with open("report.pdf", "rb") as source_file:
    source = source_file.read()

document = read_pdf_ir(BytesIO(source), filename="report.pdf")
title_node = next(
    node
    for node in document.nodes.values()
    if node.metadata.get("pdf.info_key") == "/Title"
)
edit = EditOperation(
    operation_id="update-title",
    type="update_pdf_metadata",
    target_node_id=title_node.node_id,
    payload={"field": "Title", "value": "Updated title"},
)

with open("report-edited.pdf", "wb") as output_file:
    patch_pdf(document, BytesIO(source), output_file, edits=(edit,))
```

H9 never rewrites the original PDF body. Zero edits reuse the exact source bytes. A
mutation is constructed with pypdf incremental mode in an internal buffer; the complete
original PDF must remain the exact candidate prefix, and pypdf's changed-object inventory
must contain only the authoritative `/Info` object. Before caller output is written, the
candidate is strictly re-read, catalog and `/Info` object identities and page count must
remain stable, requested values must match, every unrequested Document Information entry
must remain semantically identical, and an independent pdfminer metadata read must agree
with pypdf.

PDFs with XMP metadata authority, encryption, signature fields, certification policy,
linearization, missing or ambiguous indirect `/Info` ownership, supported metadata stored
as non-text values, or configured resource-limit violations remain read-only or fail
closed. H9 does not add metadata keys and does not edit annotations, forms, links,
outlines, page text, images, page content streams or arbitrary PDF objects. Identity
Markdown is inspection-only; direct typed `update_pdf_metadata` is authoritative. The
existing one-way `PdfConverter` remains byte-for-byte unchanged and independent of H9.

## PDF existing URI-link incremental edits

Phase H10 extends v0.7 without turning PDF into a general annotation editor. The reader
materializes deterministic `pdf-link-uri` nodes only for existing indirect `/Subtype
/Link` annotations with an existing `/A` action, `/S /URI`, and existing `/URI` value.
Writable capability `update_pdf_link_uri` is advertised only when the URI is text and the
annotation/action ownership is unique and fully authoritative.

```python
from io import BytesIO

from markitdown.twoways import EditOperation, EditPrecondition
from markitdown.twoways.formats.pdf import patch_pdf, read_pdf_ir

with open("report.pdf", "rb") as source_file:
    source = source_file.read()

document = read_pdf_ir(BytesIO(source), filename="report.pdf")
link_node = next(
    node for node in document.nodes.values() if node.semantic_role == "pdf-link-uri"
)
edit = EditOperation(
    operation_id="update-link",
    type="update_pdf_link_uri",
    target_node_id=link_node.node_id,
    precondition=EditPrecondition(expected_old_value=link_node.payload.text),
    payload={
        "page_index": link_node.metadata["pdf.page_index"],
        "annotation_index": link_node.metadata["pdf.annotation_index"],
        "old_uri": link_node.payload.text,
        "uri": "https://example.com/new",
    },
)

with open("report-edited.pdf", "wb") as output_file:
    patch_pdf(document, BytesIO(source), output_file, edits=(edit,))
```

H10 preserves H9's append-only source-prefix contract and permits mixed metadata/link
transactions. The pypdf incremental changed-object set must equal the exact union of the
H9 `/Info` owner and requested H10 link mutation owners. A fresh strict re-read must keep
page object identities, annotation count/order/ownership topology, every sibling
annotation fingerprint, and immutable target semantics outside `/URI` unchanged. Direct
action targets may change their containing annotation fingerprint only because `/URI`
changed. pdfplumber independently confirms requested hyperlink URI semantics.

H10 fails closed for direct annotation-array entries without indirect write authority,
shared mutation owners, `/Dest`, `/AA`, unsupported actions, non-text URI values,
ambiguous/malformed annotation authority, source-policy blockers such as XMP,
encryption/signatures/certification/linearization, and annotation/URI resource-limit
violations. It does not create, delete, reorder, resize or restyle annotations; edit
forms, non-URI actions, page text/images/content streams, outlines or appearances; or
regenerate the PDF. PDF identity Markdown remains inspection-only. The existing one-way
`PdfConverter` remains byte-for-byte unchanged.

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

| Area | Text / Markdown H1 | CSV H2 | JSON H3 | XML H4 | HTML H5 | IPYNB H6 | EPUB H7 | ZIP H8 | PDF H9-H10 | PPTX | DOCX | XLSX tranche one |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Read into `DocumentIR` | exact decoded lexical source + representation | lexical field spans + table semantics | strict spans + RFC 6901 hierarchy | strict XML owners + namespace identity | lexical owners + independent recovery signature | notebook/cell source semantics + lexical representation | OCF package graph + selected OPF/XHTML owners | ordered recursive inventory + namespaced supported inner IR | strict PDF source + existing `/Info` text owners + deterministic existing URI-link evidence/topology | slides/groups/notes/text/media/tables | body/headers/footers/text/media/tables | worksheets and typed cells |
| Primary patch | `replace_text` | `update_csv_cells` | `replace_json_scalar` | `replace_xml_text` / `replace_xml_attribute` | `replace_html_text` / `replace_html_attribute` | `replace_ipynb_cell_source` via H3 scalar lowering | `replace_epub_metadata_text` / `replace_epub_xhtml_text` via H4 lowering | routes the existing typed inner operation through the exact member chain; ZIP structure itself is read-only | `update_pdf_metadata` for existing Title/Author/Subject/Keywords + `update_pdf_link_uri` for existing safe URI links | bounded native text/style/geometry/media/table | bounded native text/style/media/table | scalar non-formula, non-merged cells |
| Identity Markdown edit | inspection-only | inspection-only | inspection-only | inspection-only | inspection-only | inspection-only | inspection-only | inspection-only for every ZIP-backed imported node | inspection-only | supported safe semantic regions | supported safe semantic regions | supported safe simple cell regions |
| Representation proof | encoding/BOM/newline | encoding/BOM + dialect/spans/terminators | encoding/BOM + pointer/span/raw token | encoding/BOM/declaration + lexical spans/namespaces | encoding/BOM/meta + lexical spans + recovery signature | encoding/BOM + source string/list shape/cardinality + notebook reread | ordered OCF inventory + member digests + OPF graph + H4 XML ownership | root/member SHA+size, ordered nested inventory, member metadata, full chain + shared global budgets | exact source prefix + root/Info/page/annotation identities + annotation topology/fingerprints + changed-object audit + strict pypdf/pdfminer/pdfplumber agreement | OPC/XML ownership | OPC/XML ownership | OPC/XML + typed cell ownership |
| Structural edits | unsupported | unsupported | unsupported | unsupported | unsupported | unsupported; notebook/cell structure and non-source state are read-only | unsupported; package graph/inventory/nav/media are read-only | unsupported; add/delete/rename/reorder/comment/compression/encryption/raw member replacement are read-only | unsupported; no new keys, annotation creation/deletion/reordering, forms, or page/object-graph edits | bounded; ambiguous structures fail closed | bounded; ambiguous structures fail closed | row/column/sheet changes unsupported |

H1-H5 together form the v0.5 text/structured-text parity tranche. H6-H8 extend v0.6
with bounded Jupyter Notebook source preservation, EPUB 3 package-preserving text
mutation and recursive ordinary ZIP composition. H9-H10 extend v0.7 with conservative
PDF Document Information mutation followed by existing URI-link target preservation.
Every tranche remains isolated behind exact source and native ownership authority.

## Fidelity details

Format-specific proof strengthens the common safety model:

- native text binds source size, encoding, BOM and newline policy;
- CSV binds delimiter, field spans/raw digests and physical row terminators;
- JSON binds RFC 6901 paths, hierarchy, lexical value spans and raw-token digests;
- XML binds namespace-aware ownership paths, exact lexical/value spans, QName and
  expanded-name identity, declaration and representation evidence;
- HTML binds recovery-aware native paths, exact lexical/value spans, original/normalized
  names, quote shape, encoding/meta declarations and an independent recovery signature;
- IPYNB binds notebook/cell semantics, source string/list representation, fixed array
  cardinality and raw source-token evidence while reusing H3 scalar lexical authority;
- EPUB binds OCF inventory/order/member metadata, package/rootfile/manifest/spine graph,
  selected text-owner evidence and untouched member SHA-256 while reusing H4 XML authority;
- ZIP binds root source authority, full recursive member-chain SHA/size evidence, ordered
  inventories, archive comments, supported member metadata, strong-package classification
  priority and transaction-wide recursion budgets;
- PDF binds strict source/catalog/Info ownership, exact source-prefix preservation, the
  incremental changed-object set, page count/object identities, complete annotation
  topology/fingerprints, immutable URI-link semantics outside `/URI`, dual pypdf/pdfminer
  metadata semantics and an independent pdfplumber URI oracle;
- CSV, JSON, XML, HTML and IPYNB prove every encoded byte segment outside requested
  targets remains exact through their native or composed preservation contracts;
- EPUB proves byte-identical content for every untouched archive member and strict graph
  equivalence around requested text-owner changes;
- ZIP proves byte-identical uncompressed content for untouched members, delegates touched
  terminal semantics to existing typed inner writers and re-reads the complete recursive
  candidate before output;
- text, CSV, JSON, XML, HTML, IPYNB, EPUB, ZIP and PDF candidates are re-read before
  destination emission according to their native or composed verifier contract;
- XML additionally rejects DTD/entity/external-resolution surfaces before mutation;
- HTML additionally rejects recovery-sensitive/foreign/template/table/rawtext/RCDATA
  mutation surfaces before mutation;
- EPUB additionally rejects unsafe/duplicate/encrypted/symlink archive members,
  unsupported ZIP compression, resource-limit violations and ambiguous package graphs;
- ZIP additionally rejects unsafe/duplicate/encrypted/symlink members, unsupported ZIP
  compression, recursion-depth/member/expanded-byte/ratio violations and ambiguous member
  classification before typed routing;
- PDF additionally rejects XMP authority, encryption, signatures/certification,
  linearization, ambiguous/missing Info ownership, non-text supported metadata values,
  `/Dest`, `/AA`, unsupported/non-text URI actions, shared or ambiguous link ownership,
  and configured source/page/metadata/annotation/URI/increment limits before caller output;
- OOXML writers start from the original package and restrict mutation to authorized
  parts/subtrees, with unrelated package members verified after writes.

## Clean Markdown vs identity Markdown

Use clean mode when Markdown is the final projection. Use identity mode only where the
format adapter advertises a reversible semantic Markdown path. Do not remove or forge
`m2w` identity comments: the importer validates projection manifest, document/node
identity, semantic digests and native locator evidence before emitting typed edits.

Native lexical text/Markdown, CSV, JSON, XML and HTML are explicit v0.5 inspection-only
identity projections. IPYNB H6 and EPUB H7 keep the same inspection-only identity
boundary. H8 preserves visible projection of supported nested content but forces
`editable_capabilities=()` for every ZIP-backed imported block, so identity Markdown
cannot become an alternate archive mutation path. H9-H10 apply the same inspection-only
boundary to PDF metadata and URI-link blocks. Direct typed native paths remain writable
only where source evidence is sufficient.

## Scope discipline and roadmap

New work should improve fidelity, compatibility, safety, tests, or reduce complexity.
The project deliberately avoids broad platform features and keeps a soft production-size
ceiling around roughly twice the upstream MarkItDown implementation.

The approved broader parity program is in
`docs/superpowers/specs/2026-09-11-markitdown-2ways-full-parity-program-design.md`.
Completed v0.5 execution documents include:

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

Current v0.6 execution documents include:

- `docs/superpowers/specs/2026-09-13-markitdown-2ways-phase-h6-ipynb-source-preservation-design.md`
- `docs/superpowers/plans/2026-09-13-phase-h6-ipynb-source-preservation-implementation.md`
- `docs/superpowers/specs/2026-09-13-markitdown-2ways-phase-h7-epub-package-preservation-design.md`
- `docs/superpowers/plans/2026-09-13-phase-h7-epub-package-preservation.md`
- `docs/superpowers/specs/2026-09-13-markitdown-2ways-phase-h8-recursive-zip-preservation-design.md`
- `docs/superpowers/plans/2026-09-13-phase-h8-recursive-zip-preservation.md`

Current v0.7 execution documents include:

- `docs/superpowers/specs/2026-09-14-markitdown-2ways-phase-h9-pdf-metadata-preservation-design.md`
- `docs/superpowers/plans/2026-09-14-markitdown-2ways-phase-h9-pdf-metadata-preservation.md`
- `docs/superpowers/specs/2026-09-14-markitdown-2ways-phase-h10-pdf-uri-link-preservation-design.md`
- `docs/superpowers/plans/2026-09-14-markitdown-2ways-phase-h10-pdf-uri-link-preservation.md`

Each tranche is complete only after its exact final branch head passes pre-commit plus
the package and OCR matrices on Python 3.10-3.13. H5 uses a separate recovery-aware
contract and leaves the one-way HTML path unchanged. H6 composes notebook-specific
authority with H3 lexical scalar patching and leaves the existing one-way IPYNB path
unchanged. H7 composes EPUB package authority with H4 XML text mutation and leaves the
existing one-way EPUB path unchanged. H8 composes ordinary ZIP preservation/routing with
the existing typed H1-H7/native package writers, leaves the one-way `ZipConverter`
unchanged. H9 adds conservative PDF Document Information incremental mutation; H10 adds
only existing safe URI-link target mutation and leaves the existing one-way `PdfConverter`
unchanged. Annotation structural editing, forms, non-URI actions, page text/image/content
mutation, outlines, new metadata keys, media-native mutation, other archive families,
remote writeback and archive structural editing remain outside the current completed
boundary.
