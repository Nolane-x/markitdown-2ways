from __future__ import annotations

from hashlib import sha1
from io import BytesIO
import inspect
from pathlib import Path
from types import SimpleNamespace

import pytest

from markitdown._stream_info import StreamInfo
from markitdown.converters import _pdf_converter as converter_module
from markitdown.twoways.ir.nodes import TextPayload
from markitdown.twoways.readers import pdf_converter as reader_module
from markitdown.twoways.readers.pdf_converter import (
    PdfConverterExtractionSnapshot,
    read_pdf_converter_snapshot_ir,
)


EXPECTED_CONVERTER_BLOB = "ffbcbd990cfc40a577404c453ebe47bf477c4929"
SOURCE = b"%PDF-1.7\noffline H27 differential fixture\n"


def test_existing_pdf_converter_blob_is_unchanged() -> None:
    path = Path(inspect.getsourcefile(converter_module.PdfConverter) or "")
    assert path.is_file()
    data = path.read_bytes()
    git_blob = sha1(
        b"blob " + str(len(data)).encode("ascii") + b"\0" + data
    ).hexdigest()
    assert git_blob == EXPECTED_CONVERTER_BLOB


@pytest.mark.parametrize(
    "raw",
    (
        ".1\nText",
        ".2\n\nText",
        "prefix\n.10\nvalue\nsuffix",
        ".3",
        ".A\nText",
        "plain\ntext\n",
        "",
    ),
)
def test_h27_local_postprocess_matches_unchanged_one_way_helper(raw: str) -> None:
    expected = converter_module._merge_partial_numbering_lines(raw)
    document = read_pdf_converter_snapshot_ir(
        BytesIO(SOURCE),
        stream_info=StreamInfo(extension=".pdf"),
        snapshot=PdfConverterExtractionSnapshot(
            extracted_text=raw,
            provider="offline-helper-differential",
            extraction_path="test-helper",
        ),
    )
    node = document.nodes[document.root_node_ids[0]]
    assert isinstance(node.payload, TextPayload)
    assert node.payload.text == expected


def test_h27_matches_full_one_way_converter_with_offline_extractors(
    monkeypatch,
) -> None:
    raw = ".1\n\nGeneral requirement\n.2\nSecond requirement\n"

    class _Page:
        def extract_text(self):
            return "page text not used by final whole-document route"

        def close(self) -> None:
            pass

    class _Pdf:
        pages = [_Page()]

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            pass

    monkeypatch.setattr(
        converter_module,
        "pdfplumber",
        SimpleNamespace(open=lambda stream: _Pdf()),
    )
    monkeypatch.setattr(
        converter_module,
        "_extract_form_content_from_words",
        lambda page: None,
    )
    monkeypatch.setattr(
        converter_module.pdfminer.high_level,
        "extract_text",
        lambda stream: raw,
    )
    monkeypatch.setattr(converter_module, "_dependency_exc_info", None)

    info = StreamInfo(
        extension=".pdf",
        mimetype="application/pdf",
        filename="fixture.pdf",
    )
    one_way = converter_module.PdfConverter().convert(BytesIO(SOURCE), info)
    h27 = read_pdf_converter_snapshot_ir(
        BytesIO(SOURCE),
        stream_info=info,
        snapshot=PdfConverterExtractionSnapshot(
            extracted_text=raw,
            provider="offline-extractor-fake",
            extraction_path="pdfminer-whole-document",
        ),
    )

    node = h27.nodes[h27.root_node_ids[0]]
    assert isinstance(node.payload, TextPayload)
    assert node.payload.text == one_way.markdown


def test_production_reader_has_no_pdf_runtime_or_process_dependencies() -> None:
    source = inspect.getsource(reader_module)
    forbidden = (
        "import pdfminer",
        "from pdfminer",
        "import pdfplumber",
        "from pdfplumber",
        "PdfConverter(",
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
