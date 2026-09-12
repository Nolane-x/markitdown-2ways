# MarkItDown 2Ways

MarkItDown 2Ways is the focused two-way layer in this fork. It keeps the existing
one-way `MarkItDown` API and CLI intact, and adds bounded, evidence-driven round trips:

```text
native document -> DocumentIR -> Markdown / typed edits -> native document
```

The production scope is intentionally narrow: Core IR, capability reporting,
identity/clean Markdown projection, PPTX, DOCX, conservative XLSX mutation, and the
first v0.5 source-preserving native text/Markdown tranche. This project is not an
Office automation platform, workflow engine, document-management service, or general
application framework.

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

## Capability model

2Ways does not treat successful parsing as proof that an edit is safe. Readers publish
deterministic capability decisions, and unknown or unadvertised operations default to
read-only. Reason codes are stable machine-readable diagnostics.

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

Phase H1 / v0.5 introduces a native source-preserving adapter for `.txt`, `.text`,
`.md`, and `.markdown`. Plain text and Markdown share the same adapter because the
lexical source bytes, rather than parsed Markdown structure, are authoritative in this
tranche.

```python
from io import BytesIO

from markitdown.twoways import EditOperation
from markitdown.twoways.formats.text import patch_text, read_text_ir

with open("README.md", "rb") as source_file:
    source = source_file.read()

document = read_text_ir(
    BytesIO(source),
    filename="README.md",
    mimetype="text/markdown",
)
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

The reader records source SHA-256/size plus exact representation metadata: encoding,
BOM, newline convention and byte-roundtrip proof. The writer verifies the original
source bytes, native locator, capability and edit preconditions; it then preserves the
recorded encoding/BOM/newline policy, re-reads the candidate, and writes destination
bytes only after verification succeeds. Zero-edit and semantic no-op writes remain
byte-identical.

Mixed-newline files remain readable but direct `replace_text` is read-only with
`text.newline.mixed`. A representation that cannot be proven byte-roundtrippable is
read-only with `text.encoding.not_roundtrippable`. A source with no existing newline
convention cannot introduce a line break in H1 because selecting LF/CRLF/CR would be a
guess.

### Why native source is read-only in identity Markdown

Existing identity-Markdown text import is intentionally semantic: for Office-derived
text it may interpret supported Markdown formatting and normalize whitespace/paragraph
structure. Those semantics are not an exact lexical edit protocol for arbitrary `.txt`
or `.md` source. Consequently H1 native source nodes set `text.native_source=true` and
remain directly writable through typed `replace_text`, while identity-Markdown manifests
publish no editable capability for those nodes. Unchanged projections can still be
validated/imported to zero edits.

A future raw-source identity protocol may become editable only after it can prove
preservation of marker-like text, Markdown syntax, trailing spaces, repeated blank
lines and other lexical details without guessing.

## PPTX and DOCX round trips

PPTX and DOCX use identity Markdown where the projection/importer can prove a semantic
edit maps back to one native owner. Supported text edits patch only the native XML part
that owns the target. Unsupported or ambiguous structures fail closed instead of being
silently rebuilt.

Both formats also expose bounded deep edits through the same capability kernel:

- `set_text_style` on safe existing native runs, with direct bold/italic/underline,
  font size, font family and RGB color where representation is exact;
- PPTX `move_resize` on safe non-group slide shapes using integer EMUs;
- picture alt-text edits where native carriers are unambiguous;
- simple table-cell text updates where every changed coordinate is bound to expected
  old text.

Inherited/theme style synthesis, rotation/group-coordinate rewriting, structural table
editing, theme/master/SmartArt/macros/OLE mutation, DOCX numbering/field/tracked-change
mutation and other ambiguous surfaces remain outside the writable boundary.

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

Simple lossless text-cell regions can participate in identity Markdown. Formula cells,
merged cells, rich inline/shared strings, unsupported cell types and ambiguous/lossy
regions remain read-only. Row/column/sheet structural edits, formula mutation,
merge/unmerge, chart/drawing mutation and style mutation are outside tranche one.
The production writer patches the original package rather than using `openpyxl` as a
serializer; `openpyxl` is used only as an independent regression oracle.

## Current capability boundary

| Area | Native text / Markdown H1 | PPTX | DOCX | XLSX tranche one |
| --- | --- | --- | --- | --- |
| Read into `DocumentIR` | exact decoded lexical source + representation metadata | slides, groups, notes, text, pictures, tables, charts | body, headers, footers, text, hyperlinks, pictures, tables | worksheets and typed cells |
| Primary patch | whole-source direct `replace_text` when representation is provable | compatible slide/group/notes text | compatible body/header/footer/hyperlink text | scalar non-formula, non-merged cells |
| Identity Markdown edit | read-only for native lexical source in H1 | supported safe semantic regions | supported safe semantic regions | supported safe simple cell regions |
| Direct run style | n/a | safe existing runs | safe existing runs | preserved; mutation unsupported |
| Geometry | n/a | safe non-group slide shapes | preserved; mutation unsupported | preserved; mutation unsupported |
| Tables / grids | n/a | simple cell text patchable; complex tables read-only | simple cell text patchable; complex tables read-only | worksheet grid; safe cells patchable |
| Formulas | n/a | n/a | n/a | read/preserved; read-only |
| Structural/theme edits | lexical source replacement only; no syntax-aware subtree edits | bounded; ambiguous structures fail closed | bounded; ambiguous structures fail closed | row/column/sheet/style changes unsupported |

CSV, JSON, XML and HTML are intentionally not writable through the H1 text adapter.
Their v0.5 tranches must independently prove dialect or syntax-aware lexical ownership
rather than passing parsed content through a generic serializer.

## Fidelity and safety model

The round-trip layer is designed around explicit proof rather than best-effort rebuilds:

- source SHA-256 is bound to `DocumentIR` and writers verify the supplied source;
- native text also binds source size, encoding, BOM and newline policy;
- edits can carry semantic, native-locator and expected-old-value preconditions;
- text source representation is revalidated against the actual bytes before mutation;
- no-op patching preserves the original file byte-for-byte;
- native text candidate output is re-read before destination emission;
- OOXML writers start from the original package and restrict mutation to authorized
  parts/subtrees;
- unrelated package members/native subtrees are verified after writes;
- style/geometry/table/XLSX verification re-reads requested semantics or direct native
  properties;
- malformed or ambiguous OPC member paths fail closed;
- duplicate relationship IDs inside one OOXML `.rels` part fail closed;
- XML parsing disables DTD/entity/network resolution;
- the 2Ways core does not perform network or subprocess I/O.

## Clean Markdown vs identity Markdown

Use clean mode when Markdown is the final projection. Use identity mode when a supported
semantic region will be edited and re-imported. Do not remove or forge `m2w` identity
comments: the importer validates projection manifest, document/node identity, source
semantic digests and native locator evidence before emitting typed edits.

Native lexical text/Markdown is the explicit H1 exception: identity projection is
inspection-only until a raw-source lossless protocol exists; direct typed native edits
remain available when the source representation is writable.

## Scope discipline and roadmap

New work should improve fidelity, compatibility, safety, tests, or reduce complexity.
The project deliberately avoids broad platform features and keeps a soft production-size
ceiling around roughly twice the upstream MarkItDown implementation.

The approved broader parity program is in
`docs/superpowers/specs/2026-09-11-markitdown-2ways-full-parity-program-design.md`.
The current H1 execution design and plan are:

- `docs/superpowers/specs/2026-09-12-markitdown-2ways-phase-h1-text-source-preservation-design.md`
- `docs/superpowers/plans/2026-09-12-phase-h1-text-source-preservation-implementation.md`

After H1 passes exact-head CI, Phase H2 adds CSV with independent dialect/quoting/span
proof. JSON/XML/HTML follow with syntax-aware lexical/subtree locators. Parser support
alone is never evidence that mutation is allowed.
