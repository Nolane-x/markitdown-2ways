from __future__ import annotations

from hashlib import sha1
from io import BytesIO
import inspect
from pathlib import Path
from types import SimpleNamespace

from markitdown._stream_info import StreamInfo
from markitdown.converters import _doc_intel_converter as converter_module
from markitdown.twoways.readers import document_intelligence as reader_module
from markitdown.twoways.readers.document_intelligence import (
    DocumentIntelligenceAnalysisSnapshot,
    read_document_intelligence_analysis_ir,
)
from markitdown.twoways.ir.nodes import TextPayload


EXPECTED_CONVERTER_BLOB = "f8a5c8e8c82638fc5186105679ff1af0175992c8"
SOURCE = b"%PDF-1.7\noffline differential fixture\n"
CONTENT = "# Heading\n<!-- service\ncomment -->\nBody\n"


def _info() -> StreamInfo:
    return StreamInfo(
        mimetype="application/pdf",
        extension=".pdf",
        filename="fixture.pdf",
    )


def test_existing_doc_intel_converter_blob_is_unchanged() -> None:
    path = Path(
        inspect.getsourcefile(converter_module.DocumentIntelligenceConverter) or ""
    )
    assert path.is_file()
    data = path.read_bytes()
    git_blob = sha1(
        b"blob " + str(len(data)).encode("ascii") + b"\0" + data
    ).hexdigest()
    assert git_blob == EXPECTED_CONVERTER_BLOB


def test_h22_matches_one_way_comment_removal_with_offline_fake(
    monkeypatch,
) -> None:
    class _Feature:
        FORMULAS = "formulas"
        OCR_HIGH_RESOLUTION = "ocrHighResolution"
        STYLE_FONT = "styleFont"

    class _Request:
        def __init__(self, *, bytes_source: bytes) -> None:
            self.bytes_source = bytes_source

    class _Poller:
        def result(self):
            return SimpleNamespace(content=CONTENT)

    class _Client:
        def begin_analyze_document(self, **kwargs):
            assert kwargs["model_id"] == "prebuilt-layout"
            assert kwargs["body"].bytes_source == SOURCE
            assert kwargs["output_content_format"] == "markdown"
            return _Poller()

    fake_client = _Client()
    monkeypatch.setattr(converter_module, "_dependency_exc_info", None)
    monkeypatch.setattr(converter_module, "DocumentAnalysisFeature", _Feature)
    monkeypatch.setattr(converter_module, "AnalyzeDocumentRequest", _Request)
    monkeypatch.setattr(
        converter_module,
        "DocumentIntelligenceClient",
        lambda **kwargs: fake_client,
    )

    converter = converter_module.DocumentIntelligenceConverter(
        endpoint="https://example.invalid",
        credential=object(),
    )
    one_way = converter.convert(BytesIO(SOURCE), _info())

    document = read_document_intelligence_analysis_ir(
        BytesIO(SOURCE),
        stream_info=_info(),
        analysis=DocumentIntelligenceAnalysisSnapshot(
            content=CONTENT,
            provider="offline-fake-client",
        ),
    )
    node = document.nodes[document.root_node_ids[0]]
    assert isinstance(node.payload, TextPayload)
    assert node.payload.text == one_way.markdown


def test_production_reader_has_no_azure_network_or_process_imports() -> None:
    source = inspect.getsource(reader_module)
    forbidden = (
        "azure.ai.documentintelligence",
        "azure.identity",
        "azure.core.credentials",
        "import requests",
        "from requests",
        "import httpx",
        "from httpx",
        "urllib.request",
        "import socket",
        "from socket",
        "import subprocess",
        "from subprocess",
        "time.sleep",
    )
    assert not any(token in source for token in forbidden)
