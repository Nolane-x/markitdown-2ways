from __future__ import annotations

from io import BytesIO
import inspect

import pytest

from markitdown.twoways.readers import youtube
from markitdown.twoways.readers.youtube import (
    YouTubeDerivedLimits,
    read_youtube_snapshot_ir,
)

from .test_remote_youtube_reader import HTML_SNAPSHOT, VIDEO_ID, WATCH_URL, _info


@pytest.mark.parametrize(
    "url",
    (
        None,
        "",
        "file:///tmp/video.html",
        "data:text/html,<p>x</p>",
        "ftp://www.youtube.com/watch?v=abc123DEF45",
        "https://youtube.com.example.com/watch?v=abc123DEF45",
        "https://example.com/watch?v=abc123DEF45",
        "https://user:secret@www.youtube.com/watch?v=abc123DEF45",
        "https://www.youtube.com:bad/watch?v=abc123DEF45",
        "https://www.youtube.com:443/watch?v=abc123DEF45",
        "https:///watch?v=abc123DEF45",
        "https://www.youtube.com/watch",
        "https://www.youtube.com/watch?x=abc123DEF45",
        "https://www.youtube.com/channel/abc123DEF45",
        "https://youtu.be/",
    ),
)
def test_youtube_reader_rejects_invalid_or_non_owned_origins(
    url: str | None,
) -> None:
    with pytest.raises(ValueError):
        read_youtube_snapshot_ir(
            BytesIO(HTML_SNAPSHOT),
            stream_info=_info(url),
        )


def test_youtube_reader_requires_html_converter_ownership() -> None:
    with pytest.raises(ValueError, match="YouTubeConverter|owned"):
        read_youtube_snapshot_ir(
            BytesIO(HTML_SNAPSHOT),
            stream_info=_info(mimetype=None, extension=None),
        )


def test_youtube_source_limit_exact_boundary_and_one_byte_over() -> None:
    exact = read_youtube_snapshot_ir(
        BytesIO(HTML_SNAPSHOT),
        stream_info=_info(),
        limits=YouTubeDerivedLimits(max_html_bytes=len(HTML_SNAPSHOT)),
    )
    assert exact.source is not None
    assert exact.source.size_bytes == len(HTML_SNAPSHOT)

    with pytest.raises(ValueError, match="max_html_bytes"):
        read_youtube_snapshot_ir(
            BytesIO(HTML_SNAPSHOT),
            stream_info=_info(),
            limits=YouTubeDerivedLimits(max_html_bytes=len(HTML_SNAPSHOT) - 1),
        )


def test_youtube_markdown_limit_exact_boundary_and_one_byte_over() -> None:
    baseline = read_youtube_snapshot_ir(
        BytesIO(HTML_SNAPSHOT),
        stream_info=_info(),
    )
    node = baseline.nodes[baseline.root_node_ids[0]]
    size = len(node.payload.text.encode("utf-8"))

    exact = read_youtube_snapshot_ir(
        BytesIO(HTML_SNAPSHOT),
        stream_info=_info(),
        limits=YouTubeDerivedLimits(max_markdown_utf8_bytes=size),
    )
    assert exact.root_node_ids

    with pytest.raises(ValueError, match="max_markdown_utf8_bytes"):
        read_youtube_snapshot_ir(
            BytesIO(HTML_SNAPSHOT),
            stream_info=_info(),
            limits=YouTubeDerivedLimits(max_markdown_utf8_bytes=size - 1),
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


def test_youtube_source_capture_never_uses_unbounded_read() -> None:
    probe = _BoundedReadProbe(HTML_SNAPSHOT, maximum_request=64 * 1024)

    read_youtube_snapshot_ir(
        probe,
        stream_info=_info(),
        limits=YouTubeDerivedLimits(max_html_bytes=len(HTML_SNAPSHOT)),
    )

    assert probe.requests
    assert all(0 <= size <= 64 * 1024 for size in probe.requests)


def test_youtube_reader_has_no_network_process_or_transcript_service_imports() -> None:
    source = inspect.getsource(youtube)
    forbidden = (
        "youtube_transcript_api",
        "import requests",
        "from requests",
        "import httpx",
        "from httpx",
        "urllib.request",
        "import socket",
        "from socket",
        "import subprocess",
        "from subprocess",
        "import selenium",
        "from selenium",
        "import playwright",
        "from playwright",
        "time.sleep",
    )
    assert not any(token in source for token in forbidden)


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("max_html_bytes", 0),
        ("max_transcript_utf8_bytes", 0),
        ("max_markdown_utf8_bytes", 0),
        ("max_html_bytes", True),
        ("max_transcript_utf8_bytes", False),
    ),
)
def test_youtube_limits_fail_closed(field: str, value: object) -> None:
    with pytest.raises((TypeError, ValueError)):
        YouTubeDerivedLimits(**{field: value})


def test_uppercase_owned_host_is_accepted_without_weakening_authority() -> None:
    url = f"https://WWW.YOUTUBE.COM/watch?v={VIDEO_ID}"
    document = read_youtube_snapshot_ir(
        BytesIO(HTML_SNAPSHOT),
        stream_info=_info(url),
    )
    assert document.source is not None
    assert document.source.uri == url
    assert (
        document.metadata.custom["twoways.youtube_snapshot.v1"]["video_id"] == VIDEO_ID
    )


def test_escaped_current_converter_url_shape_is_supported() -> None:
    url = f"https://www.youtube.com/watch\\?v\\={VIDEO_ID}"
    document = read_youtube_snapshot_ir(
        BytesIO(HTML_SNAPSHOT),
        stream_info=_info(url),
    )
    assert document.source is not None
    assert document.source.uri == url
    assert document.metadata.custom["twoways.youtube_snapshot.v1"]["video_id"] == VIDEO_ID


def test_http_remains_in_current_h21_frozen_boundary() -> None:
    url = WATCH_URL.replace("https://", "http://", 1)
    document = read_youtube_snapshot_ir(
        BytesIO(HTML_SNAPSHOT),
        stream_info=_info(url),
    )
    assert document.source is not None
    assert document.source.uri == url
