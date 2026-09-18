from __future__ import annotations

from io import BytesIO

import pytest

from markitdown._stream_info import StreamInfo
from markitdown.twoways import (
    AudioConverterSnapshot,
    AudioDerivedLimits,
    read_audio_snapshot_ir,
)

from .test_audio_snapshot_reader import OUTPUT, SOURCE, _snapshot


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
        ("materialization_id", ""),
        ("metadata_provider", "   "),
        ("transcript_provider", ""),
    ),
)
def test_snapshot_rejects_blank_authority_fields(field: str, value: str) -> None:
    values = {
        "content": OUTPUT,
        "provider": "offline-fixture",
        "materialization_id": "audio-001",
        "metadata_provider": "fake-exiftool",
        "transcript_provider": "fake-transcriber",
    }
    values[field] = value
    with pytest.raises(ValueError, match="non-empty"):
        AudioConverterSnapshot(**values)


def test_snapshot_rejects_non_string_content() -> None:
    with pytest.raises(TypeError, match="content"):
        AudioConverterSnapshot(content=b"not-text", provider="offline-fixture")


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("max_source_bytes", 0),
        ("max_markdown_utf8_bytes", 0),
        ("max_source_bytes", True),
        ("max_markdown_utf8_bytes", False),
        ("max_markdown_utf8_bytes", 1.5),
    ),
)
def test_limits_fail_closed(field: str, value: object) -> None:
    with pytest.raises((TypeError, ValueError)):
        AudioDerivedLimits(**{field: value})


def test_source_limit_accepts_exact_boundary_and_rejects_one_over() -> None:
    exact = read_audio_snapshot_ir(
        BytesIO(SOURCE),
        stream_info=StreamInfo(extension=".wav"),
        snapshot=_snapshot(),
        limits=AudioDerivedLimits(max_source_bytes=len(SOURCE)),
    )
    assert exact.source is not None
    assert exact.source.size_bytes == len(SOURCE)

    with pytest.raises(ValueError, match="max_source_bytes"):
        read_audio_snapshot_ir(
            BytesIO(SOURCE),
            stream_info=StreamInfo(extension=".wav"),
            snapshot=_snapshot(),
            limits=AudioDerivedLimits(max_source_bytes=len(SOURCE) - 1),
        )


def test_source_capture_never_uses_unbounded_read() -> None:
    probe = _BoundedReadProbe(SOURCE, maximum_request=64 * 1024)
    read_audio_snapshot_ir(
        probe,
        stream_info=StreamInfo(extension=".wav"),
        snapshot=_snapshot(),
        limits=AudioDerivedLimits(max_source_bytes=len(SOURCE)),
    )
    assert probe.requests
    assert all(0 <= size <= 64 * 1024 for size in probe.requests)


def test_markdown_limit_accepts_exact_boundary_and_rejects_one_over() -> None:
    size = len(OUTPUT.encode("utf-8"))
    exact = read_audio_snapshot_ir(
        BytesIO(SOURCE),
        stream_info=StreamInfo(extension=".wav"),
        snapshot=_snapshot(),
        limits=AudioDerivedLimits(max_markdown_utf8_bytes=size),
    )
    assert exact.root_node_ids

    with pytest.raises(ValueError, match="max_markdown_utf8_bytes"):
        read_audio_snapshot_ir(
            BytesIO(SOURCE),
            stream_info=StreamInfo(extension=".wav"),
            snapshot=_snapshot(),
            limits=AudioDerivedLimits(max_markdown_utf8_bytes=size - 1),
        )


@pytest.mark.parametrize(
    ("extension", "mimetype"),
    (
        (".ogg", None),
        (".flac", None),
        (".aac", None),
        (None, "audio/ogg"),
        (None, "audio/flac"),
        (None, "application/octet-stream"),
        (None, None),
    ),
)
def test_unsupported_one_way_surface_fails_closed(
    extension: str | None,
    mimetype: str | None,
) -> None:
    with pytest.raises(ValueError, match="AudioConverter"):
        read_audio_snapshot_ir(
            BytesIO(SOURCE),
            stream_info=StreamInfo(extension=extension, mimetype=mimetype),
            snapshot=_snapshot(),
        )


def test_stream_must_return_bytes() -> None:
    class _TextStream:
        def read(self, size: int = -1) -> str:
            return "text"

    with pytest.raises(TypeError, match="bytes"):
        read_audio_snapshot_ir(
            _TextStream(),
            stream_info=StreamInfo(extension=".wav"),
            snapshot=_snapshot(),
        )
