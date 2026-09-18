from __future__ import annotations

from io import BytesIO
import inspect

import pytest

from markitdown._stream_info import StreamInfo
from markitdown.twoways.readers import remote
from markitdown.twoways.readers.remote import (
    RemoteDerivedLimits,
    read_bing_serp_snapshot_ir,
)

from .test_remote_bing_serp_reader import BING_URL, SNAPSHOT


def _info(url: str | None = BING_URL, **updates: object) -> StreamInfo:
    values = {
        "url": url,
        "mimetype": "text/html",
        "extension": ".html",
        "filename": "bing.html",
        "charset": "utf-8",
    }
    values.update(updates)
    return StreamInfo(**values)


@pytest.mark.parametrize(
    "url",
    (
        None,
        "",
        "http://www.bing.com/search?q=markitdown",
        "file:///tmp/bing.html",
        "data:text/html,<p>x</p>",
        "ftp://www.bing.com/search?q=markitdown",
        "https://bing.com/search?q=markitdown",
        "https://www.bing.com.example.com/search?q=markitdown",
        "https://example.com/search?q=markitdown",
        "https://user:secret@www.bing.com/search?q=markitdown",
        "https:///search?q=markitdown",
        "https://www.bing.com/",
        "https://www.bing.com/search?x=markitdown",
    ),
)
def test_bing_reader_rejects_invalid_or_non_owned_origins(
    url: str | None,
) -> None:
    with pytest.raises(ValueError):
        read_bing_serp_snapshot_ir(
            BytesIO(SNAPSHOT),
            stream_info=_info(url),
        )


def test_bing_specialized_converter_ownership_is_required() -> None:
    with pytest.raises(ValueError, match="BingSerpConverter|owned"):
        read_bing_serp_snapshot_ir(
            BytesIO(SNAPSHOT),
            stream_info=_info(mimetype=None, extension=None),
        )


def test_bing_source_limit_exact_boundary_and_one_byte_over() -> None:
    document = read_bing_serp_snapshot_ir(
        BytesIO(SNAPSHOT),
        stream_info=_info(),
        limits=RemoteDerivedLimits(max_source_bytes=len(SNAPSHOT)),
    )
    assert document.source is not None
    assert document.source.size_bytes == len(SNAPSHOT)

    with pytest.raises(ValueError, match="max_source_bytes"):
        read_bing_serp_snapshot_ir(
            BytesIO(SNAPSHOT),
            stream_info=_info(),
            limits=RemoteDerivedLimits(max_source_bytes=len(SNAPSHOT) - 1),
        )


def test_bing_markdown_limit_exact_boundary_and_one_byte_over() -> None:
    baseline = read_bing_serp_snapshot_ir(
        BytesIO(SNAPSHOT),
        stream_info=_info(),
    )
    node = baseline.nodes[baseline.root_node_ids[0]]
    size = len(node.payload.text.encode("utf-8"))

    exact = read_bing_serp_snapshot_ir(
        BytesIO(SNAPSHOT),
        stream_info=_info(),
        limits=RemoteDerivedLimits(max_markdown_utf8_bytes=size),
    )
    assert exact.root_node_ids

    with pytest.raises(ValueError, match="max_markdown_utf8_bytes"):
        read_bing_serp_snapshot_ir(
            BytesIO(SNAPSHOT),
            stream_info=_info(),
            limits=RemoteDerivedLimits(max_markdown_utf8_bytes=size - 1),
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


def test_bing_source_capture_never_uses_unbounded_read() -> None:
    probe = _BoundedReadProbe(SNAPSHOT, maximum_request=64 * 1024)

    read_bing_serp_snapshot_ir(
        probe,
        stream_info=_info(),
        limits=RemoteDerivedLimits(max_source_bytes=len(SNAPSHOT)),
    )

    assert probe.requests
    assert all(0 <= size <= 64 * 1024 for size in probe.requests)


def test_remote_reader_module_still_has_no_network_or_process_imports() -> None:
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


def test_degenerate_bing_html_remains_derived_not_writable() -> None:
    source = b"<html><head><title>Empty Bing</title></head><body></body></html>"
    document = read_bing_serp_snapshot_ir(
        BytesIO(source),
        stream_info=_info(filename="empty-bing.html"),
    )
    node = document.nodes[document.root_node_ids[0]]

    assert node.native_locator is None
    assert node.metadata["twoways.capabilities.v1"][0]["state"] == "derived"
