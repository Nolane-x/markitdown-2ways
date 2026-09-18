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
composition over supported typed inner formats, conservative PDF Document Information,
existing URI-link targets, bounded terminal plain-text AcroForm `/V` incremental
mutation, bounded existing PNG `tEXt`/`zTXt`/`iTXt` metadata value mutation, and bounded
existing JPEG Exif IFD0 `ImageDescription`/`Artist` fixed-allocation text mutation,
bounded existing MP3 ID3v1/ID3v1.1 `Title`/`Artist`/`Album` fixed-slot text mutation,
bounded existing Outlook MSG Unicode `PidTagSubject` exact-size stream mutation,
bounded existing legacy XLS BIFF8 `Number` Xnum fixed-slot mutation, and read-only
Wikipedia, Bing SERP, remote RSS/Atom and YouTube multi-input derived-snapshot parity,
plus caller-materialized Azure Document Intelligence and Content Understanding analysis
with explicit no-writeback provenance while local feed XML remains under native H4 XML
authority. It is
not an Office automation platform, workflow engine, document-management service, browser
automation layer, archive authoring suite, or general application framework.

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

## PDF terminal plain-text AcroForm value edits

Phase H11 adds one narrowly bounded AcroForm mutation: `update_pdf_text_field_value` for
an existing uniquely owned terminal plain-text `/FT /Tx` field whose dictionary is also
its `/Subtype /Widget` annotation. The field must already own text `/T` and `/V` values,
be bound to exactly one page `/Annots` slot, and have no `/Parent`, `/Kids`, `/AP`, `/A`
or `/AA` authority. The source AcroForm must be indirect, retain `/Fields`, already set
`/NeedAppearances true`, expose usable default appearance/resource authority (`/DA` plus
non-empty `/DR /Font`), and contain no XFA or calculation-order authority.

```python
from io import BytesIO

from markitdown.twoways import EditOperation, EditPrecondition
from markitdown.twoways.formats.pdf import patch_pdf, read_pdf_ir

with open("form.pdf", "rb") as source_file:
    source = source_file.read()

document = read_pdf_ir(BytesIO(source), filename="form.pdf")
field_node = next(
    node
    for node in document.nodes.values()
    if node.semantic_role == "pdf-form-text-value"
    and node.metadata.get("pdf.form_field_name") == "customer.name"
)
edit = EditOperation(
    operation_id="update-customer-name",
    type="update_pdf_text_field_value",
    target_node_id=field_node.node_id,
    precondition=EditPrecondition(expected_old_value=field_node.payload.text),
    payload={
        "field_name": "customer.name",
        "old_value": field_node.payload.text,
        "value": "Bob",
    },
)

with open("form-edited.pdf", "wb") as output_file:
    patch_pdf(document, BytesIO(source), output_file, edits=(edit,))
```

H11 keeps the exact H9/H10 incremental discipline. Routing fresh-parses the source and
revalidates field name, field object-generation identity, AcroForm identity,
page/annotation binding, field flags, `/MaxLen`, native locator and an immutable semantic
digest that masks only `/V`. The writer resolves that exact native field/widget owner,
rechecks its immutable digest immediately before mutation, and replaces only the existing
`/V` with a text string. It never calls pypdf's generic form-update API and never creates
fields, appearances, resources or AcroForm structure. Mixed H9/H10/H11 transactions are
permitted only when every edit preflights and native mutation owners are disjoint.

The candidate must keep the complete original PDF as an exact prefix. The changed-object
inventory must equal the exact union of requested H9 `/Info`, H10 URI-owner and H11 field
owners. Strict pypdf re-read preserves AcroForm/root-field topology, page/annotation
binding, sibling fields, `NeedAppearances`, field/widget semantics outside `/V`, and every
unrequested value; an independent bounded pdfminer traversal must agree on source and
candidate form values. H11 fidelity evidence explicitly records that appearance is
**viewer-regenerated** through the already-present `NeedAppearances=true` contract. That
is not an engine-independent visual-rendering guarantee.

Appearance-backed fields, hierarchical or split field/widget ownership, multiline,
password, file-select, comb and rich-text fields, checkbox/radio/list/combo/signature
controls, XFA, calculations/scripts, form creation/deletion/reparenting, `/DV`/`DA`/`DR`
mutation, annotation creation/deletion/order/geometry/style changes, page text/images or
content streams, outlines and arbitrary PDF object replacement remain read-only or out of
scope. PDF identity Markdown remains inspection-only; direct typed operations are the
only writable PDF path. The existing one-way `PdfConverter` remains unchanged.

## PNG existing text metadata value edits

Phase H12 starts v0.8 with bounded existing PNG `tEXt` mutation. Phase H13 extends that
same native-preserving boundary to existing `zTXt` and `iTXt` owners without turning the
adapter into a generic PNG metadata editor. The reader strict-parses PNG framing and CRCs,
binds source SHA-256/size, records exact chunk index/type/raw digests and persists the
resource-limit authority under which the IR was accepted.

Across `tEXt`, `zTXt`, and `iTXt`, `update_png_text_metadata` is writable only when the
keyword occurs exactly once across the complete native text-owner set and the source is
not APNG. PNG permits repeated textual keywords, so uniqueness is a 2Ways mutation-safety
rule rather than a claim about PNG validity. The writer recomputes this cross-type
ownership from a fresh authoritative parse; forged or stale capability metadata cannot
make an ambiguous owner writable.

```python
from io import BytesIO

from markitdown.twoways import EditOperation
from markitdown.twoways.formats.png import patch_png, read_png_ir

with open("card.png", "rb") as source_file:
    source = source_file.read()

document = read_png_ir(BytesIO(source), filename="card.png")
title_node = next(
    node
    for node in document.nodes.values()
    if node.metadata.get("png.keyword") == "Title"
)
edit = EditOperation(
    operation_id="update-title",
    type="update_png_text_metadata",
    target_node_id=title_node.node_id,
    payload={
        "keyword": "Title",
        "old_value": title_node.payload.text,
        "value": "Updated title",
    },
)

with open("card-edited.png", "wb") as output_file:
    patch_png(document, BytesIO(source), output_file, edits=(edit,))
```

H12-H13 never serialize or re-encode image pixels. `tEXt` values remain Latin-1. `zTXt`
values are Latin-1 behind compression method 0 and are decompressed through a hard-bounded
zlib stream. `iTXt` text is UTF-8; its compression flag/method, language tag and translated
keyword are immutable native evidence. A compressed `iTXt` owner stays compressed and an
uncompressed one stays uncompressed. H13 rejects invalid, incomplete or trailing zlib
streams, unsupported compression fields, invalid UTF-8/language tags and decompression
expansion beyond the active text limit.

After transaction-wide preflight, the writer replaces only complete native bytes for the
requested text chunks and recomputes only those chunks' length/CRC fields. It then
strict-re-reads source and candidate, requires exact chunk count/type ordering, verifies
requested semantic values plus immutable target metadata, and proves every unrequested
chunk byte-for-byte identical. Target chunk type and keyword never change. Zero edits and
semantic no-ops return the exact source bytes.

Read-time resource authority remains monotonic: a later caller may tighten limits but
cannot loosen the limits recorded in `DocumentIR`. Malformed/truncated framing, CRC
failure, trailing bytes after IEND, unknown critical chunks, invalid text ownership or
encoding, duplicate writable keywords, APNG mutation and effective resource-limit
violations all fail closed before caller output receives bytes.

H12-H13 do not add/delete/rename/reorder or convert text chunks; change compression mode;
mutate language tags or translated keywords; edit pixels, IHDR, IDAT, palette,
transparency, color profiles, EXIF or ICC data; or provide an identity-Markdown writeback
path. XMP stored inside `iTXt` is not treated as permission for generic XMP semantic
editing: H13 exposes only the bounded existing text-owner operation. The existing one-way
`ImageConverter`, including ExifTool metadata extraction and optional LLM-derived
description behavior, remains unchanged; derived descriptions are not native writable
PNG owners.

## JPEG existing Exif text value edits

Phase H14 extends v0.8 with a deliberately fixed-allocation JPEG boundary. The reader
strictly traverses JPEG markers and scan data, recognizes Exif APP1 TIFF structure, and
projects existing IFD0 `ImageDescription` (`0x010E`) and `Artist` (`0x013B`) type-2 ASCII
owners. The only writable operation is `update_jpeg_exif_text`, and only when ownership is
unique, non-overlapping, fully in bounds, and free of competing XMP/IPTC or multiple-Exif
authority.

```python
from io import BytesIO

from markitdown.twoways import EditOperation
from markitdown.twoways.formats.jpeg import patch_jpeg, read_jpeg_ir

with open("photo.jpg", "rb") as source_file:
    source = source_file.read()

document = read_jpeg_ir(BytesIO(source), filename="photo.jpg")
artist_node = next(
    node
    for node in document.nodes.values()
    if node.metadata.get("jpeg.exif_tag_name") == "Artist"
)
edit = EditOperation(
    operation_id="update-artist",
    type="update_jpeg_exif_text",
    target_node_id=artist_node.node_id,
    payload={
        "tag_id": artist_node.metadata["jpeg.exif_tag_id"],
        "old_value": artist_node.payload.text,
        "value": "Nolane",
    },
)

with open("photo-edited.jpg", "wb") as output_file:
    patch_jpeg(document, BytesIO(source), output_file, edits=(edit,))
```

H14 never serializes a JPEG or relocates TIFF data. A replacement must be strict ASCII,
contain no embedded NUL, and fit as `encoded + NUL` inside the exact existing TIFF count.
The writer zero-pads the remainder of that same allocation, leaving total file size, APP1
length, TIFF type/count/offsets, marker topology, scan bytes and every byte outside the
authorized target slot unchanged. Read-time limits are persisted and can only be tightened
at write time.

The writer fresh-parses the complete source before mutation, rechecks XMP/IPTC/multiple
Exif/duplicate/overlap policy independently of cached capability metadata, verifies exact
native locator and owner digests, preflights the whole transaction, patches an internal
same-size buffer, then strict-re-reads the candidate. The verifier requires identical
marker topology and exact bytes outside target slots; Pillow is used only in tests as an
independent Exif/pixel oracle. Structural Exif edits, tag creation/deletion/reordering,
allocation growth, TIFF relocation, sub-IFD/GPS/MakerNote/UserComment mutation, XMP/IPTC
mutation, image/scan rewriting and identity-Markdown writeback remain unsupported. The
existing one-way `ImageConverter` remains unchanged.


## MP3 existing ID3v1 fixed-slot text edits

Phase H15 extends v0.8 to MP3 with a fixed-width terminal ID3v1/ID3v1.1 boundary. The
reader requires a terminal 128-byte `TAG` record, conservatively proves MPEG Layer III
frame topology, and projects only existing `Title`, `Artist`, and `Album` fields. The
only writable operation is `update_mp3_id3v1_text`.

```python
from io import BytesIO

from markitdown.twoways import EditOperation
from markitdown.twoways.formats.mp3 import patch_mp3, read_mp3_ir

with open("song.mp3", "rb") as source_file:
    source = source_file.read()

document = read_mp3_ir(BytesIO(source), filename="song.mp3")
title_node = next(
    node
    for node in document.nodes.values()
    if node.metadata.get("mp3.id3v1_field") == "Title"
)
edit = EditOperation(
    operation_id="update-title",
    type="update_mp3_id3v1_text",
    target_node_id=title_node.node_id,
    payload={
        "field": "Title",
        "old_value": title_node.payload.text,
        "value": "Nolane",
    },
)

with open("song-edited.mp3", "wb") as output_file:
    patch_mp3(document, BytesIO(source), output_file, edits=(edit,))
```

Each writable field owns exactly 30 bytes. Replacements must be representable in
ISO-8859-1, contain no embedded NUL, and fit that allocation. Short values are NUL-padded
inside the same slot; the file length and every byte outside requested slots remain
exact. Read-time resource limits are persisted with tamper-evident authority and may only
be tightened at write time.

Before mutation, the writer revalidates source SHA/size, recomputes read-limit authority,
fresh-parses MPEG and terminal metadata, rechecks native locators and slot/tag digests,
and rejects forged cached capabilities. ID3v2, APEv2, Lyrics3, noncanonical ID3v1
padding, free-format/unsupported/unproven MPEG topology and malformed terminal metadata
remain read-only. H15 never creates or deletes tags and never writes Year, Comment,
Track, Genre, MPEG audio frames, WAV, M4A or MP4 metadata. The existing one-way
`AudioConverter` remains unchanged.


## AudioConverter local-derived snapshot parity

Phase H24 adds the read-only derived semantics of the unchanged one-way
`AudioConverter` without weakening H15. H15 remains the native MP3 ID3v1/ID3v1.1
mutation authority; H24 is a separate enrichment view for exact caller-materialized
one-way Markdown over the complete default WAV/MP3/M4A/MP4 acceptance surface.

```python
from io import BytesIO

from markitdown._stream_info import StreamInfo
from markitdown.twoways import AudioConverterSnapshot, read_audio_snapshot_ir

source = b"...exact audio bytes..."
document = read_audio_snapshot_ir(
    BytesIO(source),
    stream_info=StreamInfo(extension=".wav", mimetype="audio/x-wav"),
    snapshot=AudioConverterSnapshot(
        content="Title: Demo\n\n### Audio Transcript:\nHello world",
        provider="caller-materialized",
    ),
)
```

The H24 production reader never executes exiftool, transcription, ffmpeg, network or
subprocess behavior. It mirrors the current one-way acceptance rules and the exact
transcription branch order, including conflict cases and the distinction between MIME
prefix acceptance and exact-MIME transcription routing. Source bytes and materialized
Markdown are independently digested. The root is `CapabilityState.DERIVED` with reason
`audio.output.not_native_writable`, has no native locator, and exposes no writer.
WAV/M4A/MP4 therefore gain semantic parity only, not native mutation. For MP3, H24 can
coexist with H15 over the same source digest but never inherits H15's native locators or
edit capability.

## Outlook MSG Unicode Subject exact-size edits

Phase H16 extends v0.8 to Outlook MSG with one deliberately narrow MAPI/CFB boundary:
the already-existing top-level Unicode `PidTagSubject` (`0x0037001F`) stream. The only
writable operation is `update_msg_subject_text`, and a replacement must encode to exactly
the same UTF-16LE byte length as the existing Subject stream.

```python
from io import BytesIO

from markitdown.twoways import EditOperation
from markitdown.twoways.formats.msg import patch_msg, read_msg_ir

with open("message.msg", "rb") as source_file:
    source = source_file.read()

document = read_msg_ir(BytesIO(source), filename="message.msg")
subject_node = next(
    node
    for node in document.nodes.values()
    if node.metadata.get("msg.property_tag") == 0x0037001F
)
edit = EditOperation(
    operation_id="update-subject",
    type="update_msg_subject_text",
    target_node_id=subject_node.node_id,
    payload={
        "property_tag": 0x0037001F,
        "old_value": subject_node.payload.text,
        "value": "Nolane",
    },
)

with open("message-edited.msg", "wb") as output_file:
    patch_msg(document, BytesIO(source), output_file, edits=(edit,))
```

H16 strictly parses bounded CFB v3/v4 header, DIFAT/FAT, directory, MiniFAT/root
mini-stream and MAPI property authority. Writable Subject ownership requires exactly one
top-level `__substg1.0_0037001F` stream, exactly one matching property entry, and exactly
one `PidTagStoreSupportMask` (`0x340D0003`) carrying `STORE_UNICODE_OK`. ANSI Subject,
`PidTagSubjectPrefix`, `PidTagNormalizedSubject`, invalid UTF-16, conflicting/duplicate
owners, malformed/aliased CFB chains and resource-limit violations remain read-only.

The writer verifies source SHA/size and tamper-evident read-time limits, fresh-parses the
complete authoritative MSG, rechecks native locator/property/directory/chain/range
evidence, and scatter-writes only the existing Subject stream's exact physical ranges.
It never changes the MAPI property stream, directory entries, FAT/DIFAT/MiniFAT, stream
allocation or total file length. The verifier strict-reparses the candidate and proves
every byte outside the authorized Subject physical ranges is unchanged. `olefile` is
used only as an independent read-only differential oracle in tests; the existing one-way
`OutlookMsgConverter` remains unchanged.

H16 does not resize/create/delete streams or mutate sender, recipients, body/HTML/RTF,
attachments, named properties, embedded messages, ANSI Subject, subject-prefix/
normalized-subject companions or general CFB structure. Identity-Markdown writeback
remains inspection-only.


## Legacy XLS BIFF8 NUMBER fixed-slot edits

Phase H17 extends v0.8 to classic `.xls` with one intentionally narrow BIFF8 boundary:
existing worksheet `Number` (`0x0203`) records. The existing `update_sheet_cells`
operation may replace only the current 8-byte little-endian IEEE-754 `Xnum` payload of
an already-owned NUMBER cell.

```python
from io import BytesIO

from markitdown.twoways import EditOperation
from markitdown.twoways.formats.xls import patch_xls, read_xls_ir

with open("legacy.xls", "rb") as source_file:
    source = source_file.read()

document = read_xls_ir(BytesIO(source), filename="legacy.xls")
sheet = document.nodes[document.canvases[0].root_node_ids[0]]
cell = next(cell for cell in sheet.payload.cells if cell.metadata["xls.present"])
edit = EditOperation(
    operation_id="update-number",
    type="update_sheet_cells",
    target_node_id=sheet.node_id,
    payload={
        "cells": [
            {
                "row": cell.row,
                "column": cell.column,
                "old_value": cell.metadata["xls.typed_value"],
                "value": 42.5,
            }
        ]
    },
)

with open("legacy-edited.xls", "wb") as output_file:
    patch_xls(document, BytesIO(source), output_file, edits=(edit,))
```

H17 strictly parses bounded CFB header/DIFAT/FAT/directory/MiniFAT/root-mini-stream
authority and a conservative BIFF8 record topology. Writable authority requires a unique
top-level `Workbook` stream, BIFF8 globals/sheet BOFs, a unique NUMBER owner for the
requested coordinate, finite source values and no workbook-global blocker. The row,
column, XF index, record type/size/order, BoundSheet ownership, CFB allocation and file
length are immutable.

Replacement values must be int/float scalars, not bool, finite, and exactly representable
under the H17 binary64 contract. H17 never converts values to RK/MulRk and never creates,
deletes, resizes or relocates BIFF/CFB records or streams. `FilePass`, any `Formula`
record, competing `Book` authority, duplicate cell ownership, non-finite NUMBER owners,
unsupported sheet/dialog modes and malformed/aliased container topology make mutation
read-only.

Before emission, the writer verifies source SHA/size and tamper-evident read-time limits,
fresh-parses CFB+BIFF, rebinds sheet/cell native evidence and preflights the complete edit
set for unique coordinates and disjoint physical ranges. The verifier strict-re-reads the
candidate and requires exact CFB/BIFF topology, semantic NUMBER readback and byte identity
outside authorized 8-byte Xnum ranges. Candidate verification is mandatory and cannot be
disabled. `xlrd` is used only as an independent read-only differential oracle in tests;
the existing one-way `XlsConverter` remains unchanged. Identity-Markdown writeback and
all non-NUMBER or structural XLS edits remain unsupported.


## Wikipedia remote-derived snapshot parity

Phase H18 starts v0.9 with a Class-D source adapter for an already-materialized Wikipedia
HTML snapshot. H18 does **not** fetch the URL. The caller supplies exact snapshot bytes
plus `StreamInfo.url`; the reader validates current `WikipediaConverter` ownership,
derives the same normalized Markdown as the public one-way stream path, and records the
remote URI, snapshot SHA-256/size, converter identity/blob and derived Markdown
SHA-256/UTF-8 size in versioned evidence.

```python
from io import BytesIO

from markitdown._stream_info import StreamInfo
from markitdown.twoways import (
    capabilities_for_node,
    read_wikipedia_snapshot_ir,
)

with open("wikipedia-snapshot.html", "rb") as source_file:
    snapshot = source_file.read()
document = read_wikipedia_snapshot_ir(
    BytesIO(snapshot),
    stream_info=StreamInfo(
        url="https://en.wikipedia.org/wiki/Microsoft",
        mimetype="text/html",
        extension=".html",
        filename="Microsoft.html",
        charset="utf-8",
    ),
)

node = document.nodes[document.root_node_ids[0]]
print(node.payload.text)
print(capabilities_for_node(node).for_operation("replace_text"))
```

The H18 root text node is explicitly `CapabilityState.DERIVED` with reason
`remote.source.not_native_writable`. Neither the canvas nor node receives a native
locator. H18 has no writer, no remote mutation operation and no identity-Markdown
writeback path. The supplied URL is provenance rather than a fetch instruction, and the
snapshot digest proves only the bytes that were analyzed—not freshness of Wikipedia.

`RemoteDerivedLimits` bounds both materialized source bytes and derived Markdown UTF-8
bytes. Invalid/non-Wikipedia origins, URL user-info, unsupported URL schemes, converter
ownership mismatch or budget exhaustion fail closed. The 2Ways H18 module imports no
network/process client and invokes the existing `WikipediaConverter` only on a private
`BytesIO`. The one-way `WikipediaConverter` and MarkItDown HTTP behavior remain
unchanged. H20+ may reuse this remote-derived evidence pattern, but sources with
additional service derivation such as YouTube transcripts and Azure analyzers require
their own provenance contracts.


## Bing SERP remote-derived snapshot parity

Phase H19 extends the v0.9 Class-D source-adapter program to an already-materialized Bing
search-results HTML snapshot. H19 does **not** issue a Bing search or fetch the URL. The
caller supplies exact snapshot bytes plus an accepted Bing SERP `StreamInfo.url`; the
reader requires existing `BingSerpConverter` ownership and derives the same normalized
Markdown as the public one-way stream path.

```python
from io import BytesIO

from markitdown._stream_info import StreamInfo
from markitdown.twoways import (
    capabilities_for_node,
    read_bing_serp_snapshot_ir,
)

snapshot = b"<html>...already-materialized Bing SERP...</html>"
document = read_bing_serp_snapshot_ir(
    BytesIO(snapshot),
    stream_info=StreamInfo(
        url="https://www.bing.com/search?q=markitdown",
        mimetype="text/html",
        extension=".html",
        filename="bing.html",
        charset="utf-8",
    ),
)

node = document.nodes[document.root_node_ids[0]]
print(node.payload.text)
print(capabilities_for_node(node).for_operation("replace_text"))
```

The H19 root is explicitly `DERIVED` with reason
`remote.source.not_native_writable`. Source URI/SHA-256/size, converter identity/blob
and derived Markdown SHA-256/UTF-8 size are recorded in the same versioned remote
snapshot evidence envelope introduced by H18. Neither node nor canvas receives a native
locator, and there is no Bing writer, search mutation operation or identity-Markdown
writeback path.

H19 reuses H18's bounded source capture, derived capability and Markdown normalization
helpers without changing the H18 Wikipedia reader body. Wrong schemes, Bing lookalike
hosts, credential-bearing URLs, non-search paths, converter ownership mismatches and
source/Markdown budget violations fail closed. The 2Ways remote reader performs no
network or subprocess I/O; `BingSerpConverter` runs only over a private `BytesIO`.
The one-way Bing converter, converter registry and MarkItDown fetching behavior remain
unchanged. RSS/Atom is intentionally deferred to H20 because local XML authority and
remote-derived feed provenance require a separate contract.


## Remote RSS/Atom snapshot parity with local XML separation

Phase H20 extends the v0.9 Class-D source-adapter program to already-materialized remote
RSS and Atom snapshots. The caller supplies exact feed bytes plus an explicit HTTP/HTTPS
origin; H20 never dereferences that URL, follows redirects, polls a feed, resolves DNS or
opens a socket.

```python
from io import BytesIO

from markitdown._stream_info import StreamInfo
from markitdown.twoways import (
    capabilities_for_node,
    read_remote_feed_snapshot_ir,
)

snapshot = b"<rss version='2.0'>...</rss>"
document = read_remote_feed_snapshot_ir(
    BytesIO(snapshot),
    stream_info=StreamInfo(
        url="https://example.com/feed.xml",
        mimetype="application/rss+xml",
        extension=".xml",
        filename="feed.xml",
        charset="utf-8",
    ),
)

node = document.nodes[document.root_node_ids[0]]
print(node.payload.text)
print(capabilities_for_node(node).for_operation("replace_text"))
```

Remote authority is deliberately separate from native XML authority. The same RSS/Atom
bytes read through H4 `read_xml_ir` remain native XML with lexical locators and the
existing bounded XML writer where H4 permits mutation. H20 requires an explicit valid
HTTP/HTTPS origin plus successful ownership and conversion by the existing
`RssConverter`; a local feed with no URL is rejected by H20 rather than silently
downgraded to derived content.

The H20 root is `CapabilityState.DERIVED` with reason
`remote.source.not_native_writable`. Source URI/SHA-256/size, `RssConverter`
identity/blob and derived Markdown SHA-256/UTF-8 size are persisted in the same
versioned remote-snapshot evidence envelope used by H18/H19. The node and canvas have no
native locator, no writer is registered, and there is no remote feed mutation or
identity-Markdown writeback path.

Both RSS and Atom must match the existing public one-way `MarkItDown.convert_stream`
title/Markdown semantics exactly. `RemoteDerivedLimits` bounds materialized source and
derived Markdown bytes, source capture never uses an unbounded read, and malformed
origins, credential-bearing URLs, generic non-feed XML, malformed feed bytes or budget
violations fail closed. H20 changes neither H4 XML production files nor
`_rss_converter.py`; the URL is provenance only, not a fetch instruction.


## YouTube multi-input derived-snapshot parity

Phase H21 extends the v0.9 Class-D program to YouTube without turning 2Ways into a
network client. The caller supplies an already-materialized YouTube HTML snapshot and,
optionally, a separately materialized transcript. These inputs are independent
authorities: absence of a transcript means only that no transcript was supplied to H21;
it is **not** evidence that YouTube has no transcript or that a remote transcript service
is unavailable.

```python
from io import BytesIO

from markitdown._stream_info import StreamInfo
from markitdown.twoways import (
    YouTubeTranscriptSnapshot,
    read_youtube_snapshot_ir,
)

html = b"<html>...already-materialized YouTube page...</html>"
document = read_youtube_snapshot_ir(
    BytesIO(html),
    stream_info=StreamInfo(
        url="https://www.youtube.com/watch?v=abc123DEF45",
        mimetype="text/html",
        extension=".html",
        filename="video.html",
        charset="utf-8",
    ),
    transcript=YouTubeTranscriptSnapshot(
        video_id="abc123DEF45",
        language_code="en",
        parts=("already", "materialized", "transcript"),
        provider="caller-snapshot",
    ),
)
```

The HTML source descriptor binds only the supplied HTML URI, SHA-256 and byte size.
Transcript provenance is recorded separately with video ID, language code, provider,
ordered part count, joined UTF-8 SHA-256 and UTF-8 size. A supplied transcript must match
the video ID derived from the accepted YouTube URL. The transcript changes derived
document identity but never changes the HTML source digest or pretends to be native HTML
ownership.

H21 reproduces the current local `YouTubeConverter` HTML projection and its one-space
transcript joining rule without importing or calling `youtube_transcript_api` in
production. Differential tests compare H21 against the unchanged one-way converter using
only deterministic in-memory transcript fakes. Production H21 performs no fetch, retry,
sleep, DNS/socket, browser automation or subprocess action.

`YouTubeDerivedLimits` independently bounds HTML bytes, transcript UTF-8 bytes and final
Markdown UTF-8 bytes. Source capture is bounded, URL authority rejects credentials,
lookalike hosts and malformed/explicit ports, and the root remains
`CapabilityState.DERIVED` with reason `remote.source.not_native_writable`. There is no
YouTube writer, transcript edit operation, remote writeback path or identity-Markdown
writeback path. The existing one-way `YouTubeConverter` remains unchanged; H22 is the
next planned derived-analysis boundary for Azure Document Intelligence.


## Document Intelligence derived-analysis parity

Phase H22 extends the v0.9 Class-D program to the existing one-way
`DocumentIntelligenceConverter` without making 2Ways an Azure client. The caller
supplies the exact source bytes plus an already-materialized analysis snapshot; H22
binds those two authorities separately and derives visible Markdown locally.

```python
from io import BytesIO

from markitdown._stream_info import StreamInfo
from markitdown.twoways import (
    DocumentIntelligenceAnalysisSnapshot,
    read_document_intelligence_analysis_ir,
)

source = b"%PDF-1.7..."
document = read_document_intelligence_analysis_ir(
    BytesIO(source),
    stream_info=StreamInfo(
        mimetype="application/pdf",
        extension=".pdf",
        filename="report.pdf",
    ),
    analysis=DocumentIntelligenceAnalysisSnapshot(
        content="# Report\n<!--service note-->\nVisible body",
        provider="caller-materialized",
        model_id="prebuilt-layout",
        content_format="markdown",
    ),
)
```

H22 mirrors the default file surface of the current one-way converter (DOCX, PPTX,
XLSX, PDF, JPEG, PNG, BMP and TIFF) but does not claim native ownership of those file
formats. Existing native 2Ways readers remain the only authority for native mutation.
The analysis snapshot is explicitly derived evidence and cannot grant a native locator.

Visible Markdown applies only the existing converter's final local semantic transform:
HTML comments are removed from the caller-supplied analysis content. Source SHA/size,
analysis-content SHA/UTF-8 size, provider/model/content-format descriptors, derived
Markdown SHA/UTF-8 size and the protected one-way converter blob are persisted in
`twoways.document_intelligence_analysis.v1`.

`DocumentIntelligenceDerivedLimits` independently bounds source, analysis content and
final Markdown. Source reads are bounded. Production H22 imports no Azure SDK, loads no
credential, creates no client/poller, and performs no network, retry, sleep, browser or
subprocess action. The root is `CapabilityState.DERIVED` with reason
`analysis.output.not_native_writable`; no H22 writer, Azure writeback or
identity-Markdown writeback path exists. The one-way
`_doc_intel_converter.py` remains unchanged.

## Content Understanding derived-analysis parity

Phase H23 closes the remaining Azure reader-bridge gap in the v0.9 Class-D program.
The caller supplies exact source bytes plus the exact already-materialized string from
the one-way Content Understanding `to_llm_input(result)` stage. Production H23 does
not construct an Azure client, resolve credentials, submit or poll analysis, call
`get_analyzer()`, invoke `to_llm_input()`, retry, sleep, open sockets or spawn a process.

H23 covers the default auto-routing path only. It independently mirrors the current
one-way extension/MIME routing for documents, email, images, video and audio; extension
authority wins over conflicting MIME, MIME parameters are stripped, current aliases are
canonicalized, and the resolved file type determines modality, default analyzer and
canonical payload content type. The supplied snapshot is rejected unless its analyzer
ID and content type exactly match that independently derived route. Custom analyzers
remain outside H23 because resolving an unknown analyzer's base modality may require a
remote SDK `get_analyzer()` call.

```python
from io import BytesIO

from markitdown._stream_info import StreamInfo
from markitdown.twoways import (
    ContentUnderstandingAnalysisSnapshot,
    read_content_understanding_analysis_ir,
)

source = b"%PDF-1.7..."
document = read_content_understanding_analysis_ir(
    BytesIO(source),
    stream_info=StreamInfo(
        extension=".pdf",
        mimetype="application/pdf",
        filename="report.pdf",
    ),
    analysis=ContentUnderstandingAnalysisSnapshot(
        content="---\ncontentType: document\n---\n# Report",
        provider="caller-materialized",
        analyzer_id="prebuilt-documentSearch",
        content_type="application/pdf",
    ),
)
```

Source bytes and materialized analysis are independently digested. The H23 root is
`CapabilityState.DERIVED` with reason `analysis.output.not_native_writable`, has no
native locator, and exposes no writer or identity-Markdown writeback path.
`ContentUnderstandingDerivedLimits` independently bounds source and materialized UTF-8
analysis bytes, and source reads are bounded. Provenance records the resolved file type,
modality, verified analyzer/content type, converter identity/blob, and explicit
no-network/no-SDK/no-credential/no-`to_llm_input` evidence. The unchanged one-way
`_cu_converter.py` remains the routing/semantic regression authority.

## Outlook MSG derived semantic parity

Phase H26 separates the unchanged one-way `OutlookMsgConverter` human-readable message
projection from H16's deliberately narrow native Subject authority. The caller supplies
exact MSG bytes plus already-materialized sender, recipients, subject and body values.
H26 reproduces the exact one-way `# Email Message` scaffold, fixed
`From`/`To`/`Subject` ordering, truthiness omission, `## Content` section and final
`.strip()`.

The materialized subject is also exposed as the derived document title, matching the
one-way converter result. Source bytes and each semantic field are independently
digested; `None` and an empty string remain distinct provenance states even though both
are omitted by the visible projection.

Production H26 performs no OLE parsing, code-page decoding, charset detection, network
or process action. Its root is `CapabilityState.DERIVED` with reason
`msg.output.not_native_writable`, has no native locator and exposes no writer. H16
remains the only native MSG mutation path and still permits only its proven exact-size
top-level Unicode `PidTagSubject` replacement.

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

| Area | Text / Markdown H1 | CSV H2 | JSON H3 | XML H4 | HTML H5 | IPYNB H6 | EPUB H7 | ZIP H8 | PDF H9-H11 | PNG H12-H13 | JPEG H14 | MP3 H15 | MSG H16 | XLS H17 | Derived H18-H26 | PPTX | DOCX | XLSX tranche one |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Read into `DocumentIR` | exact decoded lexical source + representation | lexical field spans + table semantics | strict spans + RFC 6901 hierarchy | strict XML owners + namespace identity | lexical owners + independent recovery signature | notebook/cell source semantics + lexical representation | OCF package graph + selected OPF/XHTML owners | ordered recursive inventory + namespaced supported inner IR | strict PDF source + existing `/Info` text owners + URI-link topology + bounded AcroForm text-field evidence | strict PNG chunk topology + existing `tEXt`/`zTXt`/`iTXt` owners + bounded compressed-text/read-time resource authority | strict JPEG marker/scan topology + bounded Exif APP1/TIFF IFD0 text-owner evidence | terminal ID3v1/1.1 owners + conservative MPEG Layer III topology + competing-metadata authority | bounded CFB v3/v4 topology + top-level Unicode `PidTagSubject`/MAPI authority | bounded CFB v3/v4 + BIFF8 workbook/sheet topology + existing NUMBER owners | materialized Wikipedia/Bing SERP/feed/YouTube snapshots + optional YouTube transcript + source/analysis-separated Azure bridges + H24 AudioConverter materialized Markdown + H25 ImageConverter metadata/caption materializations + H26 Outlook MSG semantic materialization | slides/groups/notes/text/media/tables | body/headers/footers/text/media/tables | worksheets and typed cells |
| Primary patch | `replace_text` | `update_csv_cells` | `replace_json_scalar` | `replace_xml_text` / `replace_xml_attribute` | `replace_html_text` / `replace_html_attribute` | `replace_ipynb_cell_source` via H3 scalar lowering | `replace_epub_metadata_text` / `replace_epub_xhtml_text` via H4 lowering | routes the existing typed inner operation through the exact member chain; ZIP structure itself is read-only | `update_pdf_metadata` + `update_pdf_link_uri` + `update_pdf_text_field_value` for existing H11-safe terminal plain-text fields | `update_png_text_metadata` for an existing cross-type uniquely owned `tEXt`/`zTXt`/`iTXt` value | `update_jpeg_exif_text` for existing unique safe IFD0 `ImageDescription`/`Artist` type-2 allocations | `update_mp3_id3v1_text` for existing `Title`/`Artist`/`Album` 30-byte slots | `update_msg_subject_text` for one existing top-level Unicode Subject stream with exact encoded length | `update_sheet_cells` for existing unique BIFF8 NUMBER Xnum slots only | none; `replace_text` is explicit DERIVED/read-only | bounded native text/style/geometry/media/table | bounded native text/style/media/table | scalar non-formula, non-merged cells |
| Identity Markdown edit | inspection-only | inspection-only | inspection-only | inspection-only | inspection-only | inspection-only | inspection-only | inspection-only for every ZIP-backed imported node | inspection-only | inspection-only | inspection-only | inspection-only | inspection-only | inspection-only | inspection-only | supported safe semantic regions | supported safe semantic regions | supported safe simple cell regions |
| Representation proof | encoding/BOM/newline | encoding/BOM + dialect/spans/terminators | encoding/BOM + pointer/span/raw token | encoding/BOM/declaration + lexical spans/namespaces | encoding/BOM/meta + lexical spans + recovery signature | encoding/BOM + source string/list shape/cardinality + notebook reread | ordered OCF inventory + member digests + OPF graph + H4 XML ownership | root/member SHA+size, ordered nested inventory, member metadata, full chain + shared global budgets | exact source prefix + root/Info/page/annotation/AcroForm identities + annotation/form topology/fingerprints + immutable target digests + exact changed-object audit + pypdf/pdfminer/pdfplumber agreement | source SHA/size + monotonic read-time limits + chunk order/type/CRC/raw digests + bounded zlib decode + immutable compression/language metadata + exact unrequested chunk bytes | source SHA/size + monotonic limits + marker/segment topology + TIFF owner/type/count/offset/slot digests + exact outside-slot bytes | source SHA/size + tamper-evident monotonic limits + MPEG frame/terminal metadata topology + ID3v1/slot digests + exact outside-slot bytes | source SHA/size + tamper-evident limits + CFB FAT/DIFAT/MiniFAT/directory topology + MAPI entry/stream/chain/range digests + exact outside-range bytes | source SHA/size + tamper-evident limits + CFB allocation/directory authority + BIFF record/sheet/NUMBER owner digests + exact outside-slot bytes | remote/snapshot evidence through H21; H22 separately binds Document Intelligence source/analysis/Markdown evidence; H23 binds Content Understanding source/materialized-output plus verified default routing; H24 independently binds local audio source/materialized Markdown plus exact AudioConverter acceptance/transcription-route evidence without optional dependency execution; H25 independently binds image source, ordered metadata materialization and optional caption materialization while reproducing exact ImageConverter ordering/strip semantics without ExifTool or LLM execution; H26 independently binds MSG source plus materialized From/To/Subject/body while reproducing exact one-way message scaffold/title semantics without OLE or charset runtime dependencies | OPC/XML ownership | OPC/XML ownership | OPC/XML + typed cell ownership |
| Structural edits | unsupported | unsupported | unsupported | unsupported | unsupported | unsupported; notebook/cell structure and non-source state are read-only | unsupported; package graph/inventory/nav/media are read-only | unsupported; add/delete/rename/reorder/comment/compression/encryption/raw member replacement are read-only | unsupported; no new metadata keys, annotation structure, form structure, page/object-graph edits, appearance regeneration or non-H11 form controls | unsupported; existing unique text value only, with chunk type/keyword/compression mode/language metadata immutable | unsupported; fixed-allocation existing text value only, with APP1/TIFF topology immutable | unsupported; fixed terminal slots only; ID3v2/APEv2/Lyrics3/audio frames are read-only | unsupported; exact-size existing Unicode Subject only; CFB/MAPI topology and all other properties are read-only | unsupported; NUMBER Xnum value bytes only; record/stream/container topology immutable | unsupported; no remote/native writer or writeback | bounded; ambiguous structures fail closed | bounded; ambiguous structures fail closed | row/column/sheet changes unsupported |

H1-H5 together form the v0.5 text/structured-text parity tranche. H6-H8 extend v0.6
with bounded Jupyter Notebook source preservation, EPUB 3 package-preserving text
mutation and recursive ordinary ZIP composition. H9-H11 extend v0.7 with conservative
PDF Document Information mutation, existing URI-link target preservation, and bounded
existing terminal plain-text AcroForm value mutation. H12-H17 extend v0.8 with conservative native preservation across bounded PNG text
owners, fixed-allocation JPEG Exif IFD0 text owners, fixed-slot MP3 ID3v1 text owners,
one exact-size Outlook MSG Unicode Subject owner, and existing legacy XLS BIFF8 NUMBER
Xnum slots. Every tranche remains isolated
behind exact source and native ownership authority. H18-H23 complete the planned v0.9
Class-D input-parity surface with read-only derived parity for Wikipedia, Bing SERP,
RSS/Atom, YouTube and the two caller-materialized Azure analysis bridges. Materialized
inputs are evidence, visible Markdown remains explicitly derived, and none of these
adapters claims remote/native writeback authority. H21 separately binds YouTube HTML and
transcript materializations; H22 separately binds Document Intelligence source and
analysis output; H23 additionally verifies Content Understanding default routing before
accepting materialized output.

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
  incremental changed-object set, page count/object identities, complete annotation and
  AcroForm topology/fingerprints, immutable URI-link semantics outside `/URI`, immutable
  H11 field/widget semantics outside `/V`, NeedAppearances/default-appearance authority,
  dual pypdf/pdfminer metadata semantics, an independent pdfplumber URI oracle, and an
  independent bounded pdfminer form-value oracle;
- H11 PDF form fidelity proves semantic `/V` mutation and exact native-owner preservation
  while explicitly delegating visual appearance regeneration to viewers; it does not
  claim engine-independent visual rendering equivalence;
- PNG binds source SHA/size, monotonic read-time resource limits, exact chunk topology,
  CRC/raw owner evidence, cross-type unique writable `tEXt`/`zTXt`/`iTXt` ownership,
  bounded zlib authority, immutable `iTXt` compression/language metadata and
  byte-identical preservation of every unrequested chunk;
- JPEG H14 binds source SHA/size, monotonic read-time resource limits, exact marker/scan
  topology, Exif APP1/TIFF byte order and IFD0 entry identity, fixed value allocation,
  owner/slot digests, and byte-identical preservation of every byte outside requested
  value slots; Pillow independently checks decoded pixels and semantic Exif readback;
- MP3 H15 binds source SHA/size, tamper-evident monotonic read-time limits, conservative
  MPEG Layer III frame topology, terminal metadata classification, exact ID3v1/slot
  digests and fixed 30-byte ownership; every byte outside requested slots remains exact,
  with Mutagen used only as an optional read-only semantic oracle in tests;
- MSG H16 binds source SHA/size, tamper-evident monotonic read-time limits, bounded CFB
  header/DIFAT/FAT/MiniFAT/directory/root-mini-stream topology, exact top-level MAPI
  property-entry and Unicode Subject stream ownership, physical chain/range evidence and
  byte-identical preservation outside the authorized Subject ranges; `olefile`
  independently checks stream inventory, Subject semantics and non-subject stream bytes;
- XLS H17 binds source SHA/size, tamper-evident monotonic read-time limits, bounded CFB
  allocation/directory ownership, BIFF8 global/sheet record topology, immutable
  row/column/XF/record identity and exact 8-byte NUMBER Xnum physical ranges; every byte
  outside requested slots remains exact, with `xlrd` used only as an independent
  read-only semantic oracle in tests;
- Wikipedia H18 binds the supplied remote URI, exact materialized snapshot SHA/size,
  one-way converter identity/blob and derived Markdown digest/UTF-8 size; the single
  semantic text node is explicitly DERIVED, has no native locator, performs no network
  I/O inside 2Ways and exposes no remote/native writer;
- YouTube H21 separately binds HTML URI/SHA/size/video identity and optional caller-
  materialized transcript video/language/provider/part-count/SHA/size evidence; the
  production reader performs no transcript-service/network/process action, and offline
  differential tests protect the unchanged one-way YouTube semantics;
- Document Intelligence H22 separately binds exact source SHA/size and caller-materialized
  analysis provider/model/content SHA/size, then applies only the unchanged one-way
  comment-removal transform; production imports no Azure SDK, credentials or network
  client, and the analysis node has no native locator or writer;
- CSV, JSON, XML, HTML and IPYNB prove every encoded byte segment outside requested
  targets remains exact through their native or composed preservation contracts;
- EPUB proves byte-identical content for every untouched archive member and strict graph
  equivalence around requested text-owner changes;
- ZIP proves byte-identical uncompressed content for untouched members, delegates touched
  terminal semantics to existing typed inner writers and re-reads the complete recursive
  candidate before output;
- text, CSV, JSON, XML, HTML, IPYNB, EPUB, ZIP, PDF, PNG, JPEG, MP3, MSG and XLS candidates are re-read
  before destination emission according to their native or composed verifier contract;
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
  unsupported URI actions/ownership, malformed or ambiguous AcroForm trees/bindings,
  unsupported field modes, appearance-backed or action-bearing form fields, XFA,
  calculations, invalid appearance authority, and configured source/page/metadata/
  annotation/URI/form/increment limits before caller output;
- PNG additionally rejects malformed/truncated framing, CRC mismatch, trailing bytes,
  unsupported critical chunks, invalid text ownership/encoding, unsupported compression
  fields, invalid UTF-8/language tags, malformed/incomplete/trailing zlib streams,
  decompression-limit violations, duplicate writable keywords, APNG mutation and
  effective read-time/writer resource-limit violations;
- JPEG H14 additionally rejects malformed marker/scan/TIFF structure, multiple Exif
  segments, XMP/IPTC dual authority, duplicate target tags, overlapping allocations,
  unsupported type/encoding, stale or forged owner evidence, allocation growth and
  effective read-time/writer resource-limit violations;
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
cannot become an alternate archive mutation path. H9-H11 apply the same inspection-only
boundary to PDF metadata, URI-link and form-value blocks. H12-H13 keep PNG native text
identity projection inspection-only; H14 applies the same inspection-only boundary to
JPEG Exif text owners; H15-H17 apply it to MP3 ID3v1, MSG Subject and legacy XLS NUMBER owners.
H18-H26 derived text is likewise inspection-only and explicitly derived; these nodes
never gain native locators or writers. H21's optional transcript plus H22/H23 analysis snapshots are provenance, not writable
native owners. Direct typed native paths remain
writable only where source evidence is sufficient.

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
- `docs/superpowers/plans/2026-09-13-markitdown-2ways-phase-h8-recursive-zip-preservation.md`

Current v0.7 execution documents include:

- `docs/superpowers/specs/2026-09-14-markitdown-2ways-phase-h9-pdf-metadata-preservation-design.md`
- `docs/superpowers/plans/2026-09-14-markitdown-2ways-phase-h9-pdf-metadata-preservation.md`
- `docs/superpowers/specs/2026-09-14-markitdown-2ways-phase-h10-pdf-uri-link-preservation-design.md`
- `docs/superpowers/plans/2026-09-14-markitdown-2ways-phase-h10-pdf-uri-link-preservation.md`
- `docs/superpowers/specs/2026-09-14-markitdown-2ways-phase-h11-pdf-acroform-text-value-preservation-design.md`
- `docs/superpowers/plans/2026-09-14-markitdown-2ways-phase-h11-pdf-acroform-text-value-preservation-implementation.md`

Current v0.8 execution documents include:

- `docs/superpowers/specs/2026-09-16-markitdown-2ways-phase-h12-png-text-metadata-preservation-design.md`
- `docs/superpowers/plans/2026-09-16-markitdown-2ways-phase-h12-png-text-metadata-preservation-implementation.md`
- `docs/superpowers/specs/2026-09-17-markitdown-2ways-phase-h13-png-compressed-international-text-preservation-design.md`
- `docs/superpowers/plans/2026-09-17-markitdown-2ways-phase-h13-png-compressed-international-text-preservation-implementation.md`
- `docs/superpowers/specs/2026-09-17-markitdown-2ways-phase-h14-jpeg-exif-inplace-text-preservation-design.md`
- `docs/superpowers/plans/2026-09-17-markitdown-2ways-phase-h14-jpeg-exif-inplace-text-preservation-implementation.md`
- `docs/superpowers/specs/2026-09-17-markitdown-2ways-phase-h15-mp3-id3v1-fixed-slot-preservation-design.md`
- `docs/superpowers/plans/2026-09-17-markitdown-2ways-phase-h15-mp3-id3v1-fixed-slot-preservation-implementation.md`
- `docs/superpowers/specs/2026-09-18-markitdown-2ways-phase-h16-msg-unicode-subject-fixed-stream-preservation-design.md`
- `docs/superpowers/plans/2026-09-18-markitdown-2ways-phase-h16-msg-unicode-subject-fixed-stream-preservation-implementation.md`
- `docs/superpowers/specs/2026-09-18-markitdown-2ways-phase-h17-xls-biff8-number-fixed-slot-preservation-design.md`
- `docs/superpowers/plans/2026-09-18-markitdown-2ways-phase-h17-xls-biff8-number-fixed-slot-preservation-implementation.md`
Current v0.9 execution documents include:

- `docs/superpowers/specs/2026-09-18-markitdown-2ways-phase-h18-wikipedia-remote-derived-snapshot-parity-design.md`
- `docs/superpowers/plans/2026-09-18-markitdown-2ways-phase-h18-wikipedia-remote-derived-snapshot-parity-implementation.md`
- `docs/superpowers/specs/2026-09-18-markitdown-2ways-phase-h19-bing-serp-remote-derived-snapshot-parity-design.md`
- `docs/superpowers/plans/2026-09-18-markitdown-2ways-phase-h19-bing-serp-remote-derived-snapshot-parity-implementation.md`
- `docs/superpowers/specs/2026-09-18-markitdown-2ways-phase-h20-remote-feed-snapshot-parity-design.md`
- `docs/superpowers/plans/2026-09-18-markitdown-2ways-phase-h20-remote-feed-snapshot-parity-implementation.md`
- `docs/superpowers/specs/2026-09-18-markitdown-2ways-phase-h21-youtube-multi-input-provenance-design.md`
- `docs/superpowers/plans/2026-09-18-markitdown-2ways-phase-h21-youtube-multi-input-provenance-implementation.md`
- `docs/superpowers/specs/2026-09-18-markitdown-2ways-phase-h22-document-intelligence-derived-analysis-design.md`
- `docs/superpowers/plans/2026-09-18-markitdown-2ways-phase-h22-document-intelligence-derived-analysis-implementation.md`
- `docs/superpowers/specs/2026-09-18-markitdown-2ways-phase-h23-content-understanding-derived-analysis-design.md`
- `docs/superpowers/plans/2026-09-18-markitdown-2ways-phase-h23-content-understanding-derived-analysis-implementation.md`

Current v1.0-gate execution documents include:

- `docs/superpowers/specs/2026-09-18-markitdown-2ways-phase-h24-audio-derived-snapshot-parity-design.md`
- `docs/superpowers/plans/2026-09-18-markitdown-2ways-phase-h24-audio-derived-snapshot-parity-implementation.md`
- `docs/superpowers/specs/2026-09-18-markitdown-2ways-phase-h25-image-multi-input-derived-parity-design.md`
- `docs/superpowers/plans/2026-09-18-markitdown-2ways-phase-h25-image-multi-input-derived-parity-implementation.md`
- `docs/superpowers/specs/2026-09-18-markitdown-2ways-phase-h26-outlook-msg-derived-semantic-parity-design.md`
- `docs/superpowers/plans/2026-09-18-markitdown-2ways-phase-h26-outlook-msg-derived-semantic-parity-implementation.md`

Each tranche is complete only after its exact final branch head passes pre-commit plus
the package and OCR matrices on Python 3.10-3.13. H5 uses a separate recovery-aware
contract and leaves the one-way HTML path unchanged. H6 composes notebook-specific
authority with H3 lexical scalar patching and leaves the existing one-way IPYNB path
unchanged. H7 composes EPUB package authority with H4 XML text mutation and leaves the
existing one-way EPUB path unchanged. H8 composes ordinary ZIP preservation/routing with
the existing typed H1-H7/native package writers, leaves the one-way `ZipConverter`
unchanged. H9 adds conservative PDF Document Information incremental mutation; H10 adds
only existing safe URI-link target mutation; H11 adds only existing H11-safe terminal
plain-text AcroForm `/V` mutation and leaves the existing one-way `PdfConverter`
unchanged. H12 starts v0.8 with existing unique PNG `tEXt` value mutation; H13 extends
that same bounded operation to existing cross-type unique `zTXt`/`iTXt` owners with
bounded decompression and immutable compression/language metadata. H14 adds only
fixed-allocation existing Exif IFD0 `ImageDescription`/`Artist` mutation with fresh native
authority and exact outside-slot preservation. H15 adds only existing terminal ID3v1/1.1
`Title`/`Artist`/`Album` fixed-slot mutation with fresh MPEG/terminal-metadata
authority, tamper-evident read limits and exact outside-slot preservation. H16 adds only
an existing top-level Unicode `PidTagSubject` replacement with exact encoded length,
fresh CFB/MAPI authority, tamper-evident read limits and exact outside-range preservation.
H17 adds only existing BIFF8 NUMBER Xnum mutation with fresh CFB/BIFF authority,
tamper-evident read limits and exact outside-slot preservation. H18 starts v0.9 with an
already-materialized Wikipedia snapshot, deterministic derived Markdown/provenance,
explicit `DERIVED` capability state and no network or remote/native writeback path. H19
extends that Class-D boundary to already-materialized Bing SERP HTML while still making
no search request, network call or remote writeback claim. H20 adds explicit remote
RSS/Atom snapshot semantics while preserving local feed bytes under H4 native XML
authority and still performs no fetch/poll/writeback action. H21 adds YouTube
multi-input provenance: HTML and optional transcript snapshots are independently bound,
production performs no transcript-service/network/process action, and absence of a
transcript is never treated as proof of remote unavailability. H22 adds caller-materialized
Azure Document Intelligence analysis provenance while separately binding source and
analysis evidence, reproducing only the one-way comment-removal transform and performing
no SDK/credential/network action. H23 closes the planned Azure Content Understanding
bridge by independently verifying default file-type/modality/analyzer/content-type routing
and binding exact caller-materialized `to_llm_input()` output, again with no SDK,
credential or network action. H24 then closes the unchanged `AudioConverter`'s local
metadata/transcript derived-semantic gap for WAV/MP3/M4A/MP4 while keeping H15 as the
only native MP3 authority and adding no WAV/M4A/MP4 writer. The one-way
`ContentUnderstandingConverter`, `ImageConverter`, `AudioConverter`, `OutlookMsgConverter`, `XlsConverter`, `WikipediaConverter`,
`BingSerpConverter`, `RssConverter` and `YouTubeConverter` remain unchanged. Annotation structural editing, form structure and non-H11 form controls,
appearance-backed forms, non-URI actions, page text/image/content mutation, outlines, new
metadata keys, further media-native mutation, other archive families, remote writeback
and archive structural editing remain outside the current completed boundary.