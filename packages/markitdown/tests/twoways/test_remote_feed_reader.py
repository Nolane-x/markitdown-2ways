from __future__ import annotations

from hashlib import sha256
from io import BytesIO
from pathlib import Path

from markitdown import MarkItDown
from markitdown._stream_info import StreamInfo
from markitdown.twoways import (
    CapabilityState,
    build_capability_report,
    capabilities_for_node,
)
from markitdown.twoways.ir.nodes import TextPayload
from markitdown.twoways.ir.serialization import (
    canonical_json_bytes,
    canonical_json_digest,
    decode_document,
)
from markitdown.twoways.readers.remote import read_remote_feed_snapshot_ir


RSS_FIXTURE = Path(__file__).parents[1] / "test_files" / "test_rss.xml"
RSS_URL = "https://blogs.microsoft.com/feed/"
RSS_CONVERTER_BLOB = "6b7b1201062208f7e24695b388bc4c3baabbb229"

ATOM_SNAPSHOT = b"""<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>Example Atom Feed</title>
  <subtitle>A small synthetic feed.</subtitle>
  <entry>
    <title>First entry</title>
    <updated>2026-09-18T00:00:00Z</updated>
    <summary type="text">Atom summary.</summary>
  </entry>
</feed>
"""
ATOM_URL = "https://example.com/feed.atom"


def _rss_info(**updates: object) -> StreamInfo:
    values = {
        "url": RSS_URL,
        "mimetype": "application/rss+xml",
        "extension": ".xml",
        "filename": "test_rss.xml",
        "charset": "utf-8",
    }
    values.update(updates)
    return StreamInfo(**values)


def _atom_info(**updates: object) -> StreamInfo:
    values = {
        "url": ATOM_URL,
        "mimetype": "application/atom+xml",
        "extension": ".atom",
        "filename": "feed.atom",
        "charset": "utf-8",
    }
    values.update(updates)
    return StreamInfo(**values)


def _root(document):
    assert len(document.root_node_ids) == 1
    return document.nodes[document.root_node_ids[0]]


def test_rss_reader_matches_public_one_way_markdown_exactly() -> None:
    source = RSS_FIXTURE.read_bytes()
    info = _rss_info()

    document = read_remote_feed_snapshot_ir(BytesIO(source), stream_info=info)
    public = MarkItDown().convert_stream(BytesIO(source), stream_info=info)

    assert document.source is not None
    assert document.source.format == "remote-feed-snapshot"
    assert document.source.filename == "test_rss.xml"
    assert document.source.mimetype == "application/rss+xml"
    assert document.source.uri == RSS_URL
    assert document.source.sha256 == sha256(source).hexdigest()
    assert document.source.size_bytes == len(source)
    assert document.source.preserved_source_ref is None
    assert document.metadata.title == public.title

    node = _root(document)
    assert node.kind == "text"
    assert node.semantic_role == "derived_document"
    assert isinstance(node.payload, TextPayload)
    assert node.payload.text == public.markdown
    assert node.native_locator is None
    assert document.canvases[0].kind == "remote-derived"
    assert document.canvases[0].native_locator is None


def test_atom_reader_matches_public_one_way_markdown_exactly() -> None:
    info = _atom_info()

    document = read_remote_feed_snapshot_ir(
        BytesIO(ATOM_SNAPSHOT),
        stream_info=info,
    )
    public = MarkItDown().convert_stream(BytesIO(ATOM_SNAPSHOT), stream_info=info)

    assert document.source is not None
    assert document.source.format == "remote-feed-snapshot"
    assert document.source.uri == ATOM_URL
    assert document.metadata.title == public.title == "Example Atom Feed"

    node = _root(document)
    assert isinstance(node.payload, TextPayload)
    assert node.payload.text == public.markdown
    assert "First entry" in node.payload.text
    assert "Atom summary." in node.payload.text


def test_feed_reader_records_remote_snapshot_evidence() -> None:
    source = RSS_FIXTURE.read_bytes()
    document = read_remote_feed_snapshot_ir(
        BytesIO(source),
        stream_info=_rss_info(),
    )
    node = _root(document)
    assert isinstance(node.payload, TextPayload)
    markdown_bytes = node.payload.text.encode("utf-8")

    evidence = document.metadata.custom["twoways.remote_snapshot.v1"]
    assert evidence["kind"] == "feed"
    assert evidence["uri"] == RSS_URL
    assert evidence["source_sha256"] == sha256(source).hexdigest()
    assert evidence["source_size_bytes"] == len(source)
    assert evidence["converter"] == "RssConverter"
    assert evidence["converter_blob_sha"] == RSS_CONVERTER_BLOB
    assert evidence["markdown_sha256"] == sha256(markdown_bytes).hexdigest()
    assert evidence["markdown_utf8_size_bytes"] == len(markdown_bytes)
    assert evidence["network_performed_by_twoways"] is False


def test_feed_root_is_derived_and_has_no_native_write_authority() -> None:
    document = read_remote_feed_snapshot_ir(
        BytesIO(ATOM_SNAPSHOT),
        stream_info=_atom_info(),
    )
    node = _root(document)

    decision = capabilities_for_node(node).for_operation("replace_text")
    assert decision.state is CapabilityState.DERIVED
    assert decision.reason_code == "remote.source.not_native_writable"
    assert decision.constraints == {
        "identity_markdown": False,
        "remote_writeback": False,
        "native_owner": False,
        "materialization": "explicit-local-only",
    }

    report = build_capability_report(document)
    assert report.total_nodes == 1
    assert report.derived_nodes == 1
    assert report.writable_nodes == 0
    assert dict(report.writable_by_operation) == {}

    assert len(document.diagnostics) == 1
    assert document.diagnostics[0].code == "remote.source.not_native_writable"
    assert document.diagnostics[0].severity == "info"


def test_feed_provenance_is_descriptive_not_native() -> None:
    document = read_remote_feed_snapshot_ir(
        BytesIO(ATOM_SNAPSHOT),
        stream_info=_atom_info(),
    )
    node = _root(document)
    provenance = node.provenance[0]

    assert provenance.source_format == "remote-feed-snapshot"
    assert provenance.extraction_method == "RssConverter"
    assert provenance.metadata["uri"] == ATOM_URL
    assert provenance.metadata["source_sha256"] == document.source.sha256
    assert provenance.metadata["remote_writeback"] is False
    assert node.native_locator is None


def test_feed_repeated_reads_and_canonical_round_trip_are_deterministic() -> None:
    info = _atom_info()
    first = read_remote_feed_snapshot_ir(
        BytesIO(ATOM_SNAPSHOT),
        stream_info=info,
    )
    second = read_remote_feed_snapshot_ir(
        BytesIO(ATOM_SNAPSHOT),
        stream_info=info,
    )

    assert canonical_json_digest(first) == canonical_json_digest(second)
    encoded = canonical_json_bytes(first)
    decoded = decode_document(encoded)
    assert canonical_json_bytes(decoded) == encoded
    assert decoded.schema_version == "0.1.0"
    assert build_capability_report(decoded) == build_capability_report(first)
