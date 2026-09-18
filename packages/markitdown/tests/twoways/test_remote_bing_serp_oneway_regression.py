from __future__ import annotations

from io import BytesIO

from markitdown import MarkItDown
from markitdown._stream_info import StreamInfo
from markitdown.converters._bing_serp_converter import BingSerpConverter

from .test_remote_bing_serp_reader import BING_URL, SNAPSHOT


INFO = StreamInfo(
    url=BING_URL,
    mimetype="text/html",
    extension=".html",
    filename="bing.html",
    charset="utf-8",
)


def test_existing_bing_converter_ownership_and_semantics_remain_intact() -> None:
    converter = BingSerpConverter()

    assert converter.accepts(BytesIO(SNAPSHOT), INFO) is True

    direct = converter.convert(BytesIO(SNAPSHOT), INFO)
    public = MarkItDown().convert_stream(BytesIO(SNAPSHOT), stream_info=INFO)

    assert direct.title == "markitdown - Search"
    assert public.title == "markitdown - Search"
    assert "A Bing search for 'markitdown'" in direct.markdown
    assert "First result" in direct.markdown
    assert "Second result" in direct.markdown
    assert "A Bing search for 'markitdown'" in public.markdown
    assert "First result" in public.markdown
    assert "Second result" in public.markdown
