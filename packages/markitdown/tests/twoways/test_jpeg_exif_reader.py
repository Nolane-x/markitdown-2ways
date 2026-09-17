from __future__ import annotations

from io import BytesIO

from markitdown.twoways.capabilities import CapabilityState, capabilities_for_node
from markitdown.twoways.formats.jpeg import JpegLimits, read_jpeg_ir
from markitdown.twoways.ir.nodes import TextPayload
from markitdown.twoways.ir.serialization import canonical_json_digest, validate_document

from ._jpeg_fixtures import (
    ARTIST,
    IMAGE_DESCRIPTION,
    ExifTextEntry,
    iptc_app13,
    make_jpeg,
    xmp_app1,
)


def _nodes(document):
    return [
        node
        for node in document.nodes.values()
        if node.semantic_role == "jpeg-exif-text"
    ]


def _decision(document, tag_id: int):
    node = next(
        node for node in _nodes(document) if node.metadata["jpeg.exif_tag_id"] == tag_id
    )
    return capabilities_for_node(node).for_operation("update_jpeg_exif_text")


def test_reads_exif_ifd0_text_into_deterministic_ir() -> None:
    source = make_jpeg()

    first = read_jpeg_ir(BytesIO(source), filename="card.jpg", mimetype="image/jpeg")
    second = read_jpeg_ir(BytesIO(source), filename="card.jpg", mimetype="image/jpeg")

    validate_document(first)
    assert canonical_json_digest(first) == canonical_json_digest(second)
    assert first.source is not None
    assert first.source.format == "jpeg"
    assert first.source.filename == "card.jpg"
    assert first.source.mimetype == "image/jpeg"
    assert first.source.size_bytes == len(source)
    assert first.source.sha256 is not None
    assert first.source.preserved_source_ref == f"jpeg:sha256:{first.source.sha256}"
    assert len(first.canvases) == 1
    assert first.canvases[0].kind == "image"

    nodes = _nodes(first)
    assert [node.metadata["jpeg.exif_tag_id"] for node in nodes] == [
        IMAGE_DESCRIPTION,
        ARTIST,
    ]
    assert [
        node.payload.text for node in nodes if isinstance(node.payload, TextPayload)
    ] == [
        "Alpha",
        "Nolane",
    ]
    for node in nodes:
        assert isinstance(node.payload, TextPayload)
        assert node.native_locator is not None
        assert node.native_locator.backend == "jpeg"
        assert node.native_locator.part_uri == "/"
        assert node.metadata["jpeg.ifd_path"] == "IFD0"
        assert node.metadata["jpeg.tiff_type"] == 2
        assert isinstance(node.metadata["jpeg.marker_index"], int)
        assert isinstance(node.metadata["jpeg.ifd_entry_offset"], int)
        assert isinstance(node.metadata["jpeg.value_offset"], int)
        assert isinstance(node.metadata["jpeg.value_slot_sha256"], str)
        assert isinstance(node.metadata["jpeg.app1_sha256"], str)


def test_unique_safe_owner_advertises_h14_mutation() -> None:
    document = read_jpeg_ir(BytesIO(make_jpeg()), filename="card.jpg")

    decision = _decision(document, IMAGE_DESCRIPTION)

    assert decision.state is CapabilityState.WRITABLE
    assert decision.reason_code is None
    assert decision.constraints == {
        "identity_markdown": False,
        "existing_owner_only": True,
        "fixed_allocation": True,
        "source_preservation": "jpeg-exact-outside-target-slot",
        "tag_identity_immutable": True,
    }


def test_xmp_authority_makes_supported_exif_owner_read_only() -> None:
    document = read_jpeg_ir(
        BytesIO(make_jpeg(extra_segments=(xmp_app1(),))),
        filename="xmp.jpg",
    )

    decision = _decision(document, IMAGE_DESCRIPTION)

    assert decision.state is CapabilityState.READ_ONLY
    assert decision.reason_code == "jpeg.metadata.xmp_read_only"


def test_iptc_authority_makes_supported_exif_owner_read_only() -> None:
    document = read_jpeg_ir(
        BytesIO(make_jpeg(extra_segments=(iptc_app13(),))),
        filename="iptc.jpg",
    )

    decision = _decision(document, ARTIST)

    assert decision.state is CapabilityState.READ_ONLY
    assert decision.reason_code == "jpeg.metadata.iptc_read_only"


def test_multiple_exif_segments_are_readable_but_read_only() -> None:
    document = read_jpeg_ir(BytesIO(make_jpeg(second_exif=True)), filename="multi.jpg")

    for node in _nodes(document):
        decision = capabilities_for_node(node).for_operation("update_jpeg_exif_text")
        assert decision.state is CapabilityState.READ_ONLY
        assert decision.reason_code == "jpeg.exif.multiple_segments"


def test_duplicate_target_tag_is_readable_but_read_only() -> None:
    source = make_jpeg(
        entries=(
            ExifTextEntry(ARTIST, "Ada", capacity=12),
            ExifTextEntry(ARTIST, "Grace", capacity=12),
        )
    )
    document = read_jpeg_ir(BytesIO(source), filename="duplicate.jpg")

    nodes = _nodes(document)
    assert len(nodes) == 2
    for node in nodes:
        decision = capabilities_for_node(node).for_operation("update_jpeg_exif_text")
        assert decision.state is CapabilityState.READ_ONLY
        assert decision.reason_code == "jpeg.exif.duplicate_tag"


def test_overlapping_value_allocations_are_read_only() -> None:
    document = read_jpeg_ir(
        BytesIO(make_jpeg(overlap_external=True)),
        filename="overlap.jpg",
    )

    for node in _nodes(document):
        decision = capabilities_for_node(node).for_operation("update_jpeg_exif_text")
        assert decision.state is CapabilityState.READ_ONLY
        assert decision.reason_code == "jpeg.exif.value_overlap"


def test_read_time_limits_are_persisted_as_authority() -> None:
    limits = JpegLimits(max_source_bytes=1024 * 1024, max_text_value_bytes=32)

    document = read_jpeg_ir(BytesIO(make_jpeg()), filename="card.jpg", limits=limits)

    assert document.metadata.custom["jpeg.read_limits.v1"] == {
        "max_source_bytes": limits.max_source_bytes,
        "max_markers": limits.max_markers,
        "max_segment_data_bytes": limits.max_segment_data_bytes,
        "max_ifd_depth": limits.max_ifd_depth,
        "max_ifd_entries": limits.max_ifd_entries,
        "max_total_ifd_entries": limits.max_total_ifd_entries,
        "max_tiff_value_bytes": limits.max_tiff_value_bytes,
        "max_text_value_bytes": limits.max_text_value_bytes,
    }
