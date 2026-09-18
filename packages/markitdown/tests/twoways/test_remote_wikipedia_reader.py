from __future__ import annotations

from hashlib import sha256
from io import BytesIO
from pathlib import Path

import pytest

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
    validate_document,
)
from markitdown.twoways.readers.remote import (
    RemoteDerivedLimits,
    read_wikipedia_snapshot_ir,
)


FIXTURE = Path(__file__).parents[1] / "test_files" / "test_wikipedia.html"
WIKIPEDIA_URL = "https://en.wikipedia.org/wiki/Microsoft"
CONVERTER_BLOB = "ba0c751092fa9e37fcf982f1fae9c4dcd774e049"


def _info(**updates: object) -> StreamInfo:
    values = {
        "url": WIKIPEDIA_URL,
        "mimetype": "text/html",
        "extension": ".html",
        "filename": "Microsoft.html",
        "charset": "utf-8",
    }
    values.update(updates)
    return StreamInfo(**values)


def _snapshot() -> bytes:
    return FIXTURE.read_bytes()


def _root(document):
    assert len(document.root_node_ids) == 1
    return document.nodes[document.root_node_ids[0]]


def test_remote_limits_defaults_are_frozen() -> None:
    limits = RemoteDerivedLimits()

    assert limits.max_source_bytes == 32 * 1024 * 1024
    assert limits.max_markdown_utf8_bytes == 16 * 1024 * 1024


@pytest.mark.parametrize(
    "kwargs",
    (
        {"max_source_bytes": 0},
        {"max_source_bytes": -1},
        {"max_source_bytes": True},
        {"max_source_bytes": 1.5},
        {"max_markdown_utf8_bytes": 0},
        {"max_markdown_utf8_bytes": -1},
        {"max_markdown_utf8_bytes": False},
        {"max_markdown_utf8_bytes": "1024"},
    ),
)
def test_remote_limits_require_positive_non_bool_integers(
    kwargs: dict[str, object],
) -> None:
    with pytest.raises((TypeError, ValueError)):
        RemoteDerivedLimits(**kwargs)


def test_reader_matches_public_wikipedia_one_way_markdown_exactly() -> None:
    source = _snapshot()
    info = _info()

    document = read_wikipedia_snapshot_ir(BytesIO(source), stream_info=info)
    public = MarkItDown().convert_stream(BytesIO(source), stream_info=info)

    validate_document(document)
    assert document.source is not None
    assert document.source.format == "remote-wikipedia-snapshot"
    assert document.source.filename == "Microsoft.html"
    assert document.source.mimetype == "text/html"
    assert document.source.uri == WIKIPEDIA_URL
    assert document.source.sha256 == sha256(source).hexdigest()
    assert document.source.size_bytes == len(source)
    assert document.source.preserved_source_ref is None
    assert document.metadata.title == public.title

    assert len(document.canvases) == 1
    canvas = document.canvases[0]
    assert canvas.kind == "remote-derived"
    assert canvas.native_locator is None

    node = _root(document)
    assert node.kind == "text"
    assert node.semantic_role == "derived_document"
    assert isinstance(node.payload, TextPayload)
    assert node.payload.text == public.markdown
    assert node.native_locator is None


def test_reader_records_versioned_remote_snapshot_evidence() -> None:
    source = _snapshot()
    info = _info()
    document = read_wikipedia_snapshot_ir(BytesIO(source), stream_info=info)
    node = _root(document)
    assert isinstance(node.payload, TextPayload)
    markdown_bytes = node.payload.text.encode("utf-8")

    evidence = document.metadata.custom["twoways.remote_snapshot.v1"]
    assert evidence["kind"] == "wikipedia"
    assert evidence["uri"] == WIKIPEDIA_URL
    assert evidence["source_sha256"] == sha256(source).hexdigest()
    assert evidence["source_size_bytes"] == len(source)
    assert evidence["converter"] == "WikipediaConverter"
    assert evidence["converter_blob_sha"] == CONVERTER_BLOB
    assert evidence["markdown_sha256"] == sha256(markdown_bytes).hexdigest()
    assert evidence["markdown_utf8_size_bytes"] == len(markdown_bytes)
    assert evidence["network_performed_by_twoways"] is False


def test_root_is_explicitly_derived_and_has_no_write_authority() -> None:
    document = read_wikipedia_snapshot_ir(
        BytesIO(_snapshot()),
        stream_info=_info(),
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
    assert report.writable_nodes == 0
    assert report.read_only_nodes == 0
    assert report.derived_nodes == 1
    assert dict(report.writable_by_operation) == {}
    assert report.reason_counts["remote.source.not_native_writable"] == 1

    assert len(document.diagnostics) == 1
    diagnostic = document.diagnostics[0]
    assert diagnostic.code == "remote.source.not_native_writable"
    assert diagnostic.severity == "info"


def test_provenance_is_descriptive_not_a_native_locator() -> None:
    document = read_wikipedia_snapshot_ir(
        BytesIO(_snapshot()),
        stream_info=_info(),
    )
    node = _root(document)

    assert node.native_locator is None
    assert len(node.provenance) == 1
    provenance = node.provenance[0]
    assert provenance.source_format == "remote-wikipedia-snapshot"
    assert provenance.extraction_method == "WikipediaConverter"
    assert provenance.metadata["uri"] == WIKIPEDIA_URL
    assert provenance.metadata["source_sha256"] == document.source.sha256
    assert provenance.metadata["remote_writeback"] is False


def test_repeated_reads_and_canonical_round_trip_are_deterministic() -> None:
    source = _snapshot()
    info = _info()

    first = read_wikipedia_snapshot_ir(BytesIO(source), stream_info=info)
    second = read_wikipedia_snapshot_ir(BytesIO(source), stream_info=info)

    assert canonical_json_digest(first) == canonical_json_digest(second)
    encoded = canonical_json_bytes(first)
    decoded = decode_document(encoded)
    assert canonical_json_bytes(decoded) == encoded
    assert decoded.schema_version == "0.1.0"
    assert build_capability_report(decoded) == build_capability_report(first)
