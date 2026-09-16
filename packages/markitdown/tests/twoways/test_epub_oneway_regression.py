from __future__ import annotations

from io import BytesIO

from markitdown._stream_info import StreamInfo
from markitdown.converters._epub_converter import EpubConverter

from ._epub_fixtures import make_epub


def test_existing_one_way_epub_behavior_is_unchanged() -> None:
    source = make_epub()
    converter = EpubConverter()
    info = StreamInfo(
        extension=".epub",
        mimetype="application/epub+zip",
    )

    assert converter.accepts(BytesIO(source), info)
    result = converter.convert(BytesIO(source), info)

    assert result.title == "Demo Book"
    assert "**Title:** Demo Book" in result.markdown
    assert "**Authors:** Author One" in result.markdown
    assert "**Language:** en" in result.markdown
    assert "**Identifier:** urn:uuid:book-1" in result.markdown
    assert "Hello" in result.markdown
    assert "world" in result.markdown


def test_existing_one_way_epub_extension_and_mimetype_probe_remain_unchanged() -> None:
    converter = EpubConverter()

    assert converter.accepts(
        BytesIO(b""),
        StreamInfo(extension=".EPUB", mimetype=None),
    )
    assert converter.accepts(
        BytesIO(make_epub()),
        StreamInfo(extension=None, mimetype="application/x-epub+zip"),
    )
