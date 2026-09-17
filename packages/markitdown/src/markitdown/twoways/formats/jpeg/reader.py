from __future__ import annotations

from collections import Counter
from hashlib import sha256
from typing import Any, BinaryIO

from ...capabilities import (
    CAPABILITY_METADATA_KEY,
    CapabilityDecision,
    CapabilityState,
    encode_capabilities,
)
from ...ir.document import Canvas, DocumentIR, DocumentMetadata, SourceDescriptor
from ...ir.nodes import Node, TextPayload
from ...ir.provenance import NativeLocator, Provenance
from ...ir.serialization import validate_document
from ...readers.base import DocumentIRReader
from .limits import JpegLimits
from .parser import parse_jpeg

_JPEG_READ_LIMITS_KEY = "jpeg.read_limits.v1"
_BLOCKER_PRIORITY = (
    "jpeg.exif.multiple_segments",
    "jpeg.metadata.xmp_read_only",
    "jpeg.metadata.iptc_read_only",
    "jpeg.structure.trailing_bytes",
    "jpeg.exif.value_overlap",
    "jpeg.exif.duplicate_tag",
    "jpeg.exif.unsupported_type",
    "jpeg.exif.invalid_text_encoding",
)


def _read_source_bytes(source: BinaryIO) -> bytes:
    data = source.read()
    if isinstance(data, str):
        raise TypeError("JPEG source stream must return bytes")
    if not isinstance(data, (bytes, bytearray, memoryview)):
        raise TypeError("JPEG source stream returned a non-bytes value")
    return bytes(data)


def _limits_metadata(limits: JpegLimits) -> dict[str, int]:
    return {
        "max_source_bytes": limits.max_source_bytes,
        "max_markers": limits.max_markers,
        "max_segment_data_bytes": limits.max_segment_data_bytes,
        "max_ifd_depth": limits.max_ifd_depth,
        "max_ifd_entries": limits.max_ifd_entries,
        "max_total_ifd_entries": limits.max_total_ifd_entries,
        "max_tiff_value_bytes": limits.max_tiff_value_bytes,
        "max_text_value_bytes": limits.max_text_value_bytes,
    }


def _reason_from_blockers(blockers: tuple[str, ...]) -> str | None:
    blocker_set = set(blockers)
    for reason in _BLOCKER_PRIORITY:
        if reason in blocker_set:
            return reason
    return blockers[0] if blockers else None


def _text_capability(
    *,
    blockers: tuple[str, ...],
    tag_count: int,
    ambiguous: bool,
) -> CapabilityDecision:
    reason = _reason_from_blockers(blockers)
    if reason is None and ambiguous:
        reason = "jpeg.exif.value_overlap"
    if reason is None and tag_count != 1:
        reason = "jpeg.exif.duplicate_tag"
    if reason is not None:
        return CapabilityDecision(
            operation="update_jpeg_exif_text",
            state=CapabilityState.READ_ONLY,
            reason_code=reason,
        )
    return CapabilityDecision(
        operation="update_jpeg_exif_text",
        state=CapabilityState.WRITABLE,
        constraints={
            "identity_markdown": False,
            "existing_owner_only": True,
            "fixed_allocation": True,
            "source_preservation": "jpeg-exact-outside-target-slot",
            "tag_identity_immutable": True,
        },
    )


def _owner_metadata(owner: Any, marker: Any) -> dict[str, Any]:
    return {
        "jpeg.exif_tag_id": owner.tag_id,
        "jpeg.exif_tag_name": owner.tag_name,
        "jpeg.marker_index": owner.marker_index,
        "jpeg.segment_start": marker.start,
        "jpeg.segment_end": marker.end,
        "jpeg.marker_start": marker.start,
        "jpeg.marker_end": marker.end,
        "jpeg.ifd_path": owner.ifd_path,
        "jpeg.ifd_entry_offset": owner.entry_offset,
        "jpeg.tiff_type": owner.tiff_type,
        "jpeg.count": owner.count,
        "jpeg.tiff_byte_order": owner.byte_order,
        "jpeg.byte_order": owner.byte_order,
        "jpeg.value_offset": owner.value_offset,
        "jpeg.value_length": owner.value_length,
        "jpeg.inline_value": owner.inline_value,
        "jpeg.value_slot_sha256": owner.value_slot_sha256,
        "jpeg.app1_sha256": owner.app1_sha256,
        "jpeg.marker_raw_sha256": marker.raw_sha256,
        "jpeg.native_source": True,
    }


def read_jpeg_ir(
    source: BinaryIO,
    *,
    filename: str | None = None,
    mimetype: str | None = None,
    limits: JpegLimits | None = None,
) -> DocumentIR:
    active_limits = limits or JpegLimits()
    source_bytes = _read_source_bytes(source)
    parsed = parse_jpeg(source_bytes, limits=active_limits)
    source_digest = sha256(source_bytes).hexdigest()
    tag_counts = Counter(owner.tag_id for owner in parsed.text_owners)

    document_id = f"jpeg-document-{source_digest[:24]}"
    canvas_id = f"jpeg-canvas-{source_digest[:24]}"
    canvas_locator = NativeLocator(
        backend="jpeg",
        part_uri="/",
        object_id="jpeg-image",
    )

    nodes: dict[str, Node] = {}
    root_node_ids: list[str] = []
    for order, owner in enumerate(parsed.text_owners):
        marker = parsed.marker(owner.marker_index)
        node_id = (
            f"jpeg-exif-{source_digest[:16]}-{owner.marker_index}-"
            f"{owner.entry_offset}-{owner.tag_id}"
        )
        locator = NativeLocator(
            backend="jpeg",
            part_uri="/",
            object_id=(
                f"app1:{owner.marker_index}:ifd:{owner.ifd_path}:"
                f"entry:{owner.entry_offset}:tag:{owner.tag_id}"
            ),
            name=owner.tag_name,
            attributes={
                "marker_index": owner.marker_index,
                "ifd_path": owner.ifd_path,
                "entry_offset": owner.entry_offset,
                "tag_id": owner.tag_id,
                "value_offset": owner.value_offset,
                "value_length": owner.value_length,
            },
        )
        capability = _text_capability(
            blockers=parsed.blockers,
            tag_count=tag_counts[owner.tag_id],
            ambiguous=owner.ambiguous,
        )
        metadata = _owner_metadata(owner, marker)
        metadata[CAPABILITY_METADATA_KEY] = encode_capabilities((capability,))
        node = Node(
            node_id=node_id,
            kind="text",
            semantic_role="jpeg-exif-text",
            order=order,
            canvas_id=canvas_id,
            provenance=(
                Provenance(
                    source_format="jpeg",
                    canvas_index=0,
                    part_uri="/",
                    extraction_method="jpeg-exif-ifd0-ascii",
                    metadata={
                        "marker_index": owner.marker_index,
                        "ifd_path": owner.ifd_path,
                        "entry_offset": owner.entry_offset,
                        "tag_id": owner.tag_id,
                    },
                ),
            ),
            native_locator=locator,
            payload=TextPayload(text=owner.value),
            metadata=metadata,
        )
        nodes[node_id] = node
        root_node_ids.append(node_id)

    document = DocumentIR(
        document_id=document_id,
        source=SourceDescriptor(
            format="jpeg",
            filename=filename,
            mimetype=mimetype,
            sha256=source_digest,
            size_bytes=len(source_bytes),
            preserved_source_ref=f"jpeg:sha256:{source_digest}",
        ),
        metadata=DocumentMetadata(
            custom={_JPEG_READ_LIMITS_KEY: _limits_metadata(active_limits)}
        ),
        canvases=(
            Canvas(
                canvas_id=canvas_id,
                index=0,
                kind="image",
                name=filename,
                root_node_ids=tuple(root_node_ids),
                native_locator=canvas_locator,
            ),
        ),
        nodes=nodes,
        root_node_ids=tuple(root_node_ids),
    )
    validate_document(document)
    return document


class JpegIRReader(DocumentIRReader):
    def accepts(self, file_stream: BinaryIO, stream_info: Any, **kwargs: Any) -> bool:
        extension = (getattr(stream_info, "extension", None) or "").lower()
        mimetype = (
            (getattr(stream_info, "mimetype", None) or "")
            .split(";", 1)[0]
            .strip()
            .lower()
        )
        return extension in {".jpg", ".jpeg"} or mimetype in {
            "image/jpeg",
            "image/jpg",
        }

    def read(
        self,
        file_stream: BinaryIO,
        stream_info: Any,
        **kwargs: Any,
    ) -> DocumentIR:
        limits = kwargs.pop("limits", None)
        if kwargs:
            raise TypeError(f"unexpected JPEG reader options: {sorted(kwargs)}")
        return read_jpeg_ir(
            file_stream,
            filename=getattr(stream_info, "filename", None),
            mimetype=getattr(stream_info, "mimetype", None),
            limits=limits,
        )
