from __future__ import annotations

from hashlib import sha1
from io import BytesIO
import inspect
from pathlib import Path

import pytest

from markitdown._stream_info import StreamInfo
from markitdown.converters import _cu_converter as converter_module
from markitdown.twoways.ir.nodes import TextPayload
from markitdown.twoways.readers import content_understanding as reader_module
from markitdown.twoways.readers.content_understanding import (
    ContentUnderstandingAnalysisSnapshot,
    read_content_understanding_analysis_ir,
)


EXPECTED_CONVERTER_BLOB = "230e3d86bf533241b68dfc3d023e48b3effdc788"
SOURCE = b"offline content-understanding differential fixture"
OUTPUT = "---\ncontentType: audioVisual\n---\nSpeaker 1: hello\n"


def _make_one_way_converter():
    converter = converter_module.ContentUnderstandingConverter.__new__(
        converter_module.ContentUnderstandingConverter
    )
    converter._file_types = converter_module._ALL_FILE_TYPES
    converter._analyzer_id = None
    converter._analyzer_modality = None
    return converter


def test_existing_content_understanding_converter_blob_is_unchanged() -> None:
    path = Path(
        inspect.getsourcefile(converter_module.ContentUnderstandingConverter) or ""
    )
    assert path.is_file()
    data = path.read_bytes()
    git_blob = sha1(
        b"blob " + str(len(data)).encode("ascii") + b"\0" + data
    ).hexdigest()
    assert git_blob == EXPECTED_CONVERTER_BLOB


@pytest.mark.parametrize(
    "info",
    (
        StreamInfo(extension=".pdf", mimetype="audio/mpeg"),
        StreamInfo(extension=".jpg", mimetype="image/jpeg"),
        StreamInfo(extension=".mp3", mimetype="audio/mpeg"),
        StreamInfo(extension=".mp4", mimetype="video/mp4"),
        StreamInfo(mimetype="audio/x-wav"),
        StreamInfo(mimetype="video/x-m4v"),
    ),
)
def test_h23_matches_default_one_way_routing_and_output(
    monkeypatch,
    info: StreamInfo,
) -> None:
    class _Poller:
        def result(self):
            return object()

    class _Client:
        def __init__(self) -> None:
            self.calls: list[dict[str, object]] = []

        def begin_analyze_binary(self, **kwargs):
            self.calls.append(dict(kwargs))
            assert kwargs["binary_input"] == SOURCE
            return _Poller()

    client = _Client()
    converter = _make_one_way_converter()
    converter._client = client
    monkeypatch.setattr(converter_module, "to_llm_input", lambda result: OUTPUT)

    one_way = converter.convert(BytesIO(SOURCE), info)
    assert len(client.calls) == 1
    call = client.calls[0]

    document = read_content_understanding_analysis_ir(
        BytesIO(SOURCE),
        stream_info=info,
        analysis=ContentUnderstandingAnalysisSnapshot(
            content=one_way.markdown,
            provider="offline-fake-client",
            analyzer_id=str(call["analyzer_id"]),
            content_type=str(call["content_type"]),
        ),
    )

    node = document.nodes[document.root_node_ids[0]]
    assert isinstance(node.payload, TextPayload)
    assert node.payload.text == one_way.markdown

    evidence = document.metadata.custom["twoways.content_understanding_analysis.v1"]
    assert evidence["analyzer_id"] == call["analyzer_id"]
    assert evidence["content_type"] == call["content_type"]


def test_production_reader_has_no_azure_network_or_process_imports() -> None:
    source = inspect.getsource(reader_module)
    forbidden = (
        "azure.ai.contentunderstanding",
        "azure.identity",
        "azure.core.credentials",
        "ContentUnderstandingClient(",
        "DefaultAzureCredential(",
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
