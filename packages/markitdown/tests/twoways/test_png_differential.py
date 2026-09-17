from __future__ import annotations

from io import BytesIO

import pytest

from markitdown.twoways.formats.png import patch_png, read_png_ir
from markitdown.twoways.ir.edits import EditOperation

from ._png_fixtures import make_png


def test_pillow_confirms_pixels_unchanged_when_available() -> None:
    image_module = pytest.importorskip("PIL.Image")
    source = make_png(text=(("Title", "Alpha"),))
    document = read_png_ir(BytesIO(source), filename="card.png")
    node = next(iter(document.nodes.values()))
    output = BytesIO()
    edit = EditOperation(
        operation_id="title",
        type="update_png_text_metadata",
        target_node_id=node.node_id,
        payload={"keyword": "Title", "old_value": "Alpha", "value": "Beta"},
    )

    patch_png(document, BytesIO(source), output, edits=(edit,))

    with image_module.open(BytesIO(source)) as before:
        before_pixels = before.tobytes()
        before_size = before.size
        before_mode = before.mode
    with image_module.open(BytesIO(output.getvalue())) as after:
        after_pixels = after.tobytes()
        assert after.size == before_size
        assert after.mode == before_mode
        assert after_pixels == before_pixels
        assert after.info.get("Title") == "Beta"


def test_pillow_confirms_ztxt_edit_and_pixels_when_available() -> None:
    image_module = pytest.importorskip("PIL.Image")
    source = make_png(text=(), ztext=(("Comment", "Alpha"),))
    document = read_png_ir(BytesIO(source), filename="compressed.png")
    node = next(iter(document.nodes.values()))
    output = BytesIO()
    edit = EditOperation(
        operation_id="comment",
        type="update_png_text_metadata",
        target_node_id=node.node_id,
        payload={"keyword": "Comment", "old_value": "Alpha", "value": "Beta"},
    )

    patch_png(document, BytesIO(source), output, edits=(edit,))

    with image_module.open(BytesIO(source)) as before:
        before_pixels = before.tobytes()
        before_size = before.size
        before_mode = before.mode
    with image_module.open(BytesIO(output.getvalue())) as after:
        assert after.size == before_size
        assert after.mode == before_mode
        assert after.tobytes() == before_pixels
        assert after.info.get("Comment") == "Beta"
