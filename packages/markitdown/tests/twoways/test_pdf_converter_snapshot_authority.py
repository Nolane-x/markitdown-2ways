from __future__ import annotations

from io import BytesIO

import pytest

from markitdown.twoways import (
    PdfConverterExtractionSnapshot,
    PdfDerivedLimits,
    read_pdf_converter_snapshot_ir,
)

from .test_pdf_converter_snapshot_reader import (
    EXPECTED,
    INFO,
    RAW_TEXT,
    SOURCE,
    _snapshot,
)


class _BoundedReadProbe(BytesIO):
    def __init__(self, data: bytes, *, maximum_request: int) -> None:
        super().__init__(data)
        self.maximum_request = maximum_request
        self.requests: list[int] = []

    def read(self, size: int = -1) -> bytes:
        self.requests.append(size)
        if size < 0 or size > self.maximum_request:
            raise AssertionError(f"unbounded read request: {size}")
        return super().read(size)


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("provider", ""),
        ("provider", "   "),
        ("extraction_path", ""),
        ("extraction_path", " "),
        ("materialization_id", ""),
    ),
)
def test_snapshot_descriptors_reject_blank_values(
    field: str,
    value: str,
) -> None:
    values = {
        "extracted_text": RAW_TEXT,
        "provider": "fixture",
        "extraction_path": "pdfminer-whole-document",
        "materialization_id": "id-1",
    }
    values[field] = value
    with pytest.raises(ValueError, match=field):
        PdfConverterExtractionSnapshot(**values)


def test_snapshot_rejects_non_string_extracted_text() -> None:
    with pytest.raises(TypeError, match="extracted_text"):
        PdfConverterExtractionSnapshot(
            extracted_text=b"bytes",
            provider="fixture",
            extraction_path="pdfminer-whole-document",
        )


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("max_source_bytes", 0),
        ("max_extracted_utf8_bytes", 0),
        ("max_markdown_utf8_bytes", 0),
        ("max_source_bytes", True),
        ("max_extracted_utf8_bytes", False),
        ("max_markdown_utf8_bytes", 1.5),
    ),
)
def test_limits_fail_closed(field: str, value: object) -> None:
    with pytest.raises((TypeError, ValueError)):
        PdfDerivedLimits(**{field: value})


def test_source_limit_accepts_exact_boundary_and_reads_bounded() -> None:
    probe = _BoundedReadProbe(SOURCE, maximum_request=64 * 1024)
    exact = read_pdf_converter_snapshot_ir(
        probe,
        stream_info=INFO,
        snapshot=_snapshot(),
        limits=PdfDerivedLimits(max_source_bytes=len(SOURCE)),
    )
    assert exact.source is not None
    assert exact.source.size_bytes == len(SOURCE)
    assert probe.requests
    assert all(0 <= size <= 64 * 1024 for size in probe.requests)

    with pytest.raises(ValueError, match="max_source_bytes"):
        read_pdf_converter_snapshot_ir(
            BytesIO(SOURCE),
            stream_info=INFO,
            snapshot=_snapshot(),
            limits=PdfDerivedLimits(max_source_bytes=len(SOURCE) - 1),
        )


def test_extraction_and_markdown_limits_have_exact_boundaries() -> None:
    raw_size = len(RAW_TEXT.encode("utf-8"))
    markdown_size = len(EXPECTED.encode("utf-8"))

    exact = read_pdf_converter_snapshot_ir(
        BytesIO(SOURCE),
        stream_info=INFO,
        snapshot=_snapshot(),
        limits=PdfDerivedLimits(
            max_extracted_utf8_bytes=raw_size,
            max_markdown_utf8_bytes=markdown_size,
        ),
    )
    assert exact.root_node_ids

    with pytest.raises(ValueError, match="max_extracted_utf8_bytes"):
        read_pdf_converter_snapshot_ir(
            BytesIO(SOURCE),
            stream_info=INFO,
            snapshot=_snapshot(),
            limits=PdfDerivedLimits(max_extracted_utf8_bytes=raw_size - 1),
        )

    with pytest.raises(ValueError, match="max_markdown_utf8_bytes"):
        read_pdf_converter_snapshot_ir(
            BytesIO(SOURCE),
            stream_info=INFO,
            snapshot=_snapshot(),
            limits=PdfDerivedLimits(max_markdown_utf8_bytes=markdown_size - 1),
        )


def test_snapshot_must_use_explicit_type() -> None:
    with pytest.raises(TypeError, match="PdfConverterExtractionSnapshot"):
        read_pdf_converter_snapshot_ir(
            BytesIO(SOURCE),
            stream_info=INFO,
            snapshot={"extracted_text": RAW_TEXT},
        )


def test_source_stream_must_return_bytes() -> None:
    class _TextStream:
        def read(self, size: int = -1) -> str:
            return "text"

    with pytest.raises(TypeError, match="bytes"):
        read_pdf_converter_snapshot_ir(
            _TextStream(),
            stream_info=INFO,
            snapshot=_snapshot(),
        )
