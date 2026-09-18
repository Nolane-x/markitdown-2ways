from __future__ import annotations

from hashlib import sha1
from io import BytesIO
import inspect
from pathlib import Path

import pytest

from markitdown._stream_info import StreamInfo
from markitdown.converters import _image_converter as converter_module
from markitdown.twoways.ir.nodes import TextPayload
from markitdown.twoways.readers import image as reader_module
from markitdown.twoways.readers.image import (
    ImageDescriptionSnapshot,
    ImageMetadataSnapshot,
    read_image_snapshot_ir,
)


EXPECTED_CONVERTER_BLOB = "cd49b96d29f50861625cecfb6cee7bdd1eb30b54"
SOURCE = b"offline image differential fixture"


def test_existing_image_converter_blob_is_unchanged() -> None:
    path = Path(inspect.getsourcefile(converter_module.ImageConverter) or "")
    assert path.is_file()
    data = path.read_bytes()
    git_blob = sha1(
        b"blob " + str(len(data)).encode("ascii") + b"\0" + data
    ).hexdigest()
    assert git_blob == EXPECTED_CONVERTER_BLOB


@pytest.mark.parametrize(
    ("metadata", "description"),
    (
        ({"Artist": "A", "Title": "T"}, None),
        ({}, "  Caption text  "),
        ({"Description": "metadata-description", "Title": "T"}, "  Caption text  "),
    ),
)
def test_h25_matches_offline_one_way_materializations(
    monkeypatch,
    metadata: dict[str, str],
    description: str | None,
) -> None:
    info = StreamInfo(
        extension=".jpg",
        mimetype="image/jpeg",
        filename="fixture.jpg",
    )
    monkeypatch.setattr(
        converter_module,
        "exiftool_metadata",
        lambda file_stream, exiftool_path=None: metadata,
    )

    converter = converter_module.ImageConverter()
    kwargs: dict[str, object] = {"exiftool_path": "offline-fixture"}
    description_snapshot = None
    if description is not None:
        monkeypatch.setattr(
            converter,
            "_get_llm_description",
            lambda *args, **inner_kwargs: description,
        )
        kwargs.update(
            {
                "llm_client": object(),
                "llm_model": "vision-test",
                "llm_prompt": None,
            }
        )
        description_snapshot = ImageDescriptionSnapshot(
            content=description,
            provider="offline-llm",
            model="vision-test",
            prompt=None,
            content_type="image/jpeg",
        )

    one_way = converter.convert(BytesIO(SOURCE), info, **kwargs)
    h25 = read_image_snapshot_ir(
        BytesIO(SOURCE),
        stream_info=info,
        metadata=ImageMetadataSnapshot(
            fields=metadata,
            provider="offline-exiftool",
        ),
        description=description_snapshot,
    )
    node = h25.nodes[h25.root_node_ids[0]]
    assert isinstance(node.payload, TextPayload)
    assert node.payload.text == one_way.markdown


def test_production_reader_has_no_exiftool_llm_network_or_process_paths() -> None:
    source = inspect.getsource(reader_module)
    forbidden = (
        "exiftool_metadata",
        "_get_llm_description",
        "chat.completions",
        "openai",
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
