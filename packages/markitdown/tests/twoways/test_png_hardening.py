from __future__ import annotations

from dataclasses import replace
from io import BytesIO

import pytest

from markitdown.twoways._errors import UnsupportedEditError
from markitdown.twoways.formats.png import PngLimits, patch_png, read_png_ir
from markitdown.twoways.formats.png.parser import PngFormatError, parse_png
from markitdown.twoways.ir.edits import EditOperation

from ._png_fixtures import make_png


def _node(document):
    return next(
        node
        for node in document.nodes.values()
        if node.semantic_role == "png-text-metadata"
    )


def _raw_edit(document, value: str) -> EditOperation:
    node = _node(document)
    return EditOperation(
        operation_id="edit",
        type="update_png_text_metadata",
        target_node_id=node.node_id,
        payload={
            "keyword": node.metadata["png.keyword"],
            "old_value": node.payload.text,
            "value": value,
        },
    )


def test_invalid_png_keyword_is_rejected_by_reader() -> None:
    source = make_png(text=((" Bad", "Alpha"),))

    with pytest.raises(PngFormatError, match="keyword"):
        read_png_ir(BytesIO(source), filename="bad.png")


def test_nul_replacement_fails_without_output() -> None:
    source = make_png()
    document = read_png_ir(BytesIO(source), filename="card.png")
    output = BytesIO()

    with pytest.raises(UnsupportedEditError, match="NUL"):
        patch_png(
            document,
            BytesIO(source),
            output,
            edits=(_raw_edit(document, "bad\x00value"),),
        )

    assert output.getvalue() == b""


def test_non_latin1_replacement_fails_without_output() -> None:
    source = make_png()
    document = read_png_ir(BytesIO(source), filename="card.png")
    output = BytesIO()

    with pytest.raises(UnsupportedEditError, match="ISO-8859-1"):
        patch_png(
            document,
            BytesIO(source),
            output,
            edits=(_raw_edit(document, "snowman \u2603"),),
        )

    assert output.getvalue() == b""


def test_text_value_limit_is_enforced_without_output() -> None:
    source = make_png()
    document = read_png_ir(BytesIO(source), filename="card.png")
    output = BytesIO()
    limits = PngLimits(max_text_value_bytes=3)

    with pytest.raises(UnsupportedEditError, match="value limit"):
        patch_png(
            document,
            BytesIO(source),
            output,
            edits=(_raw_edit(document, "four"),),
            limits=limits,
        )

    assert output.getvalue() == b""


def test_apng_policy_blocker_fails_without_output() -> None:
    source = make_png(apng=True)
    document = read_png_ir(BytesIO(source), filename="animated.png")
    output = BytesIO()

    with pytest.raises(UnsupportedEditError, match="read-only"):
        patch_png(
            document,
            BytesIO(source),
            output,
            edits=(_raw_edit(document, "Beta"),),
        )

    assert output.getvalue() == b""


def test_duplicate_native_target_is_rejected_transactionally() -> None:
    source = make_png()
    document = read_png_ir(BytesIO(source), filename="card.png")
    edit = _raw_edit(document, "Beta")
    duplicate = replace(edit, operation_id="edit-2", payload={**edit.payload, "value": "Gamma"})
    output = BytesIO()

    with pytest.raises(UnsupportedEditError, match="duplicate"):
        patch_png(
            document,
            BytesIO(source),
            output,
            edits=(edit, duplicate),
        )

    assert output.getvalue() == b""


def test_shorter_replacement_preserves_every_unrequested_raw_chunk() -> None:
    source = make_png(
        text=(("Title", "A long original title"), ("Author", "Nolane")),
        ancillary=((b"pHYs", b"\x00" * 9),),
    )
    document = read_png_ir(BytesIO(source), filename="card.png")
    title = next(
        node
        for node in document.nodes.values()
        if node.metadata.get("png.keyword") == "Title"
    )
    edit = EditOperation(
        operation_id="shorter",
        type="update_png_text_metadata",
        target_node_id=title.node_id,
        payload={
            "keyword": "Title",
            "old_value": "A long original title",
            "value": "B",
        },
    )
    output = BytesIO()

    patch_png(document, BytesIO(source), output, edits=(edit,))

    source_parsed = parse_png(source)
    candidate_parsed = parse_png(output.getvalue())
    target_index = title.metadata["png.chunk_index"]
    assert len(source_parsed.chunks) == len(candidate_parsed.chunks)
    for before, after in zip(source_parsed.chunks, candidate_parsed.chunks):
        if before.index != target_index:
            assert after.raw == before.raw
