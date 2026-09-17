from __future__ import annotations

from io import BytesIO

import pytest

from markitdown.twoways.formats.jpeg import patch_jpeg, read_jpeg_ir
from markitdown.twoways.ir.edits import EditOperation

from ._jpeg_fixtures import ARTIST, IMAGE_DESCRIPTION, make_jpeg


def _node(document, tag_id: int = IMAGE_DESCRIPTION):
    return next(
        node
        for node in document.nodes.values()
        if node.semantic_role == "jpeg-exif-text"
        and node.metadata.get("jpeg.exif_tag_id") == tag_id
    )


def test_pillow_confirms_exif_readback_and_decoded_pixels_unchanged_when_available() -> None:
    image_module = pytest.importorskip("PIL.Image")
    source = make_jpeg()
    document = read_jpeg_ir(BytesIO(source), filename="card.jpg")
    description = _node(document, IMAGE_DESCRIPTION)
    output = BytesIO()
    edit = EditOperation(
        operation_id="description",
        type="update_jpeg_exif_text",
        target_node_id=description.node_id,
        payload={
            "tag_id": IMAGE_DESCRIPTION,
            "old_value": description.payload.text,
            "value": "Beta",
        },
    )

    patch_jpeg(document, BytesIO(source), output, edits=(edit,))

    with image_module.open(BytesIO(source)) as before:
        before.load()
        before_pixels = before.tobytes()
        before_size = before.size
        before_mode = before.mode
        before_exif = before.getexif()
        assert before_exif.get(IMAGE_DESCRIPTION) == "Alpha"
        assert before_exif.get(ARTIST) == "Nolane"

    with image_module.open(BytesIO(output.getvalue())) as after:
        after.load()
        after_exif = after.getexif()
        assert after.size == before_size
        assert after.mode == before_mode
        assert after.tobytes() == before_pixels
        assert after_exif.get(IMAGE_DESCRIPTION) == "Beta"
        assert after_exif.get(ARTIST) == "Nolane"
