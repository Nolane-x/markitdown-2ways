# MarkItDown 2Ways

MarkItDown 2Ways is the focused two-way layer in this fork. It keeps the existing
one-way `MarkItDown` API and CLI intact, and adds bounded, evidence-driven round trips:

```text
native document -> DocumentIR -> Markdown / typed edits -> native document
```

The production scope is intentionally narrow: Core IR, capability reporting,
identity/clean Markdown projection, PPTX, DOCX, conservative XLSX mutation, native
text/Markdown source preservation, target-only CSV cell mutation, and target-only JSON
scalar mutation. This project is not an Office automation platform, workflow engine,
document-management service, or general application framework.

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

The reader records source SHA-256/size plus exact representation metadata: encoding,
BOM, newline convention and byte-roundtrip proof. The writer verifies source identity,
native locator, capability and edit preconditions; it preserves the recorded
representation, re-reads the candidate, and writes destination bytes only after
verification succeeds. Zero-edit and semantic no-op writes remain byte-identical.

Mixed-newline files remain readable but direct `replace_text` is read-only with
`text.newline.mixed`. A representation that cannot be proven byte-roundtrippable is
read-only with `text.encoding.not_roundtrippable`. A source with no existing newline
convention cannot introduce a line break because choosing LF/CRLF/CR would be a guess.

### Native source and identity Markdown

Existing identity-Markdown text import is intentionally semantic: for Office-derived
text it may interpret supported Markdown formatting and normalize paragraph whitespace.
That is not an exact lexical protocol for arbitrary `.txt` or `.md` source. Native
source therefore remains directly writable through typed `replace_text`, while its
identity-Markdown projection is inspection-only until a raw-source protocol can prove
lexical preservation.

## CSV source-preserving cell edits

Phase H2 adds direct `update_csv_cells` edits without turning CSV into a regenerated
table. The native adapter first proves reversible text representation and CSV lexical
ownership, then records each materialized field's exact character span, semantic value,
quote state, multiline state and raw lexical digest.

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

H2 never uses `csv.writer`, pandas, or whole-document CSV serialization. It patches only
authorized field spans in the decoded lexical source, encodes the result using the
original representation, proves every untouched encoded byte segment stayed exact,
re-reads the candidate, verifies requested and unrequested cells plus structure and
representation, and only then emits destination bytes.

Supported auto-detected delimiters are comma, semicolon, tab and pipe. Auto-detection
must produce one unique supported candidate; ambiguous sources fail closed. A
single-column source without an explicit delimiter is readable but mutation is
read-only with `csv.dialect.unproven_single_column`. An explicit one-character delimiter
can make such a source authoritative.

Existing quoted targets remain quoted. An unquoted target stays unquoted unless the new
value contains the delimiter or a quote, in which case H2 introduces the required quote
wrapper and doubles embedded quote characters. Replacement CR/LF is deliberately
unsupported in H2. Existing multiline quoted neighboring fields and physical
CR/LF/CRLF/mixed record terminators are preserved rather than regenerated.

CSV identity-Markdown is read-only in H2. A Markdown table is not enough evidence to
reconstruct original quoting, blank records, ragged rows, physical terminators or exact
lexical spans. Direct typed CSV edits are the only H2 mutation path.

## JSON source-preserving scalar edits

Phase H3 adds strict JSON lexical ownership and direct `replace_json_scalar` edits.
Every JSON value receives an RFC 6901 pointer, exact character span, native locator,
raw-token digest and deterministic hierarchy evidence. Scalar nodes are writable only
when the source representation is byte-roundtrippable; object and array nodes remain
structural read-only.

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

H3 never serializes an object, array or complete document. It renders only the requested
scalar token, patches its exact source span, re-encodes using the original encoding/BOM,
and proves every encoded byte segment outside authorized targets stayed unchanged. A
strict candidate re-read then verifies the complete pointer set and parent/child order,
requested scalar semantics, every unrequested scalar semantic value and raw lexical
digest, plus representation metadata before destination output is emitted.

Supported replacement values are JSON strings, integers, finite floats, booleans and
null. Object/array replacement, member insertion/deletion/reordering, key rename, array
structural edits, JSON Patch/merge patch, JSONL/NDJSON and JSON extensions are outside
H3. Comments, trailing commas, single quotes, NaN/Infinity and duplicate decoded object
keys fail closed. A semantically equal replacement is rejected even when its lexical
spelling differs, such as changing `1e2` to `100`.

JSON identity-Markdown is inspection-only. JSON nodes project as `unknown_native` and do
not advertise `replace_json_scalar` through the Markdown manifest; typed native edits
are the only H3 mutation path. Existing one-way `.json` behavior through
`PlainTextConverter` remains unchanged.

## PPTX and DOCX round trips

PPTX and DOCX use identity Markdown where the projection/importer can prove a semantic
edit maps back to one native owner. Supported text edits patch only the native XML part
that owns the target. Unsupported or ambiguous structures fail closed instead of being
silently rebuilt.

Both formats expose bounded deep edits through the same capability kernel:

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

Formula cells, merged cells, rich inline/shared strings, unsupported cell types and
ambiguous/lossy regions remain read-only. Row/column/sheet structural edits, formula
mutation, merge/unmerge, chart/drawing mutation and style mutation are outside tranche
one. The production writer patches the original package rather than using `openpyxl` as
a serializer; `openpyxl` is an independent regression oracle.

## Current capability boundary

| Area | Native text / Markdown H1 | CSV H2 | JSON H3 | PPTX | DOCX | XLSX tranche one |
| --- | --- | --- | --- | --- | --- | --- |
| Read into `DocumentIR` | exact decoded lexical source + representation | lexical field spans + table semantics | strict value spans + RFC 6901 pointers + hierarchy | slides, groups, notes, text, pictures, tables, charts | body, headers, footers, text, hyperlinks, pictures, tables | worksheets and typed cells |
| Primary patch | whole-source `replace_text` when representation is provable | target-only `update_csv_cells` | target-only `replace_json_scalar` | compatible slide/group/notes text | compatible body/header/footer/hyperlink text | scalar non-formula, non-merged cells |
| Identity Markdown edit | read-only for native lexical source | read-only in H2 | read-only in H3 | supported safe semantic regions | supported safe semantic regions | supported safe simple cell regions |
| Representation proof | encoding/BOM/newline | encoding/BOM + delimiter + field spans + row terminators | encoding/BOM + pointer/span/raw-token evidence | OPC/XML native ownership | OPC/XML native ownership | OPC/XML + typed cell ownership |
| Structural edits | unsupported | unsupported | unsupported | bounded; ambiguous structures fail closed | bounded; ambiguous structures fail closed | row/column/sheet changes unsupported |

XML and HTML are not writable through H3. Their v0.5 tranches must independently prove
syntax-aware lexical/subtree ownership rather than route parsed content through a
generic serializer.

## Fidelity and safety model

The round-trip layer is designed around explicit proof rather than best-effort rebuilds:

- source SHA-256 is bound to `DocumentIR` and writers verify the supplied source;
- native text binds source size, encoding, BOM and newline policy;
- CSV binds source size, encoding/BOM, delimiter, native coordinate set, exact field
  spans/raw digests and physical row terminator evidence;
- JSON binds source size, encoding/BOM, exact RFC 6901 pointer ownership, hierarchy,
  lexical value spans and raw-token digests;
- edits can carry semantic, native-locator and expected-old-value preconditions;
- no-op patching preserves the original file byte-for-byte;
- native text, CSV and JSON candidates are re-read before destination emission;
- CSV and JSON prove every encoded byte segment outside requested targets is exact;
- JSON additionally verifies requested semantics and all unrequested scalar raw evidence
  after re-read;
- OOXML writers start from the original package and restrict mutation to authorized
  parts/subtrees;
- unrelated package members/native subtrees are verified after writes;
- malformed or ambiguous native ownership fails closed;
- XML parsing disables DTD/entity/network resolution;
- the 2Ways core does not perform network or subprocess I/O.

## Clean Markdown vs identity Markdown

Use clean mode when Markdown is the final projection. Use identity mode when a supported
semantic region will be edited and re-imported. Do not remove or forge `m2w` identity
comments: the importer validates projection manifest, document/node identity, source
semantic digests and native locator evidence before emitting typed edits.

Native lexical text/Markdown, CSV and JSON are explicit v0.5 exceptions: their current
identity projections are inspection-only because generic Markdown semantics do not
prove exact native lexical reconstruction. Their direct typed native paths remain
available where source evidence is sufficient.

## Scope discipline and roadmap

New work should improve fidelity, compatibility, safety, tests, or reduce complexity.
The project deliberately avoids broad platform features and keeps a soft production-size
ceiling around roughly twice the upstream MarkItDown implementation.

The approved broader parity program is in
`docs/superpowers/specs/2026-09-11-markitdown-2ways-full-parity-program-design.md`.
Current v0.5 execution documents are:

- `docs/superpowers/specs/2026-09-12-markitdown-2ways-phase-h1-text-source-preservation-design.md`
- `docs/superpowers/plans/2026-09-12-phase-h1-text-source-preservation-implementation.md`
- `docs/superpowers/specs/2026-09-12-markitdown-2ways-phase-h2-csv-source-preservation-design.md`
- `docs/superpowers/plans/2026-09-12-phase-h2-csv-source-preservation-implementation.md`
- `docs/superpowers/specs/2026-09-12-markitdown-2ways-phase-h3-json-source-preservation-design.md`
- `docs/superpowers/plans/2026-09-12-phase-h3-json-source-preservation-implementation.md`

After H3 is exact-head green, Phase H4 adds XML source preservation with namespace-aware
lexical ownership and target-only subtree/attribute/text mutation boundaries. HTML
follows with its own parser-recovery-aware source-preservation contract. Parser support
alone is never evidence that mutation is allowed.
