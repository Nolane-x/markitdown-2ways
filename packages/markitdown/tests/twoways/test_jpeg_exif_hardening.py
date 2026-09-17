from __future__ import annotations

from dataclasses import replace
from io import BytesIO

import pytest

from markitdown.twoways._errors import (
    PatchPreconditionError,
    SourcePackageMismatchError,
    UnsupportedEditError,
)
from markitdown.twoways.capabilities import (
    CAPABILITY_METADATA_KEY,
    CapabilityDecision,
    CapabilityState,
    encode_capabilities,
)
from markitdown.twoways.formats.jpeg import JpegLimits, patch_jpeg, read_jpeg_ir
from markitdown.twoways.ir.edits import EditOperation
from markitdown.twoways.ir.provenance import NativeLocator

from ._jpeg_fixtures import (
    ARTIST,
    IMAGE_DESCRIPTION,
    ExifTextEntry,
    iptc_app13,
    make_jpeg,
    xmp_app1,
)


def _node(document, tag_id: int = IMAGE_DESCRIPTION):
    return next(
        node
        for node in document.nodes.values()
        if node.semantic_role == "jpeg-exif-text"
        and node.metadata.get("jpeg.exif_tag_id") == tag_id
    )


def _edit(node, value: str) -> EditOperation:
    return EditOperation(
        operation_id=f"edit-{node.node_id}",
        type="update_jpeg_exif_text",
        target_node_id=node.node_id,
        payload={
            "tag_id": node.metadata["jpeg.exif_tag_id"],
            "old_value": node.payload.text,
            "value": value,
        },
    )


def _force_writable(document, node):
    writable = encode_capabilities(
        (
            CapabilityDecision(
                operation="update_jpeg_exif_text",
                state=CapabilityState.WRITABLE,
            ),
        )
    )
    forged_node = replace(
        node,
        metadata={**node.metadata, CAPABILITY_METADATA_KEY: writable},
    )
    return replace(document, nodes={**document.nodes, node.node_id: forged_node})


def _replace_node(document, node):
    return replace(document, nodes={**document.nodes, node.node_id: node})


def test_source_size_mismatch_fails_before_output() -> None:
    source = make_jpeg()
    document = read_jpeg_ir(BytesIO(source), filename="card.jpg")
    assert document.source is not None
    forged = replace(
        document,
        source=replace(document.source, size_bytes=len(source) + 1),
    )
    output = BytesIO()

    with pytest.raises(SourcePackageMismatchError):
        patch_jpeg(forged, BytesIO(source), output, edits=())

    assert output.getvalue() == b""


@pytest.mark.parametrize(
    ("metadata_key", "replacement"),
    (
        ("jpeg.exif_tag_name", "Forged"),
        ("jpeg.marker_index", 999),
        ("jpeg.segment_start", 999),
        ("jpeg.segment_end", 999),
        ("jpeg.ifd_path", "IFD0.forged"),
        ("jpeg.ifd_entry_offset", 999),
        ("jpeg.tiff_type", 7),
        ("jpeg.count", 999),
        ("jpeg.tiff_byte_order", "big"),
        ("jpeg.value_offset", 999),
        ("jpeg.value_length", 999),
        ("jpeg.value_slot_sha256", "0" * 64),
        ("jpeg.app1_sha256", "0" * 64),
    ),
)
def test_forged_native_metadata_fails_before_output(
    metadata_key: str,
    replacement: object,
) -> None:
    source = make_jpeg()
    document = read_jpeg_ir(BytesIO(source), filename="card.jpg")
    node = _node(document)
    if metadata_key == "jpeg.tiff_byte_order" and node.metadata[metadata_key] == replacement:
        replacement = "little"
    forged_node = replace(
        node,
        metadata={**node.metadata, metadata_key: replacement},
    )
    forged = _replace_node(document, forged_node)
    output = BytesIO()

    with pytest.raises(PatchPreconditionError, match="native|stale|evidence|binding"):
        patch_jpeg(
            forged,
            BytesIO(source),
            output,
            edits=(_edit(forged_node, "Beta"),),
        )

    assert output.getvalue() == b""


def test_forged_native_locator_fails_before_output() -> None:
    source = make_jpeg()
    document = read_jpeg_ir(BytesIO(source), filename="card.jpg")
    node = _node(document)
    assert node.native_locator is not None
    forged_node = replace(
        node,
        native_locator=NativeLocator(
            backend="jpeg",
            part_uri="/",
            object_id="app1:999:ifd:IFD0:entry:999:tag:270",
            name=node.native_locator.name,
            attributes=dict(node.native_locator.attributes),
        ),
    )
    forged = _replace_node(document, forged_node)
    output = BytesIO()

    with pytest.raises(PatchPreconditionError, match="locator|binding|native"):
        patch_jpeg(
            forged,
            BytesIO(source),
            output,
            edits=(_edit(forged_node, "Beta"),),
        )

    assert output.getvalue() == b""


@pytest.mark.parametrize(
    ("source", "tag_id", "reason_match"),
    (
        (
            make_jpeg(extra_segments=(xmp_app1(),)),
            IMAGE_DESCRIPTION,
            "XMP|xmp",
        ),
        (
            make_jpeg(extra_segments=(iptc_app13(),)),
            ARTIST,
            "IPTC|iptc",
        ),
        (
            make_jpeg(second_exif=True),
            IMAGE_DESCRIPTION,
            "multiple|segments",
        ),
        (
            make_jpeg(
                entries=(
                    ExifTextEntry(ARTIST, "Ada", capacity=12),
                    ExifTextEntry(ARTIST, "Grace", capacity=12),
                )
            ),
            ARTIST,
            "duplicate",
        ),
        (
            make_jpeg(overlap_external=True),
            IMAGE_DESCRIPTION,
            "overlap",
        ),
    ),
)
def test_forged_writable_capability_cannot_bypass_fresh_source_policy(
    source: bytes,
    tag_id: int,
    reason_match: str,
) -> None:
    document = read_jpeg_ir(BytesIO(source), filename="blocked.jpg")
    node = _node(document, tag_id)
    forged = _force_writable(document, node)
    forged_node = forged.nodes[node.node_id]
    output = BytesIO()

    with pytest.raises(UnsupportedEditError, match=reason_match):
        patch_jpeg(
            forged,
            BytesIO(source),
            output,
            edits=(_edit(forged_node, "Beta"),),
        )

    assert output.getvalue() == b""


def test_read_time_text_limit_cannot_be_loosened_by_writer() -> None:
    source = make_jpeg(
        entries=(ExifTextEntry(IMAGE_DESCRIPTION, "A", capacity=32),)
    )
    read_limits = JpegLimits(max_text_value_bytes=2)
    document = read_jpeg_ir(
        BytesIO(source),
        filename="limited.jpg",
        limits=read_limits,
    )
    node = _node(document)
    output = BytesIO()

    with pytest.raises(UnsupportedEditError, match="limit"):
        patch_jpeg(
            document,
            BytesIO(source),
            output,
            edits=(_edit(node, "ABCDE"),),
            limits=JpegLimits(max_text_value_bytes=1024),
        )

    assert output.getvalue() == b""


def test_complete_transaction_preflight_happens_before_output() -> None:
    source = make_jpeg()
    document = read_jpeg_ir(BytesIO(source), filename="card.jpg")
    description = _node(document, IMAGE_DESCRIPTION)
    artist = _node(document, ARTIST)
    invalid_artist_edit = EditOperation(
        operation_id="invalid-artist",
        type="update_jpeg_exif_text",
        target_node_id=artist.node_id,
        payload={
            "tag_id": ARTIST,
            "old_value": artist.payload.text,
            "value": "This replacement is far too long for the fixed Artist allocation",
        },
    )
    output = BytesIO()

    with pytest.raises(UnsupportedEditError):
        patch_jpeg(
            document,
            BytesIO(source),
            output,
            edits=(
                _edit(description, "Beta"),
                invalid_artist_edit,
            ),
        )

    assert output.getvalue() == b""


def test_payload_tag_identity_is_immutable() -> None:
    source = make_jpeg()
    document = read_jpeg_ir(BytesIO(source), filename="card.jpg")
    node = _node(document, IMAGE_DESCRIPTION)
    edit = EditOperation(
        operation_id="retag",
        type="update_jpeg_exif_text",
        target_node_id=node.node_id,
        payload={
            "tag_id": ARTIST,
            "old_value": node.payload.text,
            "value": "Beta",
        },
    )
    output = BytesIO()

    with pytest.raises(PatchPreconditionError, match="tag|immutable"):
        patch_jpeg(document, BytesIO(source), output, edits=(edit,))

    assert output.getvalue() == b""


def test_payload_shape_is_exact() -> None:
    source = make_jpeg()
    document = read_jpeg_ir(BytesIO(source), filename="card.jpg")
    node = _node(document)
    edit = EditOperation(
        operation_id="extra-field",
        type="update_jpeg_exif_text",
        target_node_id=node.node_id,
        payload={
            "tag_id": IMAGE_DESCRIPTION,
            "old_value": node.payload.text,
            "value": "Beta",
            "unexpected": True,
        },
    )
    output = BytesIO()

    with pytest.raises(UnsupportedEditError, match="payload"):
        patch_jpeg(document, BytesIO(source), output, edits=(edit,))

    assert output.getvalue() == b""


def test_unsupported_edit_type_fails_before_output() -> None:
    source = make_jpeg()
    document = read_jpeg_ir(BytesIO(source), filename="card.jpg")
    node = _node(document)
    edit = EditOperation(
        operation_id="wrong-op",
        type="replace_text",
        target_node_id=node.node_id,
        payload={"value": "Beta"},
    )
    output = BytesIO()

    with pytest.raises(UnsupportedEditError, match="update_jpeg_exif_text|unsupported"):
        patch_jpeg(document, BytesIO(source), output, edits=(edit,))

    assert output.getvalue() == b""
