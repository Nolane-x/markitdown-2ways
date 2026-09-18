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
from markitdown.twoways.formats.xml import read_xml_ir
from markitdown.twoways.ir.nodes import TextPayload
from markitdown.twoways.ir.serialization import (
    canonical_json_bytes,
    canonical_json_digest,
    decode_document,
)
from markitdown.twoways.readers.remote import read_rss_atom_snapshot_ir


FIXTURE = Path(__file__).parents[1] / "test_files" / "test_rss.xml"
FEED_URL = "https://feeds.example.com/news.xml"
CONVERTER_BLOB = "6b7b1201062208f7e24695b388bc4c3baabbb229"


def _snapshot() -> bytes:
    return FIXTURE.read_bytes()


def _info(**updates: object) -> StreamInfo:
    values = {
        "url": FEED_URL,
        "mimetype": "application/rss+xml",
        "extension": ".xml",
        "filename": "news.xml",
        "charset": "utf-8",
    }
    values.update(updates)
    return StreamInfo(**values)


def _root(document):
    assert len(document.root_node_ids) == 1
    return document.nodes[document.root_node_ids[0]]


def test_remote_rss_reader_matches_public_one_way_markdown_exactly() -> None:
    source = _snapshot()
    info = _info()

    document = read_rss_atom_snapshot_ir(BytesIO(source), stream_info=info)
    public = MarkItDown().convert_stream(BytesIO(source), stream_info=info)

    assert document.source is not None
    assert document.source.format == "remote-rss-atom-snapshot"
    assert document.source.filename == "news.xml"
    assert document.source.mimetype == "application/rss+xml"
    assert document.source.uri == FEED_URL
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
    assert document.canvases[0].native_locator is None


def test_remote_rss_reader_records_versioned_snapshot_evidence() -> None:
    source = _snapshot()
    document = read_rss_atom_snapshot_ir(BytesIO(source), stream_info=_info())
    node = _root(document)
    assert isinstance(node.payload, TextPayload)
    markdown_bytes = node.payload.text.encode("utf-8")

    evidence = document.metadata.custom["twoways.remote_snapshot.v1"]
    assert evidence["kind"] == "rss-atom"
    assert evidence["uri"] == FEED_URL
    assert evidence["source_sha256"] == sha256(source).hexdigest()
    assert evidence["source_size_bytes"] == len(source)
    assert evidence["converter"] == "RssConverter"
    assert evidence["converter_blob_sha"] == CONVERTER_BLOB
    assert evidence["markdown_sha256"] == sha256(markdown_bytes).hexdigest()
    assert evidence["markdown_utf8_size_bytes"] == len(markdown_bytes)
    assert evidence["network_performed_by_twoways"] is False


def test_remote_rss_root_is_explicitly_derived() -> None:
    document = read_rss_atom_snapshot_ir(BytesIO(_snapshot()), stream_info=_info())
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


def test_same_rss_bytes_remain_native_xml_when_read_locally() -> None:
    source = _snapshot()
    local = read_xml_ir(
        BytesIO(source),
        filename="news.xml",
        mimetype="application/xml",
    )

    assert local.source is not None
    assert local.source.format == "xml"
    assert local.source.uri is None
    assert local.canvases[0].native_locator is not None

    writable = []
    for node in local.nodes.values():
        if node.native_locator is None:
            continue
        for operation in ("replace_xml_text", "replace_xml_attribute"):
            if capabilities_for_node(node).for_operation(operation).state is CapabilityState.WRITABLE:
                writable.append((node.node_id, operation))
    assert writable, "same RSS bytes must retain H4 native lexical write authority"


def test_remote_and_local_modes_have_distinct_authority_for_same_bytes() -> None:
    source = _snapshot()
    remote = read_rss_atom_snapshot_ir(BytesIO(source), stream_info=_info())
    local = read_xml_ir(
        BytesIO(source),
        filename="news.xml",
        mimetype="application/xml",
    )

    assert remote.source is not None
    assert local.source is not None
    assert remote.source.sha256 == local.source.sha256 == sha256(source).hexdigest()
    assert remote.source.format == "remote-rss-atom-snapshot"
    assert local.source.format == "xml"

    remote_root = _root(remote)
    assert remote_root.native_locator is None
    assert (
        capabilities_for_node(remote_root).for_operation("replace_text").state
        is CapabilityState.DERIVED
    )
    assert any(node.native_locator is not None for node in local.nodes.values())


def test_remote_rss_reads_and_canonical_round_trip_are_deterministic() -> None:
    source = _snapshot()
    info = _info()

    first = read_rss_atom_snapshot_ir(BytesIO(source), stream_info=info)
    second = read_rss_atom_snapshot_ir(BytesIO(source), stream_info=info)

    assert canonical_json_digest(first) == canonical_json_digest(second)
    encoded = canonical_json_bytes(first)
    decoded = decode_document(encoded)
    assert canonical_json_bytes(decoded) == encoded
    assert decoded.schema_version == "0.1.0"
    assert build_capability_report(decoded) == build_capability_report(first)
