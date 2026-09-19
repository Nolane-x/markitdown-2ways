# MarkItDown 2Ways

> Preservation-first, evidence-driven bidirectional document editing built on top of Microsoft MarkItDown.

MarkItDown 2Ways keeps the original one-way `MarkItDown` API and CLI while adding a bounded two-way layer:

```text
native document -> DocumentIR -> Markdown / typed edits -> native document
```

The project is designed around one rule: **understanding a document is not the same as owning the right to mutate it**. Readers expose explicit capability evidence, writers re-check native ownership and preconditions, and ambiguous mutations fail closed.

## v1.0 status

v1.0 freezes the proven H1-H33 boundary:

- 17 native format families with explicit read/write contracts;
- 12 derived semantic surfaces with `native_writeback=false`;
- source-preserving mutation for supported owners rather than whole-document regeneration;
- deterministic canonical `DocumentIR` serialization and compatibility goldens;
- adversarial capability hardening and fail-closed defaults;
- deterministic engineering budgets for source size, public surface and core dependencies.

The machine-readable contract is in [`docs/twoways-v1-contract.json`](docs/twoways-v1-contract.json). The full technical specification, examples and phase history are in [`TWOWAYS.md`](TWOWAYS.md).

## Why 2Ways?

Ordinary conversion tools answer: **what text can I extract?** 2Ways also asks:

- Which semantic node maps to which native owner?
- Is that owner writable, read-only or merely derived?
- Can the requested edit be expressed without rewriting unrelated bytes or package members?
- Has the source changed since the edit was prepared?
- Can the candidate output be re-read and verified before it is emitted?

This allows narrow edits to preserve far more of the original representation while refusing operations that cannot be proven safe.

## Native support

| Format | Native mutation boundary |
| --- | --- |
| Text / Markdown | source-preserving `replace_text` |
| CSV | target-only cell updates |
| JSON | lexical scalar replacement |
| XML | lexical text / attribute replacement |
| HTML | recovery-aware text / quoted-attribute replacement |
| IPYNB | target cell-source replacement |
| EPUB | package-preserving metadata / XHTML text replacement |
| ZIP | preservation/routing container for supported inner edits |
| PDF | bounded metadata, URI-link and terminal text-field updates |
| PNG | existing text metadata owners |
| JPEG | existing fixed-allocation Exif text owners |
| MP3 | existing ID3v1 fixed slots |
| MSG | existing top-level Unicode Subject stream |
| XLS | existing BIFF8 NUMBER slots |
| XLSX | typed non-formula, non-merged cell updates |
| PPTX | bounded text/style/geometry/alt-text/table edits |
| DOCX | bounded text/style/alt-text/table edits |

Everything outside a proven native boundary remains read-only or unsupported.

## Derived semantic parity

2Ways also preserves semantics from one-way converter surfaces without pretending those semantics are writable native ownership:

- Wikipedia
- Bing SERP
- remote RSS/Atom
- YouTube HTML + optional transcript provenance
- Azure Document Intelligence analysis
- Azure Content Understanding analysis
- AudioConverter materialized output
- ImageConverter metadata / caption output
- Outlook MSG converter semantics
- PdfConverter extraction output
- XlsConverter sheet Markdown
- XlsxConverter sheet Markdown

All v1 derived surfaces remain explicitly non-writeback.

## Install this fork

```bash
git clone https://github.com/Nolane-x/markitdown-2ways.git
cd markitdown-2ways
pip install -e 'packages/markitdown[all]'
```

Python 3.10-3.13 are covered by the repository CI matrix.

## One-way API remains available

```python
from markitdown import MarkItDown

result = MarkItDown().convert('report.pdf')
print(result.markdown)
```

The fork intentionally keeps the original MarkItDown conversion workflow available alongside 2Ways.

### Upstream LLM image-description behavior

The synced one-way converter path follows upstream MarkItDown's client-driven retry behavior. For OpenAI-compatible clients, retry policy is configured on the client itself (for example, `OpenAI(max_retries=5)`). If image description still fails after the client's retries, MarkItDown can continue through other applicable converter fallbacks and raises `FileConversionException` only when no converter succeeds.

## 2Ways example

```python
from io import BytesIO

from markitdown.twoways import EditOperation
from markitdown.twoways.formats.text import patch_text, read_text_ir

source = b'# Title\n\nOriginal text.\n'
document = read_text_ir(BytesIO(source), filename='example.md')
node_id = document.canvases[0].root_node_ids[0]

edit = EditOperation(
    operation_id='edit-1',
    type='replace_text',
    target_node_id=node_id,
    payload={'text': '# Title\n\nUpdated text.\n'},
)

output = BytesIO()
patch_text(document, BytesIO(source), output, edits=(edit,))
assert output.getvalue() == b'# Title\n\nUpdated text.\n'
```

For format-specific APIs and preservation rules, see [`TWOWAYS.md`](TWOWAYS.md).

## Safety model

2Ways treats mutation authority as evidence, not inference:

- source SHA-256 and byte size are bound and re-checked;
- unadvertised operations default to read-only;
- typed edits may carry expected semantic/native/value preconditions;
- complete transactions are preflighted before writing;
- malformed or ambiguous ownership fails closed;
- format-specific verification protects untouched regions;
- derived semantics never automatically become native write authority;
- the 2Ways core performs no hidden network or subprocess action for its derived snapshot readers.

## Compatibility and engineering gates

Before v1.0, three final hardening phases were added:

- **H31 — Adversarial capability hardening:** immutable capability constraints, validated defaults and malformed-wire courts.
- **H32 — v1 compatibility corpus:** frozen canonical byte sizes/SHA-256 digests plus strict/forward decoder behavior.
- **H33 — deterministic engineering budgets:** bounded source size, file count, public/support cardinality and core dependencies.

Required PR CI continues to run pre-commit plus package and OCR test matrices on Python 3.10, 3.11, 3.12 and 3.13.

## Project scope

MarkItDown 2Ways is a document conversion and preservation library. It is not a workflow engine, browser automation system, document management service, Office automation replacement or hosted conversion platform.

New work should improve fidelity, compatibility, safety, tests, performance or implementation clarity without weakening the native/derived authority boundary.

## Upstream

This repository is a fork of [`microsoft/markitdown`](https://github.com/microsoft/markitdown). The original MarkItDown project, contributors, license notices and third-party notices remain acknowledged in this repository. 2Ways-specific behavior and contracts are maintained in this fork.

## License

MIT. See [`LICENSE`](LICENSE), [`ThirdPartyNotices.md`](packages/markitdown/ThirdPartyNotices.md) and the repository notices for details.
