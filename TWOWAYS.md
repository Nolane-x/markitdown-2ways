# MarkItDown 2Ways

MarkItDown 2Ways is the focused two-way layer in this fork. It keeps the existing
one-way `MarkItDown` API and CLI intact, and adds a bounded round-trip path for
high-value Office formats:

```text
native document -> DocumentIR -> Markdown / typed edits -> native document
```

The current production scope is intentionally small: Core IR, Markdown round trip,
PPTX, and DOCX. This is not intended to become an Office automation platform,
workflow engine, document-management service, or general application framework.

## Install this fork

The 2Ways layer is developed in this repository. Install the fork from source rather
than assuming the upstream PyPI package contains these APIs:

```bash
git clone https://github.com/Nolane-x/markitdown-2ways.git
cd markitdown-2ways
pip install -e 'packages/markitdown[pptx,docx]'
```

The original one-way API remains available:

```python
from markitdown import MarkItDown

result = MarkItDown().convert("report.pdf")
print(result.markdown)
```

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

## Current capability boundary

| Area | PPTX | DOCX |
| --- | --- | --- |
| Read into `DocumentIR` | slides, groups, notes, text, pictures, tables, charts | body, headers, footers, text, hyperlinks, pictures, tables |
| Text patch | compatible slide/group/notes text | compatible body/header/footer/hyperlink text |
| Picture alt text | patchable | patchable |
| Tables | semantic read-only | semantic read-only |
| Charts | semantic read-only | native-preserved / unsupported for mutation |
| Unsupported complex native edits | fail closed | fail closed |

Complex layout/style/numbering/field/tracked-change/media mutations are intentionally
outside the current write surface. The preservation writer starts from the original
OOXML package and edits only authorized parts.

## Fidelity and safety model

The round-trip layer is designed around explicit proof rather than best-effort rebuilds:

- source package SHA-256 is bound to the `DocumentIR`;
- edits can carry semantic, native-locator, and expected-old-value preconditions;
- native locators are resolved strictly inside the designated OOXML part;
- no-op patching preserves the original file byte-for-byte;
- unrelated package members and native subtrees are verified after writes;
- malformed or ambiguous OPC member paths fail closed;
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
