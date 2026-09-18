from __future__ import annotations

from io import BytesIO

import pytest

from markitdown._stream_info import StreamInfo
from markitdown.twoways.formats.xml import read_xml_ir
from markitdown.twoways.readers.remote import read_remote_feed_snapshot_ir

from .test_remote_feed_reader import ATOM_SNAPSHOT, RSS_FIXTURE


def _rss_info(url: str | None) -> StreamInfo:
    return StreamInfo(
        url=url,
        mimetype="application/rss+xml",
        extension=".rss",
        filename="feed.rss",
        charset="utf-8",
    )


def test_same_rss_bytes_keep_native_xml_authority_when_read_as_local_xml() -> None:
    source = RSS_FIXTURE.read_bytes()

    document = read_xml_ir(
        BytesIO(source),
        filename="feed.xml",
        mimetype="application/xml",
        encoding="utf-8",
    )

    assert document.source is not None
    assert document.source.format == "xml"
    assert document.source.uri is None
    assert document.source.preserved_source_ref is not None
    assert document.canvases[0].native_locator is not None
    assert any(node.native_locator is not None for node in document.nodes.values())
    assert all(
        node.metadata.get("xml.native_source") is True
        for node in document.nodes.values()
    )


def test_remote_feed_reader_refuses_same_feed_without_remote_origin() -> None:
    source = RSS_FIXTURE.read_bytes()

    with pytest.raises(ValueError, match="url"):
        read_remote_feed_snapshot_ir(
            BytesIO(source),
            stream_info=_rss_info(None),
        )


def test_remote_feed_origin_changes_authority_to_derived_not_native() -> None:
    source = RSS_FIXTURE.read_bytes()

    document = read_remote_feed_snapshot_ir(
        BytesIO(source),
        stream_info=_rss_info("https://example.com/feed.rss"),
    )

    assert document.source is not None
    assert document.source.format == "remote-feed-snapshot"
    assert document.source.uri == "https://example.com/feed.rss"
    assert document.canvases[0].native_locator is None
    assert all(node.native_locator is None for node in document.nodes.values())


@pytest.mark.parametrize(
    "url",
    (
        "",
        "file:///tmp/feed.rss",
        "data:application/rss+xml,<rss/>",
        "ftp://example.com/feed.rss",
        "https:///feed.rss",
        "https://user:secret@example.com/feed.rss",
        "https://example.com:bad/feed.rss",
        "https://example.com:99999/feed.rss",
    ),
)
def test_remote_feed_reader_rejects_invalid_remote_origins(url: str) -> None:
    with pytest.raises(ValueError):
        read_remote_feed_snapshot_ir(
            BytesIO(RSS_FIXTURE.read_bytes()),
            stream_info=_rss_info(url),
        )


@pytest.mark.parametrize(
    "url",
    (
        "http://example.com/feed.rss",
        "https://feeds.example.org/news.xml",
        "https://127.0.0.1/feed.rss",
    ),
)
def test_remote_feed_reader_accepts_arbitrary_valid_http_hosts(url: str) -> None:
    document = read_remote_feed_snapshot_ir(
        BytesIO(RSS_FIXTURE.read_bytes()),
        stream_info=_rss_info(url),
    )
    assert document.source is not None
    assert document.source.uri == url


def test_generic_non_feed_xml_is_rejected_under_candidate_xml_hints() -> None:
    source = b"<?xml version='1.0'?><document><title>Not a feed</title></document>"
    info = StreamInfo(
        url="https://example.com/data.xml",
        mimetype="application/xml",
        extension=".xml",
        filename="data.xml",
        charset="utf-8",
    )

    with pytest.raises(ValueError, match="RssConverter|owned"):
        read_remote_feed_snapshot_ir(BytesIO(source), stream_info=info)


@pytest.mark.parametrize(
    ("source", "extension", "mimetype"),
    (
        (b"<rss><broken>", ".rss", "application/rss+xml"),
        (b"<feed><broken>", ".atom", "application/atom+xml"),
    ),
)
def test_precise_feed_hints_cannot_rescue_invalid_feed_bytes(
    source: bytes,
    extension: str,
    mimetype: str,
) -> None:
    info = StreamInfo(
        url="https://example.com/feed",
        mimetype=mimetype,
        extension=extension,
        filename=f"feed{extension}",
        charset="utf-8",
    )

    with pytest.raises(ValueError, match="valid RSS/Atom"):
        read_remote_feed_snapshot_ir(BytesIO(source), stream_info=info)


def test_valid_atom_with_generic_xml_hints_is_owned_by_feed_shape() -> None:
    info = StreamInfo(
        url="https://example.com/feed.xml",
        mimetype="application/xml",
        extension=".xml",
        filename="feed.xml",
        charset="utf-8",
    )

    document = read_remote_feed_snapshot_ir(
        BytesIO(ATOM_SNAPSHOT),
        stream_info=info,
    )

    assert document.source is not None
    assert document.source.format == "remote-feed-snapshot"
