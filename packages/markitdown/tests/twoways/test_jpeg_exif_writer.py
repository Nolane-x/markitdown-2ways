from __future__ import annotations

from io import BytesIO

import pytest

from markitdown.twoways._errors import (
    PatchPreconditionError,
    SourcePackageMismatchError,
    UnsupportedEditError,
)
from markitdown.twoways.formats.jpeg import patch_jpeg, read_jpeg_ir
from markitdown.twoways.ir.edits import EditOperation, EditPrecondition
from markitdown.twoways.ir.semantics import native_locator_digest, node_semantic_digest

from ._jpeg_fixtures import ARTIST, IMAGE_DESCRIPTION, ExifTextEntry, make_jpeg


def _node(document, tag_id: int = IMAGE_DESCRIPTION):
    return next(
        node
        for node in document.nodes.values()
        if node.semantic_role == "jpeg-exif-text"
        and node.metadata.get("jpeg.exif_tag_id") == tag_id
    )


def _edit(
    document,
    value: str,
    *,
    tag_id: int = IMAGE_DESCRIPTION,
    old_value: str | None = None,
) -> EditOperation:
    node = _node(document, tag_id)
    expected_old = node.payload.text if old_value is None else old_value
    return EditOperation(
        operation_id=f"edit-{tag_id}",
        type="update_jpeg_exif_text",
        target_node_id=node.node_id,
        precondition=EditPrecondition(
            expected_semantic_digest=node_semantic_digest(node),
            expected_native_locator_digest=native_locator_digest(node),
            expected_old_value=expected_old,
        ),
        payload={
            "tag_id": tag_id,
            "old_value": expected_old,
            "value": value,
        },
    )


def test_noop_patch_preserves_source_bytes_exactly() -> None:
    source = make_jpeg()
    document = read_jpeg_ir(BytesIO(source), filename="card.jpg")
    output = BytesIO()

    result = patch_jpeg(document, BytesIO(source), output, edits=())

    assert output.getvalue() == source
    assert result.format == "jpeg"
    assert result.mode == "patch"
    assert result.fidelity.claimed_tier == "exact-preserve"


def test_semantic_noop_preserves_source_bytes_exactly() -> None:
    source = make_jpeg()
    document = read_jpeg_ir(BytesIO(source), filename="card.jpg")
    output = BytesIO()

    result = patch_jpeg(
        document,
        BytesIO(source),
        output,
        edits=(_edit(document, "Alpha"),),
    )

    assert output.getvalue() == source
    assert result.fidelity.claimed_tier == "exact-preserve"


def test_updates_external_ifd0_text_inside_existing_allocation() -> None:
    source = make_jpeg(
        entries=(
            ExifTextEntry(IMAGE_DESCRIPTION, "Alpha", capacity=24),
            ExifTextEntry(ARTIST, "Nolane", capacity=16),
        )
    )
    document = read_jpeg_ir(BytesIO(source), filename="card.jpg")
    output = BytesIO()

    result = patch_jpeg(
        document,
        BytesIO(source),
        output,
        edits=(_edit(document, "Beta"),),
    )

    candidate = output.getvalue()
    reread = read_jpeg_ir(BytesIO(candidate), filename="card.jpg")
    assert len(candidate) == len(source)
    assert _node(reread).payload.text == "Beta"
    assert _node(reread, ARTIST).payload.text == "Nolane"
    assert result.fidelity.claimed_tier == "high"


def test_updates_inline_ascii_slot_without_relocation() -> None:
    source = make_jpeg(
        entries=(ExifTextEntry(IMAGE_DESCRIPTION, "A", capacity=4, force_inline=True),)
    )
    document = read_jpeg_ir(BytesIO(source), filename="inline.jpg")
    output = BytesIO()

    patch_jpeg(
        document,
        BytesIO(source),
        output,
        edits=(_edit(document, "BC"),),
    )

    candidate = output.getvalue()
    reread = read_jpeg_ir(BytesIO(candidate), filename="inline.jpg")
    assert len(candidate) == len(source)
    assert _node(reread).payload.text == "BC"


def test_updates_big_endian_owner_without_changing_endianness() -> None:
    source = make_jpeg(
        entries=(ExifTextEntry(ARTIST, "Ada", capacity=16),),
        endian="big",
    )
    document = read_jpeg_ir(BytesIO(source), filename="big.jpg")
    output = BytesIO()

    patch_jpeg(
        document,
        BytesIO(source),
        output,
        edits=(_edit(document, "Grace", tag_id=ARTIST),),
    )

    reread = read_jpeg_ir(BytesIO(output.getvalue()), filename="big.jpg")
    node = _node(reread, ARTIST)
    assert node.payload.text == "Grace"
    assert node.metadata["jpeg.tiff_byte_order"] == "big"


def test_multiple_distinct_owner_edits_are_transactional() -> None:
    source = make_jpeg()
    document = read_jpeg_ir(BytesIO(source), filename="card.jpg")
    output = BytesIO()

    patch_jpeg(
        document,
        BytesIO(source),
        output,
        edits=(
            _edit(document, "Beta", tag_id=IMAGE_DESCRIPTION),
            _edit(document, "Ada", tag_id=ARTIST),
        ),
    )

    reread = read_jpeg_ir(BytesIO(output.getvalue()), filename="card.jpg")
    assert _node(reread, IMAGE_DESCRIPTION).payload.text == "Beta"
    assert _node(reread, ARTIST).payload.text == "Ada"


def test_growth_beyond_existing_allocation_fails_without_output() -> None:
    source = make_jpeg(
        entries=(ExifTextEntry(IMAGE_DESCRIPTION, "A", capacity=4, force_inline=True),)
    )
    document = read_jpeg_ir(BytesIO(source), filename="small.jpg")
    output = BytesIO()

    with pytest.raises(UnsupportedEditError, match="allocation|growth"):
        patch_jpeg(
            document,
            BytesIO(source),
            output,
            edits=(_edit(document, "TOO-LONG"),),
        )

    assert output.getvalue() == b""


def test_non_ascii_replacement_fails_without_output() -> None:
    source = make_jpeg()
    document = read_jpeg_ir(BytesIO(source), filename="card.jpg")
    output = BytesIO()

    with pytest.raises(UnsupportedEditError, match="ASCII"):
        patch_jpeg(
            document,
            BytesIO(source),
            output,
            edits=(_edit(document, "Tiếng Việt"),),
        )

    assert output.getvalue() == b""


def test_embedded_nul_replacement_fails_without_output() -> None:
    source = make_jpeg()
    document = read_jpeg_ir(BytesIO(source), filename="card.jpg")
    output = BytesIO()

    with pytest.raises(UnsupportedEditError, match="NUL"):
        patch_jpeg(
            document,
            BytesIO(source),
            output,
            edits=(_edit(document, "Beta\x00hidden"),),
        )

    assert output.getvalue() == b""


def test_source_digest_mismatch_fails_before_output() -> None:
    source = make_jpeg()
    document = read_jpeg_ir(BytesIO(source), filename="card.jpg")
    different = make_jpeg(
        entries=(
            ExifTextEntry(IMAGE_DESCRIPTION, "Different", capacity=16),
            ExifTextEntry(ARTIST, "Nolane", capacity=16),
        )
    )
    output = BytesIO()

    with pytest.raises(SourcePackageMismatchError):
        patch_jpeg(document, BytesIO(different), output, edits=())

    assert output.getvalue() == b""


def test_stale_old_value_fails_before_output() -> None:
    source = make_jpeg()
    document = read_jpeg_ir(BytesIO(source), filename="card.jpg")
    output = BytesIO()

    with pytest.raises(PatchPreconditionError, match="old|stale"):
        patch_jpeg(
            document,
            BytesIO(source),
            output,
            edits=(_edit(document, "Beta", old_value="stale"),),
        )

    assert output.getvalue() == b""


def test_duplicate_transaction_target_fails_before_output() -> None:
    source = make_jpeg()
    document = read_jpeg_ir(BytesIO(source), filename="card.jpg")
    output = BytesIO()

    with pytest.raises(UnsupportedEditError, match="duplicate"):
        patch_jpeg(
            document,
            BytesIO(source),
            output,
            edits=(
                _edit(document, "Beta"),
                _edit(document, "Gamma"),
            ),
        )

    assert output.getvalue() == b""
