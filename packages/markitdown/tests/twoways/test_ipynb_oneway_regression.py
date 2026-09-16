from __future__ import annotations

from io import BytesIO

from markitdown._stream_info import StreamInfo
from markitdown.converters._ipynb_converter import IpynbConverter


def _source():
    return (
        b'{"cells":['
        b'{"cell_type":"markdown","metadata":{},"source":["# Heading\\n","hello"]},'
        b'{"cell_type":"code","metadata":{},"outputs":[],"execution_count":null,'
        b'"source":["print(1)"]},'
        b'{"cell_type":"raw","metadata":{},"source":["raw"]}'
        b'],"metadata":{"title":"Notebook Title"},"nbformat":4,"nbformat_minor":5}'
    )


def test_existing_one_way_ipynb_behavior_is_unchanged() -> None:
    source = _source()
    converter = IpynbConverter()
    info = StreamInfo(
        extension=".ipynb",
        mimetype="application/json",
        charset="utf-8",
    )

    assert converter.accepts(BytesIO(source), info)
    result = converter.convert(BytesIO(source), info)

    assert result.markdown == (
        "# Heading\nhello\n\n```python\nprint(1)\n```\n\n```\nraw\n```"
    )
    assert result.title == "Notebook Title"


def test_existing_one_way_ipynb_extension_and_json_probe_remain_unchanged() -> None:
    converter = IpynbConverter()

    assert converter.accepts(
        BytesIO(b""),
        StreamInfo(extension=".IPYNB", mimetype=None, charset="utf-8"),
    )
    assert converter.accepts(
        BytesIO(_source()),
        StreamInfo(extension=None, mimetype="application/json", charset="utf-8"),
    )
