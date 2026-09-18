from __future__ import annotations

import importlib


def test_h21_youtube_symbols_are_public_without_writer_exports() -> None:
    youtube = importlib.import_module("markitdown.twoways.readers.youtube")
    readers = importlib.import_module("markitdown.twoways.readers")
    tw = importlib.import_module("markitdown.twoways")

    for module in (youtube, readers, tw):
        assert hasattr(module, "YouTubeDerivedLimits")
        assert hasattr(module, "YouTubeTranscriptSnapshot")
        assert hasattr(module, "read_youtube_snapshot_ir")

    assert "YouTubeDerivedLimits" in youtube.__all__
    assert "YouTubeTranscriptSnapshot" in youtube.__all__
    assert "read_youtube_snapshot_ir" in youtube.__all__

    for module in (readers, tw):
        assert "YouTubeDerivedLimits" in module.__all__
        assert "YouTubeTranscriptSnapshot" in module.__all__
        assert "read_youtube_snapshot_ir" in module.__all__

    for forbidden in (
        "patch_youtube",
        "write_youtube",
        "write_youtube_snapshot",
        "YouTubeWriter",
        "YouTubeTranscriptWriter",
    ):
        assert not hasattr(youtube, forbidden)
        assert not hasattr(readers, forbidden)
        assert not hasattr(tw, forbidden)
