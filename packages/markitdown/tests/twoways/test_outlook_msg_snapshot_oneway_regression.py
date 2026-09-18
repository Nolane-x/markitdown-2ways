from __future__ import annotations

from hashlib import sha1
from io import BytesIO
import inspect
from pathlib import Path
from types import SimpleNamespace

import pytest

from markitdown._stream_info import StreamInfo
from markitdown.converters import _outlook_msg_converter as converter_module
from markitdown.twoways.ir.nodes import TextPayload
from markitdown.twoways.readers import outlook_msg as reader_module
from markitdown.twoways.readers.outlook_msg import (
    OutlookMsgConverterSnapshot,
    read_outlook_msg_snapshot_ir,
)


EXPECTED_CONVERTER_BLOB = "79d7656e5bd32d3b6aaa143a32635d5fb3e8f087"
SOURCE = b"offline outlook msg differential fixture"


def test_existing_outlook_msg_converter_blob_is_unchanged() -> None:
    path = Path(inspect.getsourcefile(converter_module.OutlookMsgConverter) or "")
    assert path.is_file()
    data = path.read_bytes()
    git_blob = sha1(
        b"blob " + str(len(data)).encode("ascii") + b"\0" + data
    ).hexdigest()
    assert git_blob == EXPECTED_CONVERTER_BLOB


@pytest.mark.parametrize(
    ("sender", "recipients", "subject", "body"),
    (
        ("alice@example.com", "bob@example.com", "Subject", "Body"),
        (None, None, "Only subject", None),
        ("", "", "", ""),
    ),
)
def test_h26_matches_unchanged_one_way_projection_offline(
    monkeypatch,
    sender: str | None,
    recipients: str | None,
    subject: str | None,
    body: str | None,
) -> None:
    class _FakeMessage:
        def close(self) -> None:
            pass

    fake_ole = SimpleNamespace(OleFileIO=lambda file_stream: _FakeMessage())
    monkeypatch.setattr(converter_module, "_dependency_exc_info", None)
    monkeypatch.setattr(converter_module, "olefile", fake_ole)

    converter = converter_module.OutlookMsgConverter()
    monkeypatch.setattr(converter, "_get_long_properties", lambda msg: {})
    monkeypatch.setattr(converter, "_get_codec_name", lambda value: None)

    values = {
        "0C1F": sender,
        "0E04": recipients,
        "0037": subject,
        "1000": body,
    }
    monkeypatch.setattr(
        converter,
        "_get_property_data",
        lambda msg, property_tag, encoding=None: values[property_tag],
    )

    info = StreamInfo(
        extension=".msg",
        mimetype="application/vnd.ms-outlook",
        filename="fixture.msg",
    )
    one_way = converter.convert(BytesIO(SOURCE), info)
    h26 = read_outlook_msg_snapshot_ir(
        BytesIO(SOURCE),
        stream_info=info,
        snapshot=OutlookMsgConverterSnapshot(
            sender=sender,
            recipients=recipients,
            subject=subject,
            body=body,
            provider="offline-fixture",
        ),
    )

    node = h26.nodes[h26.root_node_ids[0]]
    assert isinstance(node.payload, TextPayload)
    assert node.payload.text == one_way.markdown
    assert h26.metadata.title == one_way.title


def test_production_reader_has_no_optional_msg_runtime_path() -> None:
    source = inspect.getsource(reader_module)
    forbidden = (
        "import olefile",
        "from olefile",
        "charset_normalizer",
        "OutlookMsgConverter(",
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
