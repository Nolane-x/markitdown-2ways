from __future__ import annotations

from io import BytesIO
from types import SimpleNamespace

from markitdown.converters import _youtube_converter as youtube_converter
from markitdown.converters._youtube_converter import YouTubeConverter
from markitdown.twoways.ir.nodes import TextPayload
from markitdown.twoways.readers.youtube import (
    YouTubeTranscriptSnapshot,
    read_youtube_snapshot_ir,
)

from .test_remote_youtube_reader import HTML_SNAPSHOT, VIDEO_ID, _info, _root


def _markdown(document) -> str:
    node = _root(document)
    assert isinstance(node.payload, TextPayload)
    return node.payload.text


def test_html_only_projection_matches_one_way_with_transcript_disabled(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        youtube_converter,
        "IS_YOUTUBE_TRANSCRIPT_CAPABLE",
        False,
    )
    one_way = YouTubeConverter().convert(
        BytesIO(HTML_SNAPSHOT),
        _info(),
    )
    two_way = read_youtube_snapshot_ir(
        BytesIO(HTML_SNAPSHOT),
        stream_info=_info(),
    )

    assert two_way.metadata.title == one_way.title
    assert _markdown(two_way) == one_way.markdown


class _FakeTranscriptList:
    def __iter__(self):
        yield SimpleNamespace(language_code="vi")


class _FakeTranscriptApi:
    def list(self, video_id: str):
        assert video_id == VIDEO_ID
        return _FakeTranscriptList()

    def fetch(self, video_id: str, *, languages):
        assert video_id == VIDEO_ID
        assert languages == ["en", "vi"]
        return [
            SimpleNamespace(text="Xin chào"),
            SimpleNamespace(text="thế giới"),
        ]


def test_explicit_transcript_matches_one_way_with_offline_fake_api(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        youtube_converter,
        "IS_YOUTUBE_TRANSCRIPT_CAPABLE",
        True,
    )
    monkeypatch.setattr(
        youtube_converter,
        "YouTubeTranscriptApi",
        _FakeTranscriptApi,
        raising=False,
    )

    def _no_sleep(*_args, **_kwargs):
        raise AssertionError("retry sleep must not run in offline differential court")

    monkeypatch.setattr(youtube_converter.time, "sleep", _no_sleep)

    one_way = YouTubeConverter().convert(
        BytesIO(HTML_SNAPSHOT),
        _info(),
    )
    two_way = read_youtube_snapshot_ir(
        BytesIO(HTML_SNAPSHOT),
        stream_info=_info(),
        transcript=YouTubeTranscriptSnapshot(
            video_id=VIDEO_ID,
            language_code="vi",
            parts=("Xin chào", "thế giới"),
            provider="offline-differential-fixture",
        ),
    )

    assert two_way.metadata.title == one_way.title
    assert _markdown(two_way) == one_way.markdown
