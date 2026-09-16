from __future__ import annotations

from io import BytesIO

import pytest

from markitdown.twoways.formats.json.reader import read_json_ir
from markitdown.twoways.formats.pdf import (
    PdfIRReader,
    PdfNativeLimits,
    PdfParseError,
    PdfPatchWriter,
    parse_pdf_source,
    patch_pdf,
    read_pdf_ir,
)
from markitdown.twoways.writers.base import TargetInfo

from ._pdf_fixtures import make_metadata_pdf


def test_pdf_public_format_surface() -> None:
    assert PdfIRReader.__name__ == "PdfIRReader"
    assert PdfPatchWriter.__name__ == "PdfPatchWriter"
    assert PdfParseError.__name__ == "PdfParseError"
    assert PdfNativeLimits.__name__ == "PdfNativeLimits"
    assert callable(parse_pdf_source)
    assert callable(patch_pdf)
    assert callable(read_pdf_ir)


def test_pdf_patch_writer_accepts_only_pdf_backed_targets() -> None:
    writer = PdfPatchWriter()
    source = make_metadata_pdf()
    document = read_pdf_ir(BytesIO(source), filename="metadata.pdf")
    json_document = read_json_ir(BytesIO(b"{}"), filename="data.json")

    assert writer.accepts(document, TargetInfo(format="pdf"))
    assert writer.accepts(document, TargetInfo(format="native", extension=".PDF"))
    assert not writer.accepts(document, TargetInfo(format="zip", extension=".zip"))
    assert not writer.accepts(
        json_document,
        TargetInfo(format="pdf", extension=".pdf"),
    )


def test_pdf_patch_writer_requires_source_stream_and_edits() -> None:
    writer = PdfPatchWriter()
    source = make_metadata_pdf()
    document = read_pdf_ir(BytesIO(source), filename="metadata.pdf")

    with pytest.raises(TypeError, match="source_stream=.*edits="):
        writer.write(document, BytesIO(), TargetInfo(format="pdf"))


def test_pdf_patch_writer_rejects_unknown_options() -> None:
    writer = PdfPatchWriter()
    source = make_metadata_pdf()
    document = read_pdf_ir(BytesIO(source), filename="metadata.pdf")

    with pytest.raises(TypeError, match="unexpected PDF writer options"):
        writer.write(
            document,
            BytesIO(),
            TargetInfo(format="pdf"),
            source_stream=BytesIO(source),
            edits=(),
            surprise=True,
        )
