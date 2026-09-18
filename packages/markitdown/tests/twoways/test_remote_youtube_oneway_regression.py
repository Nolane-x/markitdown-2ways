from __future__ import annotations

from hashlib import sha256
from io import BytesIO
import inspect
from pathlib import Path

from markitdown.converters import _youtube_converter as youtube_converter
from markitdown.converters._youtube_converter import YouTubeConverter

from .test_remote_youtube_reader import HTML_SNAPSHOT, VIDEO_ID, _info


EXPECTED_CONVERTER_BLOB = "c3779743c6fe55c4716d8816b9a5a52b929c5e32"


def test_existing_youtube_converter_blob_is_unchanged() -> None:
    path = Path(inspect.getsourcefile(YouTubeConverter) or "")
    assert path.is_file()
    assert sha256(path.read_bytes()).hexdigest() == EXPECTED_CONVERTER_BLOB


def test_existing_youtube_converter_ownership_shapes_remain_intact() -> None:
    converter = YouTubeConverter()
    urls = (
        f"https://www.youtube.com/watch?v={VIDEO_ID}",
        f"https://youtu.be/{VIDEO_ID}",
        f"https://www.youtube.com/shorts/{VIDEO_ID}",
        f"https://www.youtube.com/embed/{VIDEO_ID}",
        f"https://m.youtube.com/watch?v={VIDEO_ID}",
    )
    for url in urls:
        assert converter.accepts(
            BytesIO(HTML_SNAPSHOT),
            _info(url),
        )


def test_existing_youtube_html_only_semantics_remain_intact(monkeypatch) -> None:
    monkeypatch.setattr(
        youtube_converter,
        "IS_YOUTUBE_TRANSCRIPT_CAPABLE",
        False,
    )
    result = YouTubeConverter().convert(
        BytesIO(HTML_SNAPSHOT),
        _info(),
    )
    assert result.title == "Demo Video"
    assert result.markdown.startswith("# YouTube\n\n## Demo Video\n")
    assert "- **Views:** 123" in result.markdown
    assert "- **Keywords:** alpha,beta" in result.markdown
    assert "- **Runtime:** PT1M2S" in result.markdown
    assert "Primary description" in result.markdown
    assert "### Transcript" not in result.markdown
