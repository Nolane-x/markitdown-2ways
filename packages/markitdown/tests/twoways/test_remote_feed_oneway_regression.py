from __future__ import annotations

from io import BytesIO

from markitdown import MarkItDown
from markitdown.converters._rss_converter import RssConverter

from .test_remote_feed_reader import (
    ATOM_SNAPSHOT,
    RSS_FIXTURE,
    _atom_info,
    _rss_info,
)

def _normalize_trailing_layout_whitespace(markdown: str) -> str:
    return "\n".join(
        line.rstrip(" \t\u00a0\u202f") for line in markdown.splitlines()
    )


def test_existing_rss_converter_ownership_and_semantics_remain_intact() -> None:
    source = RSS_FIXTURE.read_bytes()
    info = _rss_info()
    converter = RssConverter()

    assert converter.accepts(BytesIO(source), info) is True

    direct = converter.convert(BytesIO(source), info)
    public = MarkItDown().convert_stream(BytesIO(source), stream_info=info)

    assert direct.title == public.title == "The Official Microsoft Blog"
    assert _normalize_trailing_layout_whitespace(direct.markdown) == (
        _normalize_trailing_layout_whitespace(public.markdown)
    )
    assert "Ignite 2024" in direct.markdown


def test_existing_atom_converter_ownership_and_semantics_remain_intact() -> None:
    info = _atom_info()
    converter = RssConverter()

    assert converter.accepts(BytesIO(ATOM_SNAPSHOT), info) is True

    direct = converter.convert(BytesIO(ATOM_SNAPSHOT), info)
    public = MarkItDown().convert_stream(
        BytesIO(ATOM_SNAPSHOT),
        stream_info=info,
    )

    assert direct.title == public.title == "Example Atom Feed"
    assert direct.markdown == public.markdown
    assert "First entry" in direct.markdown
    assert "Atom summary." in direct.markdown
