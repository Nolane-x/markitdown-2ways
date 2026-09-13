from pathlib import Path

path = Path("TWOWAYS.md")
text = path.read_text(encoding="utf-8")


def replace_once(old: str, new: str) -> None:
    global text
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"expected one documentation anchor, found {count}: {old[:100]!r}")
    text = text.replace(old, new, 1)


replace_once(
    "scalar mutation, target-only XML text/attribute mutation, and recovery-aware target-only\n"
    "HTML text/quoted-attribute mutation.",
    "scalar mutation, target-only XML text/attribute mutation, recovery-aware target-only\n"
    "HTML text/quoted-attribute mutation, and target-only Jupyter Notebook cell-source\n"
    "mutation.",
)

h6_section = """## Jupyter Notebook source-preserving cell-source edits

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
    payload={"value": "# Updated cell\\n"},
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

"""
replace_once("## PPTX and DOCX round trips\n", h6_section + "## PPTX and DOCX round trips\n")

old_table = """| Area | Text / Markdown H1 | CSV H2 | JSON H3 | XML H4 | HTML H5 | PPTX | DOCX | XLSX tranche one |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Read into `DocumentIR` | exact decoded lexical source + representation | lexical field spans + table semantics | strict spans + RFC 6901 hierarchy | strict XML owners + namespace identity | lexical owners + independent recovery signature | slides/groups/notes/text/media/tables | body/headers/footers/text/media/tables | worksheets and typed cells |
| Primary patch | `replace_text` | `update_csv_cells` | `replace_json_scalar` | `replace_xml_text` / `replace_xml_attribute` | `replace_html_text` / `replace_html_attribute` | bounded native text/style/geometry/media/table | bounded native text/style/media/table | scalar non-formula, non-merged cells |
| Identity Markdown edit | inspection-only | inspection-only | inspection-only | inspection-only | inspection-only | supported safe semantic regions | supported safe semantic regions | supported safe simple cell regions |
| Representation proof | encoding/BOM/newline | encoding/BOM + dialect/spans/terminators | encoding/BOM + pointer/span/raw token | encoding/BOM/declaration + lexical spans/namespaces | encoding/BOM/meta + lexical spans + recovery signature | OPC/XML ownership | OPC/XML ownership | OPC/XML + typed cell ownership |
| Structural edits | unsupported | unsupported | unsupported | unsupported | unsupported | bounded; ambiguous structures fail closed | bounded; ambiguous structures fail closed | row/column/sheet changes unsupported |
"""
new_table = """| Area | Text / Markdown H1 | CSV H2 | JSON H3 | XML H4 | HTML H5 | IPYNB H6 | PPTX | DOCX | XLSX tranche one |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Read into `DocumentIR` | exact decoded lexical source + representation | lexical field spans + table semantics | strict spans + RFC 6901 hierarchy | strict XML owners + namespace identity | lexical owners + independent recovery signature | notebook/cell source semantics + lexical representation | slides/groups/notes/text/media/tables | body/headers/footers/text/media/tables | worksheets and typed cells |
| Primary patch | `replace_text` | `update_csv_cells` | `replace_json_scalar` | `replace_xml_text` / `replace_xml_attribute` | `replace_html_text` / `replace_html_attribute` | `replace_ipynb_cell_source` via H3 scalar lowering | bounded native text/style/geometry/media/table | bounded native text/style/media/table | scalar non-formula, non-merged cells |
| Identity Markdown edit | inspection-only | inspection-only | inspection-only | inspection-only | inspection-only | inspection-only | supported safe semantic regions | supported safe semantic regions | supported safe simple cell regions |
| Representation proof | encoding/BOM/newline | encoding/BOM + dialect/spans/terminators | encoding/BOM + pointer/span/raw token | encoding/BOM/declaration + lexical spans/namespaces | encoding/BOM/meta + lexical spans + recovery signature | encoding/BOM + source string/list shape/cardinality + notebook reread | OPC/XML ownership | OPC/XML ownership | OPC/XML + typed cell ownership |
| Structural edits | unsupported | unsupported | unsupported | unsupported | unsupported | unsupported; notebook/cell structure and non-source state are read-only | bounded; ambiguous structures fail closed | bounded; ambiguous structures fail closed | row/column/sheet changes unsupported |
"""
replace_once(old_table, new_table)

replace_once(
    "H1-H5 together form the v0.5 text/structured-text parity tranche. Later notebook,\n"
    "publication and container work belongs to a separate v0.6 branch rather than extending\n"
    "H5's writable boundary.",
    "H1-H5 together form the v0.5 text/structured-text parity tranche. H6 starts v0.6 with\n"
    "bounded Jupyter Notebook cell-source preservation on its own branch. Publication and\n"
    "container work remains in later tranches rather than expanding H6's writable boundary.",
)

replace_once(
    "- HTML binds recovery-aware native paths, exact lexical/value spans, original/normalized\n"
    "  names, quote shape, encoding/meta declarations and an independent recovery signature;\n"
    "- CSV, JSON, XML and HTML prove every encoded byte segment outside requested targets\n"
    "  remains exact;\n"
    "- text, CSV, JSON, XML and HTML candidates are re-read before destination emission;",
    "- HTML binds recovery-aware native paths, exact lexical/value spans, original/normalized\n"
    "  names, quote shape, encoding/meta declarations and an independent recovery signature;\n"
    "- IPYNB binds notebook/cell semantics, source string/list representation, fixed array\n"
    "  cardinality and raw source-token evidence while reusing H3 scalar lexical authority;\n"
    "- CSV, JSON, XML, HTML and IPYNB prove every encoded byte segment outside requested\n"
    "  targets remains exact through their native or composed preservation contracts;\n"
    "- text, CSV, JSON, XML, HTML and IPYNB candidates are re-read before destination emission;",
)

replace_once(
    "Native lexical text/Markdown, CSV, JSON, XML and HTML are explicit v0.5 inspection-only\n"
    "identity projections. Their direct typed native paths remain writable only where native\n"
    "source evidence is sufficient.",
    "Native lexical text/Markdown, CSV, JSON, XML and HTML are explicit v0.5 inspection-only\n"
    "identity projections. IPYNB H6 keeps the same inspection-only identity boundary for cell\n"
    "source text. Direct typed native paths remain writable only where source evidence is\n"
    "sufficient.",
)

replace_once("Current v0.5 execution documents include:\n", "Completed v0.5 execution documents include:\n")

replace_once(
    "- `docs/superpowers/plans/2026-09-12-phase-h5-html-source-preservation-implementation.md`\n\n"
    "Each tranche is complete only after its exact final branch head passes pre-commit plus",
    "- `docs/superpowers/plans/2026-09-12-phase-h5-html-source-preservation-implementation.md`\n\n"
    "Current v0.6 notebook execution documents include:\n\n"
    "- `docs/superpowers/specs/2026-09-13-markitdown-2ways-phase-h6-ipynb-source-preservation-design.md`\n"
    "- `docs/superpowers/plans/2026-09-13-phase-h6-ipynb-source-preservation-implementation.md`\n\n"
    "Each tranche is complete only after its exact final branch head passes pre-commit plus",
)

replace_once(
    "the package and OCR matrices on Python 3.10-3.13. H5 uses a separate recovery-aware\n"
    "contract and does not change the existing one-way HTML converter, API or CLI. After the\n"
    "H5 exact-head gate, v0.6 notebook/publication/container work must start on a new branch.",
    "the package and OCR matrices on Python 3.10-3.13. H5 uses a separate recovery-aware\n"
    "contract and leaves the one-way HTML path unchanged. H6 composes notebook-specific\n"
    "authority with H3 lexical scalar patching and leaves the existing one-way IPYNB path\n"
    "unchanged. After the H6 exact-head gate, the EPUB tranche starts from that exact SHA on\n"
    "a new branch; recursive ZIP follows on another branch.",
)

path.write_text(text, encoding="utf-8")
