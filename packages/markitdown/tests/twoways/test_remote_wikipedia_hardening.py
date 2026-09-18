from __future__ import annotations

from io import BytesIO
import inspect
from pathlib import Path

import pytest

from markitdown import MarkItDown
from markitdown._stream_info import StreamInfo
from markitdown.twoways.readers import remote
from markitdown.twoways.readers.remote import (
    RemoteDerivedLimits,
    read_wikipedia_snapshot_ir,
)


FIXTURE = Path(__file__).parents[1] / "test_files" / "test_wikipedia.html"
BASE_URL = "https://en.wikipedia.org/wiki/Microsoft"


def _info(url: str | None = BASE_URL, **updates: object) -> StreamInfo:
    values = {
        "url": url,
        "mimetype": "text/html",
        "extension": ".html",
        "filename": "Microsoft.html",
        "charset": "utf-8",
    }
    values.update(updates)
    return StreamInfo(**values)


@pytest.mark.parametrize(
    "url",
    (
        None,
        "",
        "file:///tmp/wiki.html",
        "data:text/html,<p>x</p>",
        "ftp://en.wikipedia.org/wiki/Microsoft",
        "https://example.com/wiki/Microsoft",
        "https://wikipedia.org.example.com/wiki/Microsoft",
        "https://user@example.org@en.wikipedia.org/wiki/Microsoft",
        "https:///wiki/Microsoft",
    ),
)
def test_remote_reader_rejects_invalid_or_non_wikipedia_origin(
    url: str | None,
) -> None:
    with pytest.raises(ValueError):
        read_wikipedia_snapshot_ir(
            BytesIO(FIXTURE.read_bytes()),
            stream_info=_info(url),
        )


@pytest.mark.parametrize(
    "url",
    (
        "https://fr.wikipedia.org/wiki/Microsoft",
        "http://eng.wikipedia.org/wiki/Microsoft",
    ),
)
def test_remote_reader_accepts_current_converter_owned_language_hosts(url: str) -> None:
    document = read_wikipedia_snapshot_ir(
        BytesIO(FIXTURE.read_bytes()),
        stream_info=_info(url),
    )
    assert document.source is not None
    assert document.source.uri == url


def test_specialized_wikipedia_ownership_is_required() -> None:
    with pytest.raises(ValueError, match="WikipediaConverter|owned"):
        read_wikipedia_snapshot_ir(
            BytesIO(FIXTURE.read_bytes()),
            stream_info=_info(mimetype=None, extension=None),
        )


def test_source_limit_exact_boundary_succeeds_and_one_byte_over_fails() -> None:
    source = FIXTURE.read_bytes()
    exact = read_wikipedia_snapshot_ir(
        BytesIO(source),
        stream_info=_info(),
        limits=RemoteDerivedLimits(max_source_bytes=len(source)),
    )
    assert exact.source is not None
    assert exact.source.size_bytes == len(source)

    with pytest.raises(ValueError, match="max_source_bytes"):
        read_wikipedia_snapshot_ir(
            BytesIO(source),
            stream_info=_info(),
            limits=RemoteDerivedLimits(max_source_bytes=len(source) - 1),
        )


def test_markdown_limit_exact_boundary_succeeds_and_one_byte_below_fails() -> None:
    source = FIXTURE.read_bytes()
    info = _info()
    markdown = MarkItDown().convert_stream(BytesIO(source), stream_info=info).markdown
    size = len(markdown.encode("utf-8"))

    exact = read_wikipedia_snapshot_ir(
        BytesIO(source),
        stream_info=info,
        limits=RemoteDerivedLimits(max_markdown_utf8_bytes=size),
    )
    assert exact.root_node_ids

    with pytest.raises(ValueError, match="max_markdown_utf8_bytes"):
        read_wikipedia_snapshot_ir(
            BytesIO(source),
            stream_info=info,
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


def test_source_capture_never_uses_unbounded_read() -> None:
    source = FIXTURE.read_bytes()
    probe = _BoundedReadProbe(source, maximum_request=64 * 1024)
    read_wikipedia_snapshot_ir(
        probe,
        stream_info=_info(),
        limits=RemoteDerivedLimits(max_source_bytes=len(source)),
    )
    assert probe.requests
    assert all(0 <= size <= 64 * 1024 for size in probe.requests)


def test_remote_reader_module_has_no_network_or_process_imports() -> None:
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


def test_degenerate_html_remains_derived_not_writable() -> None:
    document = read_wikipedia_snapshot_ir(
        BytesIO(b"<html><title>Empty</title><body></body></html>"),
        stream_info=_info(filename="empty.html"),
    )
    node = document.nodes[document.root_node_ids[0]]
    assert node.native_locator is None
    assert node.metadata["twoways.capabilities.v1"][0]["state"] == "derived"
