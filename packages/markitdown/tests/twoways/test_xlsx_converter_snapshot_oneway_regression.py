from __future__ import annotations

from hashlib import sha1
from io import BytesIO
import inspect
from pathlib import Path
from types import SimpleNamespace

from markitdown._stream_info import StreamInfo
from markitdown.converters import _xlsx_converter as converter_module
from markitdown.twoways.ir.nodes import TextPayload
from markitdown.twoways.readers import xlsx_converter as reader_module
from markitdown.twoways.readers.xlsx_converter import (
    XlsxConverterSnapshot,
    XlsxSheetMarkdownSnapshot,
    read_xlsx_converter_snapshot_ir,
)


EXPECTED_CONVERTER_BLOB = "355dd8f8d74ab5c9a40bba37e1f7a7d601eeba27"
SOURCE = b"offline H29 XLSX differential fixture"


def test_existing_xlsx_converter_blob_is_unchanged() -> None:
    path = Path(inspect.getsourcefile(converter_module.XlsxConverter) or "")
    assert path.is_file()
    data = path.read_bytes()
    git_blob = sha1(
        b"blob " + str(len(data)).encode("ascii") + b"\0" + data
    ).hexdigest()
    assert git_blob == EXPECTED_CONVERTER_BLOB


def test_h29_matches_full_one_way_xlsx_assembly_offline(monkeypatch) -> None:
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

    monkeypatch.setattr(
        converter_module,
        "_read_xlsx_sheets",
        lambda file_stream: frames,
    )
    monkeypatch.setattr(converter_module, "_xlsx_dependency_exc_info", None)

    converter = converter_module.XlsxConverter()
    monkeypatch.setattr(
        converter._html_converter,
        "convert_string",
        lambda html_content, **kwargs: SimpleNamespace(
            markdown=materialized[html_content]
        ),
    )

    info = StreamInfo(
        extension=".xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename="fixture.xlsx",
    )
    one_way = converter.convert(BytesIO(SOURCE), info)
    h29 = read_xlsx_converter_snapshot_ir(
        BytesIO(SOURCE),
        stream_info=info,
        snapshot=XlsxConverterSnapshot(
            sheets=(
                XlsxSheetMarkdownSnapshot(
                    name="Summary",
                    markdown=materialized["<summary>"],
                ),
                XlsxSheetMarkdownSnapshot(
                    name="Data",
                    markdown=materialized["<data>"],
                ),
            ),
            provider="offline-oneway-differential",
            materialization_path="openpyxl-direct",
        ),
    )

    node = h29.nodes[h29.root_node_ids[0]]
    assert isinstance(node.payload, TextPayload)
    assert node.payload.text == one_way.markdown


def test_production_reader_has_no_xlsx_table_runtime_or_process_dependencies() -> None:
    source = inspect.getsource(reader_module)
    forbidden = (
        "import pandas",
        "from pandas",
        "import openpyxl",
        "from openpyxl",
        "import zipfile",
        "from zipfile",
        "import bs4",
        "from bs4",
        "BeautifulSoup(",
        "HtmlConverter(",
        "XlsxConverter(",
        "_read_xlsx_sheets(",
        "_repair_sheetview_show_zeroes(",
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
