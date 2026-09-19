# MarkItDown 2Ways v1.0.0

MarkItDown 2Ways v1.0.0 freezes the H1-H33 preservation-first bidirectional contract.

## Highlights

- 17 native format families with explicit bounded mutation authority.
- 12 derived semantic surfaces with explicit `native_writeback=false`.
- Evidence-driven `DocumentIR`, typed edits and capability reporting.
- Source/native ownership revalidation and fail-closed mutation.
- Canonical IR serialization with a machine-readable v1 compatibility corpus.
- H31 adversarial capability hardening.
- H32 golden compatibility court.
- H33 deterministic engineering budgets.
- Python 3.10-3.13 package/OCR CI coverage.

## Native families

Text/Markdown, CSV, JSON, XML, HTML, IPYNB, EPUB, ZIP, PDF, PNG, JPEG, MP3, MSG, XLS, XLSX, PPTX and DOCX.

## Derived surfaces

Wikipedia, Bing SERP, remote RSS/Atom, YouTube, Azure Document Intelligence, Azure Content Understanding, AudioConverter, ImageConverter, Outlook MSG converter, PdfConverter, XlsConverter and XlsxConverter.

## Compatibility

The product contract is `docs/twoways-v1-contract.json`. The serialized IR schema remains `MarkItDown2WaysDocument@0.1.0`; product version 1.0.0 and IR schema version are intentionally separate compatibility axes.

## Distribution

This release publishes GitHub wheel/sdist artifacts for this fork. It does not automatically publish or overwrite the upstream `markitdown` project on PyPI.

## Upstream

MarkItDown 2Ways is derived from Microsoft MarkItDown and retains upstream license and attribution notices.