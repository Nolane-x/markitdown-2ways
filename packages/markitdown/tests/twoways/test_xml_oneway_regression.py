from __future__ import annotations

from io import BytesIO

from markitdown._stream_info import StreamInfo
from markitdown.converters._plain_text_converter import PlainTextConverter


def test_existing_one_way_xml_text_behavior_is_unchanged() -> None:
    source = b'<?xml version="1.0"?><root id="7">Ada &amp; Grace</root>\n'
    converter = PlainTextConverter()
    stream_info = StreamInfo(
        extension=".xml",
        mimetype="application/xml",
        charset="utf-8",
    )

    assert converter.accepts(BytesIO(source), stream_info)
    result = converter.convert(BytesIO(source), stream_info)

    assert result.markdown == source.decode("utf-8")
