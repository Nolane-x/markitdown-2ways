from __future__ import annotations

from hashlib import sha256
from io import BytesIO

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
from markitdown.twoways.readers.remote import read_bing_serp_snapshot_ir


BING_URL = "https://www.bing.com/search?q=markitdown"
CONVERTER_BLOB = "fd00a70ab76ff01fcdc2e3bfb47aaf20708408c8"
SNAPSHOT = b"""<!doctype html>
<html>
<head><title>markitdown - Search</title></head>
<body>
<ol id="b_results">
  <li class="b_algo">
    <h2><a href="https://example.com/one">First result</a></h2>
    <p>First description.</p>
  </li>
  <li class="b_algo">
    <h2><a href="https://example.org/two">Second result</a></h2>
    <p>Second description.</p>
  </li>
</ol>
</body>
</html>
"""


def _info(**updates: object) -> StreamInfo:
    values = {
        "url": BING_URL,
        "mimetype": "text/html",
        "extension": ".html",
        "filename": "bing.html",
        "charset": "utf-8",
    }
    values.update(updates)
    return StreamInfo(**values)


def _root(document):
    assert len(document.root_node_ids) == 1
    return document.nodes[document.root_node_ids[0]]


def test_bing_reader_matches_public_one_way_markdown_exactly() -> None:
    info = _info()
    document = read_bing_serp_snapshot_ir(BytesIO(SNAPSHOT), stream_info=info)
    public = MarkItDown().convert_stream(BytesIO(SNAPSHOT), stream_info=info)

    assert document.source is not None
    assert document.source.format == "remote-bing-serp-snapshot"
    assert document.source.filename == "bing.html"
    assert document.source.mimetype == "text/html"
    assert document.source.uri == BING_URL
    assert document.source.sha256 == sha256(SNAPSHOT).hexdigest()
    assert document.source.size_bytes == len(SNAPSHOT)
    assert document.source.preserved_source_ref is None
    assert document.metadata.title == public.title

    node = _root(document)
    assert node.kind == "text"
    assert node.semantic_role == "derived_document"
    assert isinstance(node.payload, TextPayload)
    assert node.payload.text == public.markdown
    assert node.native_locator is None
    assert document.canvases[0].native_locator is None


def test_bing_reader_records_remote_snapshot_evidence() -> None:
    document = read_bing_serp_snapshot_ir(BytesIO(SNAPSHOT), stream_info=_info())
    node = _root(document)
    assert isinstance(node.payload, TextPayload)
    markdown_bytes = node.payload.text.encode("utf-8")

    evidence = document.metadata.custom["twoways.remote_snapshot.v1"]
    assert evidence["kind"] == "bing-serp"
    assert evidence["uri"] == BING_URL
    assert evidence["source_sha256"] == sha256(SNAPSHOT).hexdigest()
    assert evidence["source_size_bytes"] == len(SNAPSHOT)
    assert evidence["converter"] == "BingSerpConverter"
    assert evidence["converter_blob_sha"] == CONVERTER_BLOB
    assert evidence["markdown_sha256"] == sha256(markdown_bytes).hexdigest()
    assert evidence["markdown_utf8_size_bytes"] == len(markdown_bytes)
    assert evidence["network_performed_by_twoways"] is False


def test_bing_root_is_derived_and_not_native_writable() -> None:
    document = read_bing_serp_snapshot_ir(BytesIO(SNAPSHOT), stream_info=_info())
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


def test_bing_provenance_has_no_native_locator_or_writeback_claim() -> None:
    document = read_bing_serp_snapshot_ir(BytesIO(SNAPSHOT), stream_info=_info())
    node = _root(document)
    provenance = node.provenance[0]

    assert provenance.source_format == "remote-bing-serp-snapshot"
    assert provenance.extraction_method == "BingSerpConverter"
    assert provenance.metadata["uri"] == BING_URL
    assert provenance.metadata["source_sha256"] == document.source.sha256
    assert provenance.metadata["remote_writeback"] is False
    assert node.native_locator is None


def test_bing_repeated_reads_and_canonical_round_trip_are_deterministic() -> None:
    info = _info()
    first = read_bing_serp_snapshot_ir(BytesIO(SNAPSHOT), stream_info=info)
    second = read_bing_serp_snapshot_ir(BytesIO(SNAPSHOT), stream_info=info)

    assert canonical_json_digest(first) == canonical_json_digest(second)
    encoded = canonical_json_bytes(first)
    decoded = decode_document(encoded)
    assert canonical_json_bytes(decoded) == encoded
    assert decoded.schema_version == "0.1.0"
    assert build_capability_report(decoded) == build_capability_report(first)
