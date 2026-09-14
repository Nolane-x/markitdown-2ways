from pathlib import Path

path = Path("TWOWAYS.md")
text = path.read_text(encoding="utf-8")


def replace_once(old: str, new: str) -> None:
    global text
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"expected one match, got {count}: {old[:100]!r}")
    text = text.replace(old, new, 1)


replace_once(
    "package-preserving EPUB 3 metadata/XHTML text mutation, and bounded recursive ordinary\nZIP composition over supported typed inner formats. It is not an Office automation\n",
    "package-preserving EPUB 3 metadata/XHTML text mutation, bounded recursive ordinary ZIP\ncomposition over supported typed inner formats, and conservative PDF Document Information\nincremental metadata mutation. It is not an Office automation\n",
)

zip_tail = """Zero-edit ZIP writes are exact source bytes. Mutated archives preserve ordered inventory,
archive comments, directory entries, required member metadata and byte-identical
uncompressed content for every untouched member. H8 claims high preservation rather than
exact compressed-bitstream identity for rebuilt touched archive chains. Identity Markdown
is inspection-only for every ZIP-backed imported node even when its inner typed capability
is directly writable; direct typed operations remain the only H8 mutation path. The
existing one-way `ZipConverter` remains unchanged and independent of the H8 registry.

## PPTX and DOCX round trips
"""
pdf_section = """Zero-edit ZIP writes are exact source bytes. Mutated archives preserve ordered inventory,
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

## PPTX and DOCX round trips
"""
replace_once(zip_tail, pdf_section)

old_table = """| Area | Text / Markdown H1 | CSV H2 | JSON H3 | XML H4 | HTML H5 | IPYNB H6 | EPUB H7 | ZIP H8 | PPTX | DOCX | XLSX tranche one |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Read into `DocumentIR` | exact decoded lexical source + representation | lexical field spans + table semantics | strict spans + RFC 6901 hierarchy | strict XML owners + namespace identity | lexical owners + independent recovery signature | notebook/cell source semantics + lexical representation | OCF package graph + selected OPF/XHTML owners | ordered recursive inventory + namespaced supported inner IR | slides/groups/notes/text/media/tables | body/headers/footers/text/media/tables | worksheets and typed cells |
| Primary patch | `replace_text` | `update_csv_cells` | `replace_json_scalar` | `replace_xml_text` / `replace_xml_attribute` | `replace_html_text` / `replace_html_attribute` | `replace_ipynb_cell_source` via H3 scalar lowering | `replace_epub_metadata_text` / `replace_epub_xhtml_text` via H4 lowering | routes the existing typed inner operation through the exact member chain; ZIP structure itself is read-only | bounded native text/style/geometry/media/table | bounded native text/style/media/table | scalar non-formula, non-merged cells |
| Identity Markdown edit | inspection-only | inspection-only | inspection-only | inspection-only | inspection-only | inspection-only | inspection-only | inspection-only for every ZIP-backed imported node | supported safe semantic regions | supported safe semantic regions | supported safe simple cell regions |
| Representation proof | encoding/BOM/newline | encoding/BOM + dialect/spans/terminators | encoding/BOM + pointer/span/raw token | encoding/BOM/declaration + lexical spans/namespaces | encoding/BOM/meta + lexical spans + recovery signature | encoding/BOM + source string/list shape/cardinality + notebook reread | ordered OCF inventory + member digests + OPF graph + H4 XML ownership | root/member SHA+size, ordered nested inventory, member metadata, full chain + shared global budgets | OPC/XML ownership | OPC/XML ownership | OPC/XML + typed cell ownership |
| Structural edits | unsupported | unsupported | unsupported | unsupported | unsupported | unsupported; notebook/cell structure and non-source state are read-only | unsupported; package graph/inventory/nav/media are read-only | unsupported; add/delete/rename/reorder/comment/compression/encryption/raw member replacement are read-only | bounded; ambiguous structures fail closed | bounded; ambiguous structures fail closed | row/column/sheet changes unsupported |
"""
new_table = """| Area | Text / Markdown H1 | CSV H2 | JSON H3 | XML H4 | HTML H5 | IPYNB H6 | EPUB H7 | ZIP H8 | PDF H9 | PPTX | DOCX | XLSX tranche one |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Read into `DocumentIR` | exact decoded lexical source + representation | lexical field spans + table semantics | strict spans + RFC 6901 hierarchy | strict XML owners + namespace identity | lexical owners + independent recovery signature | notebook/cell source semantics + lexical representation | OCF package graph + selected OPF/XHTML owners | ordered recursive inventory + namespaced supported inner IR | strict PDF source + existing `/Info` text owners | slides/groups/notes/text/media/tables | body/headers/footers/text/media/tables | worksheets and typed cells |
| Primary patch | `replace_text` | `update_csv_cells` | `replace_json_scalar` | `replace_xml_text` / `replace_xml_attribute` | `replace_html_text` / `replace_html_attribute` | `replace_ipynb_cell_source` via H3 scalar lowering | `replace_epub_metadata_text` / `replace_epub_xhtml_text` via H4 lowering | routes the existing typed inner operation through the exact member chain; ZIP structure itself is read-only | `update_pdf_metadata` for existing Title/Author/Subject/Keywords | bounded native text/style/geometry/media/table | bounded native text/style/media/table | scalar non-formula, non-merged cells |
| Identity Markdown edit | inspection-only | inspection-only | inspection-only | inspection-only | inspection-only | inspection-only | inspection-only | inspection-only for every ZIP-backed imported node | inspection-only | supported safe semantic regions | supported safe semantic regions | supported safe simple cell regions |
| Representation proof | encoding/BOM/newline | encoding/BOM + dialect/spans/terminators | encoding/BOM + pointer/span/raw token | encoding/BOM/declaration + lexical spans/namespaces | encoding/BOM/meta + lexical spans + recovery signature | encoding/BOM + source string/list shape/cardinality + notebook reread | ordered OCF inventory + member digests + OPF graph + H4 XML ownership | root/member SHA+size, ordered nested inventory, member metadata, full chain + shared global budgets | exact source prefix + root/Info objgen + changed-object audit + strict pypdf/pdfminer agreement | OPC/XML ownership | OPC/XML ownership | OPC/XML + typed cell ownership |
| Structural edits | unsupported | unsupported | unsupported | unsupported | unsupported | unsupported; notebook/cell structure and non-source state are read-only | unsupported; package graph/inventory/nav/media are read-only | unsupported; add/delete/rename/reorder/comment/compression/encryption/raw member replacement are read-only | unsupported; no new keys or page/object-graph edits | bounded; ambiguous structures fail closed | bounded; ambiguous structures fail closed | row/column/sheet changes unsupported |
"""
replace_once(old_table, new_table)

replace_once(
    "H1-H5 together form the v0.5 text/structured-text parity tranche. H6-H8 extend v0.6\nwith bounded Jupyter Notebook source preservation, EPUB 3 package-preserving text\nmutation and recursive ordinary ZIP composition, each isolated behind exact source and\nnative ownership authority.\n",
    "H1-H5 together form the v0.5 text/structured-text parity tranche. H6-H8 extend v0.6\nwith bounded Jupyter Notebook source preservation, EPUB 3 package-preserving text\nmutation and recursive ordinary ZIP composition. H9 starts v0.7 with conservative PDF\nDocument Information mutation. Every tranche remains isolated behind exact source and\nnative ownership authority.\n",
)

replace_once(
    "- ZIP binds root source authority, full recursive member-chain SHA/size evidence, ordered\n  inventories, archive comments, supported member metadata, strong-package classification\n  priority and transaction-wide recursion budgets;\n",
    "- ZIP binds root source authority, full recursive member-chain SHA/size evidence, ordered\n  inventories, archive comments, supported member metadata, strong-package classification\n  priority and transaction-wide recursion budgets;\n- PDF binds strict source/catalog/Info ownership, exact source-prefix preservation, the\n  incremental changed-object set, page count and dual pypdf/pdfminer metadata semantics;\n",
)
replace_once(
    "- text, CSV, JSON, XML, HTML, IPYNB, EPUB and ZIP candidates are re-read before destination\n  emission according to their native or composed verifier contract;\n",
    "- text, CSV, JSON, XML, HTML, IPYNB, EPUB, ZIP and PDF candidates are re-read before\n  destination emission according to their native or composed verifier contract;\n",
)
replace_once(
    "- ZIP additionally rejects unsafe/duplicate/encrypted/symlink members, unsupported ZIP\n  compression, recursion-depth/member/expanded-byte/ratio violations and ambiguous member\n  classification before typed routing;\n",
    "- ZIP additionally rejects unsafe/duplicate/encrypted/symlink members, unsupported ZIP\n  compression, recursion-depth/member/expanded-byte/ratio violations and ambiguous member\n  classification before typed routing;\n- PDF additionally rejects XMP authority, encryption, signatures/certification,\n  linearization, ambiguous/missing Info ownership, non-text supported values and configured\n  source/page/metadata/increment limits before caller output;\n",
)

replace_once(
    "boundary. H8 preserves visible projection of supported nested content but forces\n`editable_capabilities=()` for every ZIP-backed imported block, so identity Markdown\ncannot become an alternate archive mutation path. Direct typed native paths remain\nwritable only where source evidence is sufficient.\n",
    "boundary. H8 preserves visible projection of supported nested content but forces\n`editable_capabilities=()` for every ZIP-backed imported block, so identity Markdown\ncannot become an alternate archive mutation path. H9 applies the same inspection-only\nboundary to PDF metadata blocks. Direct typed native paths remain writable only where\nsource evidence is sufficient.\n",
)

replace_once(
    "- `docs/superpowers/specs/2026-09-13-markitdown-2ways-phase-h8-recursive-zip-preservation-design.md`\n- `docs/superpowers/plans/2026-09-13-markitdown-2ways-phase-h8-recursive-zip-preservation.md`\n\nEach tranche is complete only after its exact final branch head passes pre-commit plus\n",
    "- `docs/superpowers/specs/2026-09-13-markitdown-2ways-phase-h8-recursive-zip-preservation-design.md`\n- `docs/superpowers/plans/2026-09-13-markitdown-2ways-phase-h8-recursive-zip-preservation.md`\n\nCurrent v0.7 execution documents include:\n\n- `docs/superpowers/specs/2026-09-14-markitdown-2ways-phase-h9-pdf-metadata-preservation-design.md`\n- `docs/superpowers/plans/2026-09-14-markitdown-2ways-phase-h9-pdf-metadata-preservation.md`\n\nEach tranche is complete only after its exact final branch head passes pre-commit plus\n",
)

replace_once(
    "unchanged, and keeps PDF native-safe mutation, media-native mutation, other archive\nfamilies, remote writeback and archive structural editing outside this tranche.\n",
    "unchanged. H9 adds only conservative PDF Document Information incremental mutation and\nleaves the existing one-way `PdfConverter` unchanged. PDF annotations/forms/links, page\ntext/image/content mutation, outlines, new metadata keys, media-native mutation, other\narchive families, remote writeback and archive structural editing remain outside the\ncurrent completed boundary.\n",
)

path.write_text(text, encoding="utf-8")
