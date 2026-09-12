# MarkItDown 2Ways

MarkItDown 2Ways is the focused two-way layer in this fork. It keeps the existing
one-way `MarkItDown` API and CLI intact, and adds a bounded round-trip path for
high-value Office formats:

```text
native document -> DocumentIR -> Markdown / typed edits -> native document
```

The current production scope is intentionally small: Core IR, capability reporting,
Markdown round trip, PPTX, DOCX, and a conservative first XLSX tranche. This is not
intended to become an Office automation platform, workflow engine, document-management
service, or general application framework.

## Install this fork

The 2Ways layer is developed in this repository. Install the fork from source rather
than assuming the upstream PyPI package contains these APIs:

```bash
git clone https://github.com/Nolane-x/markitdown-2ways.git
cd markitdown-2ways
pip install -e 'packages/markitdown[pptx,docx,xlsx]'
```

The original one-way API remains available:

```python
from markitdown import MarkItDown

result = MarkItDown().convert("report.pdf")
print(result.markdown)
```

## Capability inspection

2Ways exposes deterministic capability decisions instead of treating successful
parsing as proof that a native edit is safe. Callers can inspect one node or summarize
a complete document:

```python
from markitdown.twoways import build_capability_report, capabilities_for_node
from markitdown.twoways.formats.xlsx import read_xlsx_ir

with open("workbook.xlsx", "rb") as source_file:
    document = read_xlsx_ir(source_file)

report = build_capability_report(document)
print(report.writable_by_operation)
print(report.reason_counts)

node = document.nodes[document.canvases[0].root_node_ids[0]]
decision = capabilities_for_node(node).for_operation("update_sheet_cells")
print(decision.state, decision.reason_code, decision.constraints)
```

Unknown or unadvertised operations default to read-only. Reason codes are stable,
machine-readable diagnostics rather than arbitrary exception text.

## PPTX round trip

Identity Markdown carries stable, invisible 2Ways markers so a conservative importer
can turn supported edits back into typed operations.

```python
from io import BytesIO

from markitdown.twoways import (
    MarkdownProjectionMode,
    MarkdownProjectionOptions,
    import_identity_markdown,
    project_markdown,
)
from markitdown.twoways.formats.pptx import patch_pptx, read_pptx_ir

with open("deck.pptx", "rb") as source_file:
    source = source_file.read()

document = read_pptx_ir(BytesIO(source))
projection = project_markdown(
    document,
    options=MarkdownProjectionOptions(mode=MarkdownProjectionMode.IDENTITY),
)

# In a real workflow, edit projection.markdown with a human or model while
# preserving the identity comments. This simple replacement mirrors the
# repository's end-to-end regression test.
edited_markdown = projection.markdown.replace("38%", "42%", 1)
imported = import_identity_markdown(
    edited_markdown,
    original_document=document,
    manifest=projection.manifest,
)

with open("deck-edited.pptx", "wb") as output_file:
    patch_pptx(
        document,
        BytesIO(source),
        output_file,
        edits=imported.edits,
    )
```

For a compatible text edit, the writer patches only the native XML part that owns the
target. Unsupported structures fail closed instead of silently rebuilding the deck.

## DOCX round trip

The DOCX API follows the same flow:

```python
from io import BytesIO

from markitdown.twoways import (
    MarkdownProjectionMode,
    MarkdownProjectionOptions,
    import_identity_markdown,
    project_markdown,
)
from markitdown.twoways.formats.docx import patch_docx, read_docx_ir

with open("report.docx", "rb") as source_file:
    source = source_file.read()

document = read_docx_ir(BytesIO(source))
projection = project_markdown(
    document,
    options=MarkdownProjectionOptions(mode=MarkdownProjectionMode.IDENTITY),
)
edited_markdown = projection.markdown.replace("38%", "42%", 1)
imported = import_identity_markdown(
    edited_markdown,
    original_document=document,
    manifest=projection.manifest,
)

with open("report-edited.docx", "wb") as output_file:
    patch_docx(
        document,
        BytesIO(source),
        output_file,
        edits=imported.edits,
    )
```

## Office deep editing

DOCX and PPTX now advertise deeper typed edits through the same capability kernel.
These operations are deliberately narrower than a general Office object model: the
reader advertises them only when the native XML can be patched and verified without
rebuilding surrounding content.

`set_text_style` targets one existing native text run by `run_index`. The payload binds
that run to its expected direct style with `old_style`, then supplies the replacement
`style`. The supported direct properties are bold, italic, underline, font size, font
family, and RGB color. DOCX font sizes must be exactly representable in WordprocessingML
half-points; PPTX font sizes must be exactly representable in DrawingML hundredths of a
point. Theme/complex PPTX colors, ambiguous run layouts, fields, and structures whose
style cannot be proved directly remain read-only or fail closed. Inherited/theme style
semantics are not synthesized into direct formatting.

PPTX additionally supports `move_resize` for safe, non-group shapes on ordinary slide
parts. The edit is limited to `x`, `y`, `width`, and `height` in integer EMUs. The
writer requires one unambiguous native transform whose current values match the source
IR before mutation, and verifies exact geometry after re-reading the output. Rotation,
origin/transform rewriting, group child-coordinate spaces, notes-slide geometry, and
unknown native shapes are outside this tranche.

Both deep-edit operations are transactional: stale direct style or geometry is rejected
before bytes are returned. Verification still requires package preservation, unchanged
unrelated native subtrees, and semantic identity in addition to style/geometry readback.

## XLSX tranche-one round trip

The first XLSX tranche reads worksheets and typed scalar cells into `DocumentIR` and
supports `update_sheet_cells` only where the reader and writer can prove a conservative
native patch. Typed edits bind a coordinate to its expected old value:

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
    patch_xlsx(
        document,
        BytesIO(source),
        output_file,
        edits=(edit,),
    )
```

Simple, lossless text-cell regions can also participate in identity Markdown and are
re-imported as typed `update_sheet_cells` operations. Formula cells, merged cells,
rich inline/shared strings, unsupported cell types, and ambiguous or lossy Markdown
regions stay read-only. Row/column/sheet structural edits, formula editing,
merge/unmerge, chart or drawing mutation, and style mutation are outside tranche one.
Those native structures are preserved rather than rebuilt by the XLSX writer.

The writer starts from the original XLSX package, patches only authorized worksheet
parts, re-reads output semantics, and verifies preservation. No-op writes must remain
byte-identical. The regression corpus additionally opens patched output with
`openpyxl` as an independent validation oracle; `openpyxl` is not the production
writer.

## Safe table cell round trips

Simple DOCX and PPTX tables can participate in the same identity-Markdown workflow.
When the reader proves that every cell has an unambiguous native text carrier, the
table block advertises `update_table_cells`. Editing one or more cells in identity
Markdown produces one typed operation containing only the changed coordinates:

```python
{
    "cells": [
        {
            "row": 1,
            "column": 1,
            "old_text": "38%",
            "text": "42%",
        }
    ]
}
```

The writer validates the table-level source identity, the native locator, every cell
coordinate, and each `old_text` value before mutating anything. It then changes only
the existing native text carriers and verifies the complete table after reopening the
output. Untouched cells, table/row/cell properties, relationships, media, and unrelated
package members must remain preserved.

This is deliberately not a structural table editor. Merged or spanned cells, nested
DOCX tables, multi-paragraph cells, ambiguous text carriers, Markdown-ambiguous cell
text, row/column count changes, insertion/deletion, merge/unmerge, and table-style or
layout mutations remain read-only or fail closed.

## Current capability boundary

| Area | PPTX | DOCX | XLSX tranche one |
| --- | --- | --- | --- |
| Read into `DocumentIR` | slides, groups, notes, text, pictures, tables, charts | body, headers, footers, text, hyperlinks, pictures, tables | worksheets and typed cells |
| Scalar/text patch | compatible slide/group/notes text | compatible body/header/footer/hyperlink text | scalar non-formula, non-merged cells |
| Direct run style | safe existing runs: bold/italic/underline/font size/font family/RGB color | safe existing runs: bold/italic/underline/font size/font family/RGB color | read/preserved; style mutation unsupported |
| Geometry | safe non-group slide shapes: integer-EMU x/y/width/height | preserved / unsupported for mutation | preserved / unsupported for mutation |
| Picture alt text | patchable | patchable | preserved / unsupported for mutation |
| Tables / grids | simple cell text patchable; complex tables read-only | simple cell text patchable; complex tables read-only | worksheet cell grid; safe cells patchable |
| Formulas | n/a | n/a | read/preserved; read-only |
| Charts / drawings | chart semantics read-only; safe chart-frame geometry may be movable/resizable; chart data remains read-only | native-preserved / unsupported for mutation | native-preserved / unsupported for mutation |
| Structural/theme edits | unsupported; groups, rotation, theme/master/SmartArt/macros/OLE fail closed | structural/theme/numbering/field/tracked-change mutations unsupported | row/column/sheet/style changes unsupported |

Complex structural, inherited-style, numbering, field, tracked-change, media, theme,
and group-coordinate mutations remain outside the write surface. Preservation writers
start from the original OOXML package and edit only authorized parts.

## Fidelity and safety model

The round-trip layer is designed around explicit proof rather than best-effort rebuilds:

- source package SHA-256 is bound to the `DocumentIR`;
- edits can carry semantic, native-locator, and expected-old-value preconditions;
- `set_text_style` binds a native run to its expected direct `old_style`;
- PPTX `move_resize` binds source geometry to one native transform before mutation;
- table-cell edits additionally bind each coordinate to its expected old text;
- XLSX cell edits bind each coordinate to its expected old typed value;
- native locators are resolved strictly inside the designated OOXML part;
- no-op patching preserves the original file byte-for-byte;
- unrelated package members and native subtrees are verified after writes;
- style verification re-reads direct formatting while requiring text to remain unchanged;
- PPTX geometry verification re-reads exact requested coordinates and extents;
- table verification permits changes only to explicitly authorized cell text carriers;
- XLSX verification re-reads target semantics and restricts changes to authorized cells;
- rich XLSX inline/shared strings stay read-only until run-preserving editing exists;
- oversized or overlapping XLSX merged ranges fail closed before unsafe expansion;
- malformed or ambiguous OPC member paths fail closed;
- duplicate relationship IDs inside one OOXML `.rels` part fail closed;
- the same relationship ID may still appear independently in different `.rels` parts;
- XML parsing disables DTD/entity/network resolution;
- the 2Ways core does not perform network or subprocess I/O.

## Clean Markdown vs identity Markdown

Use clean mode when Markdown is the final projection:

```python
clean = project_markdown(document)
print(clean.markdown)
```

Use identity mode when Markdown will be edited and re-imported:

```python
identity = project_markdown(
    document,
    options=MarkdownProjectionOptions(mode=MarkdownProjectionMode.IDENTITY),
)
```

Do not remove or forge the `m2w` identity comments. The importer validates the
projection manifest, document identity, node identity, source semantic digests, and
native locator evidence before emitting typed edits.

## Scope discipline

New work in this fork should improve fidelity, compatibility, safety, tests, or reduce
complexity. The project deliberately avoids broad platform features and keeps a soft
production-size ceiling around roughly twice the upstream MarkItDown implementation.

The broader parity program is documented in
`docs/superpowers/specs/2026-09-11-markitdown-2ways-full-parity-program-design.md`.
Each future format or deeper edit surface must independently prove safe writeback;
parser support alone is never evidence that a mutation is allowed.
