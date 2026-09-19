from __future__ import annotations

from hashlib import sha1
from io import BytesIO
import inspect
from pathlib import Path
from types import SimpleNamespace

from markitdown._stream_info import StreamInfo
from markitdown.converters import _xlsx_converter as converter_module
from markitdown.twoways.ir.nodes import TextPayload
from markitdown.twoways.readers import xls_converter as reader_module
from markitdown.twoways.readers.xls_converter import (
    XlsConverterSnapshot,
    XlsSheetMarkdownSnapshot,
    read_xls_converter_snapshot_ir,
)


EXPECTED_CONVERTER_BLOB = "9f794a3b77e34c84b67358c21001ad7a87f3b9c4"
SOURCE = b"offline H28 XLS differential fixture"


def test_existing_xlsx_converter_blob_is_unchanged() -> None:
    path = Path(inspect.getsourcefile(converter_module.XlsConverter) or "")
    assert path.is_file()
    data = path.read_bytes()
    git_blob = sha1(
        b"blob " + str(len(data)).encode("ascii") + b"\0" + data
    ).hexdigest()
    assert git_blob == EXPECTED_CONVERTER_BLOB


def test_h28_matches_full_one_way_xls_assembly_offline(monkeypatch) -> None:
    class _Frame:
        def __init__(self, html: str) -> None:
            self.html = html

        def to_html(self, index: bool = True) -> str:
            assert index is False
            return self.html

    frames = {
        "Summary": _Frame("<summary>"),
        "Data": _Frame("<data>"),
    }
    materialized = {
        "<summary>": "\n| A |\n| - |\n| 1 |\n\n",
        "<data>": "  second sheet  ",
    }

    def _read_excel(file_stream, *, sheet_name, engine):
        assert sheet_name is None
        assert engine == "xlrd"
        assert file_stream.read() == SOURCE
        return frames

    monkeypatch.setattr(
        converter_module,
        "pd",
        SimpleNamespace(read_excel=_read_excel),
    )
    monkeypatch.setattr(converter_module, "_xls_dependency_exc_info", None)

    converter = converter_module.XlsConverter()
    monkeypatch.setattr(
        converter._html_converter,
        "convert_string",
        lambda html_content, **kwargs: SimpleNamespace(
            markdown=materialized[html_content]
        ),
    )

    info = StreamInfo(
        extension=".xls",
        mimetype="application/vnd.ms-excel",
        filename="fixture.xls",
    )
    one_way = converter.convert(BytesIO(SOURCE), info)
    h28 = read_xls_converter_snapshot_ir(
        BytesIO(SOURCE),
        stream_info=info,
        snapshot=XlsConverterSnapshot(
            sheets=(
                XlsSheetMarkdownSnapshot(
                    name="Summary",
                    markdown=materialized["<summary>"],
                ),
                XlsSheetMarkdownSnapshot(
                    name="Data",
                    markdown=materialized["<data>"],
                ),
            ),
            provider="offline-oneway-differential",
        ),
    )

    node = h28.nodes[h28.root_node_ids[0]]
    assert isinstance(node.payload, TextPayload)
    assert node.payload.text == one_way.markdown


def test_production_reader_has_no_xls_table_runtime_or_process_dependencies() -> None:
    source = inspect.getsource(reader_module)
    forbidden = (
        "import pandas",
        "from pandas",
        "import xlrd",
        "from xlrd",
        "import openpyxl",
        "from openpyxl",
        "import bs4",
        "from bs4",
        "BeautifulSoup(",
        "HtmlConverter(",
        "XlsConverter(",
        "import subprocess",
        "from subprocess",
        "import requests",
        "from requests",
        "import httpx",
        "from httpx",
        "urllib.request",
        "import socket",
        "from socket",
        "time.sleep",
    )
    assert not any(token in source for token in forbidden)
