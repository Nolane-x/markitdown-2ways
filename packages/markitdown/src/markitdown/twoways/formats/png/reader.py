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
from ...ir.document import Canvas, DocumentIR, SourceDescriptor
from ...ir.nodes import Node, TextPayload
from ...ir.provenance import NativeLocator, Provenance
from ...ir.serialization import validate_document
from ...readers.base import DocumentIRReader
from .limits import PngLimits
from .parser import parse_png


def _read_source_bytes(source: BinaryIO) -> bytes:
    data = source.read()
    if isinstance(data, str):
        raise TypeError("PNG source stream must return bytes")
    if not isinstance(data, (bytes, bytearray, memoryview)):
        raise TypeError("PNG source stream returned a non-bytes value")
    return bytes(data)


def _text_capability(
    *,
    keyword_count: int,
    is_apng: bool,
) -> CapabilityDecision:
    if is_apng:
        return CapabilityDecision(
            operation="update_png_text_metadata",
            state=CapabilityState.READ_ONLY,
            reason_code="png.apng.read_only",
        )
    if keyword_count != 1:
        return CapabilityDecision(
            operation="update_png_text_metadata",
            state=CapabilityState.READ_ONLY,
            reason_code="png.text.duplicate_keyword",
        )
    return CapabilityDecision(
        operation="update_png_text_metadata",
        state=CapabilityState.WRITABLE,
        constraints={
            "identity_markdown": False,
            "source_preservation": "png-chunk-exact-unrequested",
            "existing_owner_only": True,
            "keyword_immutable": True,
        },
    )


def read_png_ir(
    source: BinaryIO,
    *,
    filename: str | None = None,
    mimetype: str | None = None,
    limits: PngLimits | None = None,
) -> DocumentIR:
    active_limits = limits or PngLimits()
    source_bytes = _read_source_bytes(source)
    parsed = parse_png(source_bytes, limits=active_limits)
    source_digest = sha256(source_bytes).hexdigest()
    keyword_counts = Counter(owner.keyword for owner in parsed.text_owners)

    document_id = f"png-document-{source_digest[:24]}"
    canvas_id = f"png-canvas-{source_digest[:24]}"
    canvas_locator = NativeLocator(
        backend="png",
        part_uri="/",
        object_id="png-image",
    )

    nodes: dict[str, Node] = {}
    root_node_ids: list[str] = []
    for order, owner in enumerate(parsed.text_owners):
        chunk = parsed.chunk(owner.chunk_index)
        node_id = f"png-text-{source_digest[:16]}-{owner.chunk_index}"
        locator = NativeLocator(
            backend="png",
            part_uri="/",
            object_id=f"chunk:{owner.chunk_index}:{owner.keyword}",
            name=owner.keyword,
            attributes={
                "chunk_index": owner.chunk_index,
                "chunk_type": "tEXt",
                "keyword": owner.keyword,
            },
        )
        capability = _text_capability(
            keyword_count=keyword_counts[owner.keyword],
            is_apng=parsed.is_apng,
        )
        node = Node(
            node_id=node_id,
            kind="text",
            semantic_role="png-text-metadata",
            order=order,
            canvas_id=canvas_id,
            provenance=(
                Provenance(
                    source_format="png",
                    canvas_index=0,
                    part_uri="/",
                    extraction_method="png-text-chunk",
                    metadata={"chunk_index": owner.chunk_index},
                ),
            ),
            native_locator=locator,
            payload=TextPayload(text=owner.value),
            metadata={
                "png.keyword": owner.keyword,
                "png.chunk_index": owner.chunk_index,
                "png.chunk_type": "tEXt",
                "png.chunk_start": chunk.start,
                "png.chunk_end": chunk.end,
                "png.data_start": chunk.data_start,
                "png.data_end": chunk.data_end,
                "png.raw_sha256": owner.raw_sha256,
                "png.data_sha256": owner.data_sha256,
                "png.is_apng": parsed.is_apng,
                "png.native_source": True,
                CAPABILITY_METADATA_KEY: encode_capabilities((capability,)),
            },
        )
        nodes[node_id] = node
        root_node_ids.append(node_id)

    document = DocumentIR(
        document_id=document_id,
        source=SourceDescriptor(
            format="png",
            filename=filename,
            mimetype=mimetype,
            sha256=source_digest,
            size_bytes=len(source_bytes),
            preserved_source_ref=f"png:sha256:{source_digest}",
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


class PngIRReader(DocumentIRReader):
    def accepts(self, file_stream: BinaryIO, stream_info: Any, **kwargs: Any) -> bool:
        extension = (getattr(stream_info, "extension", None) or "").lower()
        mimetype = (
            (getattr(stream_info, "mimetype", None) or "")
            .split(";", 1)[0]
            .strip()
            .lower()
        )
        return extension == ".png" or mimetype == "image/png"

    def read(
        self,
        file_stream: BinaryIO,
        stream_info: Any,
        **kwargs: Any,
    ) -> DocumentIR:
        limits = kwargs.pop("limits", None)
        if kwargs:
            raise TypeError(f"unexpected PNG reader options: {sorted(kwargs)}")
        return read_png_ir(
            file_stream,
            filename=getattr(stream_info, "filename", None),
            mimetype=getattr(stream_info, "mimetype", None),
            limits=limits,
        )
