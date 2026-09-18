from __future__ import annotations

from io import BytesIO

import pytest

from markitdown._stream_info import StreamInfo
from markitdown.twoways import (
    ContentUnderstandingAnalysisSnapshot,
    ContentUnderstandingDerivedLimits,
    read_content_understanding_analysis_ir,
)

from .test_content_understanding_reader import (
    OUTPUT,
    PDF_INFO,
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
        ("analyzer_id", ""),
        ("content_type", "   "),
        ("api_version", ""),
        ("analysis_id", "   "),
    ),
)
def test_snapshot_rejects_blank_authority_fields(field: str, value: str) -> None:
    values = {
        "content": OUTPUT,
        "provider": "offline-fixture",
        "analyzer_id": "prebuilt-documentSearch",
        "content_type": "application/pdf",
        "api_version": "2025-05-01-preview",
        "analysis_id": "analysis-001",
    }
    values[field] = value
    with pytest.raises(ValueError, match="non-empty"):
        ContentUnderstandingAnalysisSnapshot(**values)


def test_snapshot_rejects_non_string_content() -> None:
    with pytest.raises(TypeError, match="content"):
        ContentUnderstandingAnalysisSnapshot(
            content=b"not text",
            provider="offline-fixture",
            analyzer_id="prebuilt-documentSearch",
            content_type="application/pdf",
        )


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("max_source_bytes", 0),
        ("max_analysis_utf8_bytes", 0),
        ("max_source_bytes", True),
        ("max_analysis_utf8_bytes", False),
        ("max_analysis_utf8_bytes", 1.5),
    ),
)
def test_limits_fail_closed(field: str, value: object) -> None:
    with pytest.raises((TypeError, ValueError)):
        ContentUnderstandingDerivedLimits(**{field: value})


def test_source_limit_accepts_exact_boundary_and_rejects_one_over() -> None:
    exact = read_content_understanding_analysis_ir(
        BytesIO(SOURCE),
        stream_info=PDF_INFO,
        analysis=_snapshot(),
        limits=ContentUnderstandingDerivedLimits(max_source_bytes=len(SOURCE)),
    )
    assert exact.source is not None
    assert exact.source.size_bytes == len(SOURCE)

    with pytest.raises(ValueError, match="max_source_bytes"):
        read_content_understanding_analysis_ir(
            BytesIO(SOURCE),
            stream_info=PDF_INFO,
            analysis=_snapshot(),
            limits=ContentUnderstandingDerivedLimits(max_source_bytes=len(SOURCE) - 1),
        )


def test_source_capture_never_uses_unbounded_read() -> None:
    probe = _BoundedReadProbe(SOURCE, maximum_request=64 * 1024)
    read_content_understanding_analysis_ir(
        probe,
        stream_info=PDF_INFO,
        analysis=_snapshot(),
        limits=ContentUnderstandingDerivedLimits(max_source_bytes=len(SOURCE)),
    )

    assert probe.requests
    assert all(0 <= size <= 64 * 1024 for size in probe.requests)


def test_analysis_limit_accepts_exact_boundary_and_rejects_one_over() -> None:
    size = len(OUTPUT.encode("utf-8"))
    exact = read_content_understanding_analysis_ir(
        BytesIO(SOURCE),
        stream_info=PDF_INFO,
        analysis=_snapshot(),
        limits=ContentUnderstandingDerivedLimits(max_analysis_utf8_bytes=size),
    )
    assert exact.root_node_ids

    with pytest.raises(ValueError, match="max_analysis_utf8_bytes"):
        read_content_understanding_analysis_ir(
            BytesIO(SOURCE),
            stream_info=PDF_INFO,
            analysis=_snapshot(),
            limits=ContentUnderstandingDerivedLimits(max_analysis_utf8_bytes=size - 1),
        )


@pytest.mark.parametrize(
    ("info", "analyzer_id", "content_type", "message"),
    (
        (
            StreamInfo(extension=".pdf", mimetype="audio/mpeg"),
            "prebuilt-audioSearch",
            "application/pdf",
            "analyzer_id",
        ),
        (
            StreamInfo(extension=".pdf", mimetype="audio/mpeg"),
            "prebuilt-documentSearch",
            "audio/mpeg",
            "content_type",
        ),
        (
            StreamInfo(extension=".mp3", mimetype="application/pdf"),
            "prebuilt-documentSearch",
            "audio/mpeg",
            "analyzer_id",
        ),
    ),
)
def test_routing_descriptors_fail_closed(
    info: StreamInfo,
    analyzer_id: str,
    content_type: str,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        read_content_understanding_analysis_ir(
            BytesIO(SOURCE),
            stream_info=info,
            analysis=_snapshot(
                analyzer_id=analyzer_id,
                content_type=content_type,
            ),
        )


@pytest.mark.parametrize(
    ("mimetype", "analyzer_id", "content_type"),
    (
        ("audio/x-wav", "prebuilt-audioSearch", "audio/wav"),
        ("audio/x-flac", "prebuilt-audioSearch", "audio/flac"),
        ("audio/x-m4a", "prebuilt-audioSearch", "audio/mp4"),
        ("video/x-m4v", "prebuilt-videoSearch", "video/mp4"),
        ("image/heic", "prebuilt-documentSearch", "image/heic"),
    ),
)
def test_mime_aliases_are_canonicalized_like_one_way(
    mimetype: str,
    analyzer_id: str,
    content_type: str,
) -> None:
    document = read_content_understanding_analysis_ir(
        BytesIO(SOURCE),
        stream_info=StreamInfo(mimetype=mimetype),
        analysis=_snapshot(
            analyzer_id=analyzer_id,
            content_type=content_type,
            api_version=None,
            analysis_id=None,
        ),
    )
    evidence = document.metadata.custom["twoways.content_understanding_analysis.v1"]
    assert evidence["analyzer_id"] == analyzer_id
    assert evidence["content_type"] == content_type


def test_extension_authority_wins_over_conflicting_mimetype() -> None:
    document = read_content_understanding_analysis_ir(
        BytesIO(SOURCE),
        stream_info=StreamInfo(extension=".pdf", mimetype="audio/mpeg"),
        analysis=_snapshot(api_version=None, analysis_id=None),
    )
    evidence = document.metadata.custom["twoways.content_understanding_analysis.v1"]
    assert evidence["file_type"] == "pdf"
    assert evidence["modality"] == "document"
    assert evidence["analyzer_id"] == "prebuilt-documentSearch"
    assert evidence["content_type"] == "application/pdf"


@pytest.mark.parametrize(
    ("extension", "mimetype"),
    (
        (".csv", None),
        (".json", None),
        (".zip", None),
        (".epub", None),
        (None, "text/csv"),
        (None, "application/json"),
        (None, None),
    ),
)
def test_unsupported_default_surface_fails_closed(
    extension: str | None,
    mimetype: str | None,
) -> None:
    with pytest.raises(ValueError, match="ContentUnderstandingConverter"):
        read_content_understanding_analysis_ir(
            BytesIO(SOURCE),
            stream_info=StreamInfo(extension=extension, mimetype=mimetype),
            analysis=_snapshot(),
        )
