from __future__ import annotations

from io import BytesIO
import inspect

import pytest

from markitdown import MarkItDown
from markitdown.twoways.readers import remote
from markitdown.twoways.readers.remote import (
    RemoteDerivedLimits,
    read_remote_feed_snapshot_ir,
)

from .test_remote_feed_reader import RSS_FIXTURE, _rss_info


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


def test_feed_source_limit_exact_boundary_and_one_byte_over() -> None:
    source = RSS_FIXTURE.read_bytes()
    exact = read_remote_feed_snapshot_ir(
        BytesIO(source),
        stream_info=_rss_info(),
        limits=RemoteDerivedLimits(max_source_bytes=len(source)),
    )
    assert exact.source is not None
    assert exact.source.size_bytes == len(source)

    with pytest.raises(ValueError, match="max_source_bytes"):
        read_remote_feed_snapshot_ir(
            BytesIO(source),
            stream_info=_rss_info(),
            limits=RemoteDerivedLimits(max_source_bytes=len(source) - 1),
        )


def test_feed_source_capture_never_uses_unbounded_read() -> None:
    source = RSS_FIXTURE.read_bytes()
    probe = _BoundedReadProbe(source, maximum_request=64 * 1024)

    read_remote_feed_snapshot_ir(
        probe,
        stream_info=_rss_info(),
        limits=RemoteDerivedLimits(max_source_bytes=len(source)),
    )

    assert probe.requests
    assert all(0 <= size <= 64 * 1024 for size in probe.requests)


def test_feed_markdown_limit_exact_boundary_and_one_byte_below() -> None:
    source = RSS_FIXTURE.read_bytes()
    info = _rss_info()
    markdown = MarkItDown().convert_stream(BytesIO(source), stream_info=info).markdown
    size = len(markdown.encode("utf-8"))

    exact = read_remote_feed_snapshot_ir(
        BytesIO(source),
        stream_info=info,
        limits=RemoteDerivedLimits(max_markdown_utf8_bytes=size),
    )
    assert exact.root_node_ids

    with pytest.raises(ValueError, match="max_markdown_utf8_bytes"):
        read_remote_feed_snapshot_ir(
            BytesIO(source),
            stream_info=info,
            limits=RemoteDerivedLimits(max_markdown_utf8_bytes=size - 1),
        )


def test_remote_reader_module_has_no_network_or_process_imports_after_h20() -> None:
    source = inspect.getsource(remote)
    forbidden = (
        "import requests",
        "from requests",
        "import httpx",
        "from httpx",
        "urllib.request",
        "import socket",
        "from socket",
        "import subprocess",
        "from subprocess",
    )
    assert not any(token in source for token in forbidden)
