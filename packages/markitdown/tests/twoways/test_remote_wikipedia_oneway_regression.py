from __future__ import annotations

from io import BytesIO
from pathlib import Path

from markitdown import MarkItDown
from markitdown._stream_info import StreamInfo
from markitdown.converters._wikipedia_converter import WikipediaConverter


FIXTURE = Path(__file__).parents[1] / "test_files" / "test_wikipedia.html"
INFO = StreamInfo(
    url="https://en.wikipedia.org/wiki/Microsoft",
    mimetype="text/html",
    extension=".html",
    filename="Microsoft.html",
    charset="utf-8",
)


def test_existing_wikipedia_converter_ownership_and_semantics_remain_intact() -> None:
    source = FIXTURE.read_bytes()
    converter = WikipediaConverter()

    assert converter.accepts(BytesIO(source), INFO) is True
    direct = converter.convert(BytesIO(source), INFO)
    public = MarkItDown().convert_stream(BytesIO(source), stream_info=INFO)

    assert direct.title == "Microsoft"
    assert public.title == "Microsoft"
    assert "# Microsoft" in direct.markdown
    assert "# Microsoft" in public.markdown
