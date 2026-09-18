from __future__ import annotations

from hashlib import sha256
from io import BytesIO

import pytest

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
from markitdown.twoways.readers.youtube import read_youtube_snapshot_ir


VIDEO_ID = "abc123DEF45"
WATCH_URL = f"https://www.youtube.com/watch?v={VIDEO_ID}"
HTML_SNAPSHOT = b"""<!doctype html>
<html>
<head>
  <title>Demo Video</title>
  <meta itemprop="interactionCount" content="123">
  <meta name="keywords" content="alpha,beta">
  <meta itemprop="duration" content="PT1M2S">
  <meta property="og:description" content="Fallback description">
</head>
<body>
<script>var ytInitialData = {"attributedDescriptionBodyText":{"content":"Primary description"}};</script>
</body>
</html>
"""


def _info(url: str = WATCH_URL, **updates: object) -> StreamInfo:
    values = {
        "url": url,
        "mimetype": "text/html",
        "extension": ".html",
        "filename": "video.html",
        "charset": "utf-8",
    }
    values.update(updates)
    return StreamInfo(**values)


def _root(document):
    assert len(document.root_node_ids) == 1
    return document.nodes[document.root_node_ids[0]]


@pytest.mark.parametrize(
    "url",
    (
        WATCH_URL,
        f"https://youtu.be/{VIDEO_ID}",
        f"https://www.youtube.com/shorts/{VIDEO_ID}",
        f"https://www.youtube.com/embed/{VIDEO_ID}",
        f"https://m.youtube.com/watch?v={VIDEO_ID}",
    ),
)
def test_youtube_reader_accepts_current_one_way_url_shapes(url: str) -> None:
    document = read_youtube_snapshot_ir(
        BytesIO(HTML_SNAPSHOT),
        stream_info=_info(url),
    )

    assert document.source is not None
    evidence = document.metadata.custom["twoways.youtube_snapshot.v1"]
    assert evidence["video_id"] == VIDEO_ID
    assert evidence["uri"] == url


def test_youtube_html_only_reader_binds_source_and_derived_semantics() -> None:
    document = read_youtube_snapshot_ir(
        BytesIO(HTML_SNAPSHOT),
        stream_info=_info(),
    )

    assert document.source is not None
    assert document.source.format == "remote-youtube-snapshot"
    assert document.source.filename == "video.html"
    assert document.source.mimetype == "text/html"
    assert document.source.uri == WATCH_URL
    assert document.source.sha256 == sha256(HTML_SNAPSHOT).hexdigest()
    assert document.source.size_bytes == len(HTML_SNAPSHOT)
    assert document.source.preserved_source_ref is None
    assert document.metadata.title == "Demo Video"

    node = _root(document)
    assert node.kind == "text"
    assert node.semantic_role == "derived_document"
    assert isinstance(node.payload, TextPayload)
    assert "# YouTube" in node.payload.text
    assert "## Demo Video" in node.payload.text
    assert "- **Views:** 123" in node.payload.text
    assert "- **Keywords:** alpha,beta" in node.payload.text
    assert "- **Runtime:** PT1M2S" in node.payload.text
    assert "### Description" in node.payload.text
    assert "Primary description" in node.payload.text
    assert "### Transcript" not in node.payload.text
    assert node.native_locator is None
    assert document.canvases[0].kind == "remote-derived"
    assert document.canvases[0].native_locator is None


def test_youtube_html_only_evidence_does_not_claim_transcript_unavailability() -> None:
    document = read_youtube_snapshot_ir(
        BytesIO(HTML_SNAPSHOT),
        stream_info=_info(),
    )
    node = _root(document)
    assert isinstance(node.payload, TextPayload)
    evidence = document.metadata.custom["twoways.youtube_snapshot.v1"]

    assert evidence["html_sha256"] == sha256(HTML_SNAPSHOT).hexdigest()
    assert evidence["html_size_bytes"] == len(HTML_SNAPSHOT)
    assert evidence["video_id"] == VIDEO_ID
    assert evidence["converter"] == "YouTubeConverter"
    assert evidence["converter_blob_sha"] == "c3779743c6fe55c4716d8816b9a5a52b929c5e32"
    assert evidence["transcript_provided"] is False
    assert evidence["network_performed_by_twoways"] is False
    assert "transcript_available" not in evidence


def test_youtube_root_is_derived_and_not_native_writable() -> None:
    document = read_youtube_snapshot_ir(
        BytesIO(HTML_SNAPSHOT),
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
    assert report.derived_nodes == 1
    assert report.writable_nodes == 0
    assert dict(report.writable_by_operation) == {}

    assert len(document.diagnostics) == 1
    assert document.diagnostics[0].code == "remote.source.not_native_writable"


def test_youtube_html_only_repeated_reads_and_canonical_round_trip_are_deterministic() -> None:
    first = read_youtube_snapshot_ir(
        BytesIO(HTML_SNAPSHOT),
        stream_info=_info(),
    )
    second = read_youtube_snapshot_ir(
        BytesIO(HTML_SNAPSHOT),
        stream_info=_info(),
    )

    assert canonical_json_digest(first) == canonical_json_digest(second)
    encoded = canonical_json_bytes(first)
    decoded = decode_document(encoded)
    assert canonical_json_bytes(decoded) == encoded
    assert decoded.schema_version == "0.1.0"
    assert build_capability_report(decoded) == build_capability_report(first)
