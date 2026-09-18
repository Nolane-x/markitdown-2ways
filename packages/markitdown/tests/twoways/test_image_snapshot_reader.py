from __future__ import annotations

from hashlib import sha256
from io import BytesIO

import pytest

from markitdown._stream_info import StreamInfo
from markitdown.twoways import (
    CapabilityState,
    ImageDescriptionSnapshot,
    ImageMetadataSnapshot,
    build_capability_report,
    canonical_json_bytes,
    canonical_json_digest,
    capabilities_for_node,
    decode_document,
    read_image_snapshot_ir,
)
from markitdown.twoways.ir.nodes import TextPayload


SOURCE = b"image snapshot fixture bytes"
JPEG_INFO = StreamInfo(
    extension=".jpg",
    mimetype="image/jpeg",
    filename="demo.jpg",
)

METADATA = ImageMetadataSnapshot(
    fields={
        "Artist": "Nolane",
        "Title": "Demo",
        "GPSPosition": "20.0 106.0",
    },
    provider="offline-exiftool",
    materialization_id="metadata-001",
)

DESCRIPTION = ImageDescriptionSnapshot(
    content="  A small demo image.  \n",
    provider="offline-llm",
    model="vision-test",
    prompt=None,
    content_type="image/jpeg",
    materialization_id="caption-001",
)


def _root(document):
    assert len(document.root_node_ids) == 1
    return document.nodes[document.root_node_ids[0]]


def test_combined_projection_matches_one_way_order_and_description_strip() -> None:
    document = read_image_snapshot_ir(
        BytesIO(SOURCE),
        stream_info=JPEG_INFO,
        metadata=METADATA,
        description=DESCRIPTION,
    )
    node = _root(document)

    assert isinstance(node.payload, TextPayload)
    assert node.payload.text == (
        "Title: Demo\n"
        "Artist: Nolane\n"
        "GPSPosition: 20.0 106.0\n"
        "\n# Description:\n"
        "A small demo image.\n"
    )
    assert node.semantic_role == "derived_image"
    assert node.native_locator is None
    assert document.canvases[0].kind == "derived-image"
    assert document.canvases[0].native_locator is None

    assert document.source is not None
    assert document.source.format == "image-converter-derived-source"
    assert document.source.sha256 == sha256(SOURCE).hexdigest()
    assert document.source.size_bytes == len(SOURCE)

    evidence = document.metadata.custom["twoways.image_converter_snapshot.v1"]
    assert evidence["accepted_by"] == "extension"
    assert evidence["metadata_field_count"] == 3
    assert evidence["description_provider"] == "offline-llm"
    assert evidence["description_model"] == "vision-test"
    assert evidence["description_effective_prompt"] == (
        "Write a detailed caption for this image."
    )
    assert evidence["description_content_type"] == "image/jpeg"
    assert evidence["exiftool_executed_by_twoways"] is False
    assert evidence["llm_called_by_twoways"] is False
    assert evidence["network_performed_by_twoways"] is False
    assert evidence["subprocess_performed_by_twoways"] is False


def test_metadata_only_description_only_and_empty_projection() -> None:
    metadata_only = read_image_snapshot_ir(
        BytesIO(SOURCE),
        stream_info=JPEG_INFO,
        metadata=METADATA,
    )
    description_only = read_image_snapshot_ir(
        BytesIO(SOURCE),
        stream_info=JPEG_INFO,
        description=DESCRIPTION,
    )
    empty = read_image_snapshot_ir(
        BytesIO(SOURCE),
        stream_info=JPEG_INFO,
    )

    assert _root(metadata_only).payload.text == (
        "Title: Demo\nArtist: Nolane\nGPSPosition: 20.0 106.0\n"
    )
    assert _root(description_only).payload.text == (
        "\n# Description:\nA small demo image.\n"
    )
    assert _root(empty).payload.text == ""


def test_root_is_explicitly_derived_and_not_native_writable() -> None:
    document = read_image_snapshot_ir(
        BytesIO(SOURCE),
        stream_info=JPEG_INFO,
        metadata=METADATA,
        description=DESCRIPTION,
    )
    node = _root(document)

    decision = capabilities_for_node(node).for_operation("replace_text")
    assert decision.state is CapabilityState.DERIVED
    assert decision.reason_code == "image.output.not_native_writable"
    assert decision.constraints == {
        "identity_markdown": False,
        "native_owner": False,
        "remote_writeback": False,
        "materialization": "explicit-local-only",
    }

    report = build_capability_report(document)
    assert report.total_nodes == 1
    assert report.derived_nodes == 1
    assert report.writable_nodes == 0
    assert dict(report.writable_by_operation) == {}


def test_source_metadata_and_description_are_independent_identity_authorities() -> None:
    baseline = read_image_snapshot_ir(
        BytesIO(SOURCE),
        stream_info=JPEG_INFO,
        metadata=METADATA,
        description=DESCRIPTION,
    )
    source_changed = read_image_snapshot_ir(
        BytesIO(SOURCE + b"x"),
        stream_info=JPEG_INFO,
        metadata=METADATA,
        description=DESCRIPTION,
    )
    metadata_changed = read_image_snapshot_ir(
        BytesIO(SOURCE),
        stream_info=JPEG_INFO,
        metadata=ImageMetadataSnapshot(
            fields={"Title": "Changed"},
            provider="offline-exiftool",
        ),
        description=DESCRIPTION,
    )
    description_changed = read_image_snapshot_ir(
        BytesIO(SOURCE),
        stream_info=JPEG_INFO,
        metadata=METADATA,
        description=ImageDescriptionSnapshot(
            content="Different caption",
            provider="offline-llm",
            model="vision-test",
            content_type="image/jpeg",
        ),
    )

    assert len(
        {
            baseline.document_id,
            source_changed.document_id,
            metadata_changed.document_id,
            description_changed.document_id,
        }
    ) == 4
    assert baseline.source is not None
    assert source_changed.source is not None
    assert metadata_changed.source is not None
    assert baseline.source.sha256 != source_changed.source.sha256
    assert baseline.source.sha256 == metadata_changed.source.sha256


def test_repeated_reads_and_canonical_round_trip_are_deterministic() -> None:
    first = read_image_snapshot_ir(
        BytesIO(SOURCE),
        stream_info=JPEG_INFO,
        metadata=METADATA,
        description=DESCRIPTION,
    )
    second = read_image_snapshot_ir(
        BytesIO(SOURCE),
        stream_info=JPEG_INFO,
        metadata=METADATA,
        description=DESCRIPTION,
    )

    assert canonical_json_digest(first) == canonical_json_digest(second)
    encoded = canonical_json_bytes(first)
    decoded = decode_document(encoded)
    assert canonical_json_bytes(decoded) == encoded
    assert decoded.schema_version == "0.1.0"


@pytest.mark.parametrize(
    ("info", "accepted_by"),
    (
        (StreamInfo(extension=".jpg"), "extension"),
        (StreamInfo(extension=".jpeg"), "extension"),
        (StreamInfo(extension=".png"), "extension"),
        (StreamInfo(mimetype="image/jpeg"), "mimetype"),
        (StreamInfo(mimetype="image/jpeg; charset=binary"), "mimetype"),
        (StreamInfo(mimetype="image/png"), "mimetype"),
    ),
)
def test_exact_one_way_acceptance_surface(
    info: StreamInfo,
    accepted_by: str,
) -> None:
    document = read_image_snapshot_ir(BytesIO(SOURCE), stream_info=info)
    evidence = document.metadata.custom["twoways.image_converter_snapshot.v1"]
    assert evidence["accepted_by"] == accepted_by


@pytest.mark.parametrize(
    "info",
    (
        StreamInfo(extension=".gif"),
        StreamInfo(extension=".webp"),
        StreamInfo(mimetype="image/gif"),
        StreamInfo(mimetype="image/webp"),
        StreamInfo(),
    ),
)
def test_outside_one_way_acceptance_surface_fails_closed(info: StreamInfo) -> None:
    with pytest.raises(ValueError, match="ImageConverter"):
        read_image_snapshot_ir(BytesIO(SOURCE), stream_info=info)
