from __future__ import annotations

from io import BytesIO

from markitdown._stream_info import StreamInfo
from markitdown.converters._html_converter import HtmlConverter


def test_existing_one_way_html_behavior_is_unchanged() -> None:
    source = b"<html><head><title>T</title></head><body><p>Hello</p></body></html>"
    converter = HtmlConverter()
    stream_info = StreamInfo(
        extension=".html",
        mimetype="text/html",
        charset="utf-8",
    )

    assert converter.accepts(BytesIO(source), stream_info)
    result = converter.convert(BytesIO(source), stream_info)

    assert result.markdown == "Hello"
    assert result.title == "T"


def test_existing_one_way_html_extension_and_xhtml_acceptance_remain_unchanged() -> (
    None
):
    converter = HtmlConverter()

    assert converter.accepts(
        BytesIO(b""),
        StreamInfo(extension=".HTM", mimetype=None, charset="utf-8"),
    )
    assert converter.accepts(
        BytesIO(b""),
        StreamInfo(
            extension=None,
            mimetype="application/xhtml+xml",
            charset="utf-8",
        ),
    )
