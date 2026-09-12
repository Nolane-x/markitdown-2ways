from io import BytesIO

from markitdown._stream_info import StreamInfo
from markitdown.converters._plain_text_converter import PlainTextConverter


def test_existing_one_way_json_converter_output_is_unchanged() -> None:
    source = b'{"name":"Ada", "n":1e2}\n'
    converter = PlainTextConverter()
    stream_info = StreamInfo(
        extension=".json",
        mimetype="application/json",
        charset="utf-8",
    )

    assert converter.accepts(BytesIO(source), stream_info)
    result = converter.convert(BytesIO(source), stream_info)

    assert result.markdown == source.decode("utf-8")
