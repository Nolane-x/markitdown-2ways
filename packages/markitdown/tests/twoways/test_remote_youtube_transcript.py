from __future__ import annotations

from hashlib import sha256
from io import BytesIO

import pytest

from markitdown.twoways.ir.nodes import TextPayload
from markitdown.twoways.readers.youtube import (
    YouTubeDerivedLimits,
    YouTubeTranscriptSnapshot,
    read_youtube_snapshot_ir,
)

from .test_remote_youtube_reader import HTML_SNAPSHOT, VIDEO_ID, _info, _root


def _transcript(**updates: object) -> YouTubeTranscriptSnapshot:
    values = {
        "video_id": VIDEO_ID,
        "language_code": "en",
        "parts": ("Hello", "from", "the transcript."),
        "provider": "offline-fixture",
    }
    values.update(updates)
    return YouTubeTranscriptSnapshot(**values)


def test_explicit_transcript_is_joined_and_bound_independently() -> None:
    transcript = _transcript()
    document = read_youtube_snapshot_ir(
        BytesIO(HTML_SNAPSHOT),
        stream_info=_info(),
        transcript=transcript,
    )
    node = _root(document)
    assert isinstance(node.payload, TextPayload)

    transcript_text = "Hello from the transcript."
    transcript_bytes = transcript_text.encode("utf-8")
    evidence = document.metadata.custom["twoways.youtube_snapshot.v1"]

    assert node.payload.text.endswith("\n### Transcript\nHello from the transcript.\n")
    assert evidence["transcript_provided"] is True
    assert evidence["transcript_video_id"] == VIDEO_ID
    assert evidence["transcript_language_code"] == "en"
    assert evidence["transcript_provider"] == "offline-fixture"
    assert evidence["transcript_part_count"] == 3
    assert evidence["transcript_sha256"] == sha256(transcript_bytes).hexdigest()
    assert evidence["transcript_utf8_size_bytes"] == len(transcript_bytes)
    assert evidence["network_performed_by_twoways"] is False


def test_transcript_video_id_must_match_page_authority() -> None:
    with pytest.raises(ValueError, match="video ID"):
        read_youtube_snapshot_ir(
            BytesIO(HTML_SNAPSHOT),
            stream_info=_info(),
            transcript=_transcript(video_id="different-video"),
        )


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("video_id", ""),
        ("video_id", "   "),
        ("language_code", ""),
        ("language_code", "   "),
        ("provider", ""),
        ("provider", "   "),
    ),
)
def test_transcript_rejects_empty_authority_fields(field: str, value: str) -> None:
    with pytest.raises(ValueError, match="non-empty"):
        _transcript(**{field: value})


def test_transcript_rejects_invalid_parts() -> None:
    with pytest.raises(TypeError, match="tuple"):
        _transcript(parts=["not", "a", "tuple"])

    with pytest.raises(ValueError, match="non-empty"):
        _transcript(parts=())

    with pytest.raises(ValueError, match=r"parts\[1\].*non-empty"):
        _transcript(parts=("valid", "   "))


def test_transcript_limit_accepts_exact_boundary_and_rejects_one_over() -> None:
    transcript = _transcript(parts=("é", "ok"))
    transcript_size = len("é ok".encode("utf-8"))

    exact = read_youtube_snapshot_ir(
        BytesIO(HTML_SNAPSHOT),
        stream_info=_info(),
        transcript=transcript,
        limits=YouTubeDerivedLimits(max_transcript_utf8_bytes=transcript_size),
    )
    assert exact.root_node_ids

    with pytest.raises(ValueError, match="max_transcript_utf8_bytes"):
        read_youtube_snapshot_ir(
            BytesIO(HTML_SNAPSHOT),
            stream_info=_info(),
            transcript=transcript,
            limits=YouTubeDerivedLimits(max_transcript_utf8_bytes=transcript_size - 1),
        )


def test_transcript_changes_document_identity_without_changing_html_authority() -> None:
    without = read_youtube_snapshot_ir(
        BytesIO(HTML_SNAPSHOT),
        stream_info=_info(),
    )
    with_transcript = read_youtube_snapshot_ir(
        BytesIO(HTML_SNAPSHOT),
        stream_info=_info(),
        transcript=_transcript(),
    )

    assert without.source is not None
    assert with_transcript.source is not None
    assert without.source.sha256 == with_transcript.source.sha256
    assert without.source.size_bytes == with_transcript.source.size_bytes
    assert without.document_id != with_transcript.document_id
