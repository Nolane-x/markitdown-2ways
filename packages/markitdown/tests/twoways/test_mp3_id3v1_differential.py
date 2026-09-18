from __future__ import annotations

from io import BytesIO

import pytest

from markitdown.twoways.formats.mp3 import parse_mp3, patch_mp3, read_mp3_ir
from markitdown.twoways.ir.edits import EditOperation

from ._mp3_fixtures import make_mp3


def _node(document, field: str):
    return next(
        node
        for node in document.nodes.values()
        if node.semantic_role == "mp3-id3v1-text"
        and node.metadata.get("mp3.id3v1_field") == field
    )


def _edit(document, field: str, value: str) -> EditOperation:
    node = _node(document, field)
    return EditOperation(
        operation_id=f"edit-{field.lower()}",
        type="update_mp3_id3v1_text",
        target_node_id=node.node_id,
        payload={
            "field": field,
            "old_value": node.payload.text,
            "value": value,
        },
    )


def test_audio_prefix_is_byte_identical_after_id3v1_edit() -> None:
    source = make_mp3(title="Alpha", artist="Nolane", album="Lab")
    parsed = parse_mp3(source)
    document = read_mp3_ir(BytesIO(source), filename="song.mp3")
    output = BytesIO()

    patch_mp3(
        document,
        BytesIO(source),
        output,
        edits=(
            _edit(document, "Title", "Beta"),
            _edit(document, "Artist", "Ada"),
        ),
    )

    candidate = output.getvalue()
    assert candidate[: parsed.id3v1_start] == source[: parsed.id3v1_start]
    assert len(candidate) == len(source)


def test_mutagen_confirms_id3v1_semantics_when_available() -> None:
    id3_module = pytest.importorskip("mutagen.id3")
    source = make_mp3(title="Alpha", artist="Nolane", album="Lab")
    document = read_mp3_ir(BytesIO(source), filename="song.mp3")
    output = BytesIO()

    patch_mp3(
        document,
        BytesIO(source),
        output,
        edits=(
            _edit(document, "Title", "Beta"),
            _edit(document, "Artist", "Ada"),
            _edit(document, "Album", "Research"),
        ),
    )

    tags = id3_module.ID3(BytesIO(output.getvalue()), load_v1=True)
    assert tags.getall("TIT2")[0].text == ["Beta"]
    assert tags.getall("TPE1")[0].text == ["Ada"]
    assert tags.getall("TALB")[0].text == ["Research"]
