from __future__ import annotations

from io import BytesIO

import pytest

from markitdown._stream_info import StreamInfo
from markitdown.twoways import (
    DocumentIntelligenceAnalysisSnapshot,
    DocumentIntelligenceDerivedLimits,
    read_document_intelligence_analysis_ir,
)

from .test_document_intelligence_reader import ANALYSIS_CONTENT, SOURCE, _analysis, _info


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
        ("model_id", ""),
        ("content_format", ""),
        ("api_version", ""),
        ("analysis_id", "   "),
    ),
)
def test_analysis_snapshot_rejects_blank_authority_fields(
    field: str,
    value: str,
) -> None:
    values = {
        "content": ANALYSIS_CONTENT,
        "provider": "offline-fixture",
        "model_id": "prebuilt-layout",
        "content_format": "markdown",
        "api_version": "2024-11-30",
        "analysis_id": "analysis-001",
    }
    values[field] = value
    with pytest.raises(ValueError, match="non-empty"):
        DocumentIntelligenceAnalysisSnapshot(**values)


def test_analysis_snapshot_rejects_non_string_content() -> None:
    with pytest.raises(TypeError, match="content"):
        DocumentIntelligenceAnalysisSnapshot(
            content=b"not text",
            provider="offline-fixture",
        )


@pytest.mark.parametrize(
    ("field", "value", "message"),
    (
        ("model_id", "custom-model", "prebuilt-layout"),
        ("content_format", "text", "markdown"),
    ),
)
def test_analysis_snapshot_freezes_one_way_semantic_contract(
    field: str,
    value: str,
    message: str,
) -> None:
    values = {
        "content": ANALYSIS_CONTENT,
        "provider": "offline-fixture",
        "model_id": "prebuilt-layout",
        "content_format": "markdown",
    }
    values[field] = value
    with pytest.raises(ValueError, match=message):
        DocumentIntelligenceAnalysisSnapshot(**values)


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("max_source_bytes", 0),
        ("max_analysis_utf8_bytes", 0),
        ("max_markdown_utf8_bytes", 0),
        ("max_source_bytes", True),
        ("max_analysis_utf8_bytes", False),
        ("max_markdown_utf8_bytes", 1.5),
    ),
)
def test_limits_fail_closed(field: str, value: object) -> None:
    with pytest.raises((TypeError, ValueError)):
        DocumentIntelligenceDerivedLimits(**{field: value})


def test_source_limit_accepts_exact_boundary_and_rejects_one_over() -> None:
    exact = read_document_intelligence_analysis_ir(
        BytesIO(SOURCE),
        stream_info=_info(),
        analysis=_analysis(),
        limits=DocumentIntelligenceDerivedLimits(max_source_bytes=len(SOURCE)),
    )
    assert exact.source is not None
    assert exact.source.size_bytes == len(SOURCE)

    with pytest.raises(ValueError, match="max_source_bytes"):
        read_document_intelligence_analysis_ir(
            BytesIO(SOURCE),
            stream_info=_info(),
            analysis=_analysis(),
            limits=DocumentIntelligenceDerivedLimits(
                max_source_bytes=len(SOURCE) - 1
            ),
        )


def test_source_capture_never_uses_unbounded_read() -> None:
    probe = _BoundedReadProbe(SOURCE, maximum_request=64 * 1024)
    read_document_intelligence_analysis_ir(
        probe,
        stream_info=_info(),
        analysis=_analysis(),
        limits=DocumentIntelligenceDerivedLimits(max_source_bytes=len(SOURCE)),
    )
    assert probe.requests
    assert all(0 <= size <= 64 * 1024 for size in probe.requests)


def test_analysis_limit_accepts_exact_boundary_and_rejects_one_over() -> None:
    size = len(ANALYSIS_CONTENT.encode("utf-8"))
    exact = read_document_intelligence_analysis_ir(
        BytesIO(SOURCE),
        stream_info=_info(),
        analysis=_analysis(),
        limits=DocumentIntelligenceDerivedLimits(max_analysis_utf8_bytes=size),
    )
    assert exact.root_node_ids

    with pytest.raises(ValueError, match="max_analysis_utf8_bytes"):
        read_document_intelligence_analysis_ir(
            BytesIO(SOURCE),
            stream_info=_info(),
            analysis=_analysis(),
            limits=DocumentIntelligenceDerivedLimits(
                max_analysis_utf8_bytes=size - 1
            ),
        )


def test_markdown_limit_accepts_exact_boundary_and_rejects_one_over() -> None:
    markdown = "# Demo\n\nVisible body\n"
    size = len(markdown.encode("utf-8"))
    exact = read_document_intelligence_analysis_ir(
        BytesIO(SOURCE),
        stream_info=_info(),
        analysis=_analysis(),
        limits=DocumentIntelligenceDerivedLimits(max_markdown_utf8_bytes=size),
    )
    assert exact.root_node_ids

    with pytest.raises(ValueError, match="max_markdown_utf8_bytes"):
        read_document_intelligence_analysis_ir(
            BytesIO(SOURCE),
            stream_info=_info(),
            analysis=_analysis(),
            limits=DocumentIntelligenceDerivedLimits(
                max_markdown_utf8_bytes=size - 1
            ),
        )


def test_analysis_must_use_explicit_snapshot_type() -> None:
    with pytest.raises(TypeError, match="DocumentIntelligenceAnalysisSnapshot"):
        read_document_intelligence_analysis_ir(
            BytesIO(SOURCE),
            stream_info=_info(),
            analysis={"content": ANALYSIS_CONTENT},
        )


def test_source_stream_must_return_bytes() -> None:
    class _TextStream:
        def read(self, size: int = -1) -> str:
            return "text"

    with pytest.raises(TypeError, match="bytes"):
        read_document_intelligence_analysis_ir(
            _TextStream(),
            stream_info=StreamInfo(
                mimetype="application/pdf",
                extension=".pdf",
                filename="demo.pdf",
            ),
            analysis=_analysis(),
        )
