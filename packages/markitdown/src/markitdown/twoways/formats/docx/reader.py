from __future__ import annotations

from hashlib import sha256
from typing import Any, BinaryIO

from ...ir.document import DocumentIR, SourceDescriptor
from ...ir.serialization import validate_document
from ...ooxml import snapshot_package
from ...readers.base import DocumentIRReader
from ._reader_parts import (
    _FOOTER_REL_SUFFIX,
    _HEADER_REL_SUFFIX,
    _build_part,
    _core_metadata,
    _main_part_uri,
    _read_all,
    _read_members,
    _require_lxml,
)
from .model import DocxReadOptions
from .relationships import relationships_for_part


def read_docx_ir(
    file_stream: BinaryIO,
    stream_info: Any | None = None,
    *,
    options: DocxReadOptions | None = None,
) -> DocumentIR:
    options = options or DocxReadOptions()
    _require_lxml()
    source_bytes = _read_all(file_stream)
    snapshot_package(source_bytes, limits=options.limits)
    members = _read_members(source_bytes)
    main_part = _main_part_uri(members)
    source_digest = sha256(source_bytes).hexdigest()

    canvases: list[Canvas] = []
    nodes: dict[str, Any] = {}
    resources: dict[str, Any] = {}
    diagnostics: list[Any] = []

    body_canvas, body_nodes, body_resources, body_diagnostics = _build_part(
        source_bytes=source_bytes,
        members=members,
        part_uri=main_part,
        kind="document",
        canvas_index=0,
        ordinal=0,
        relationship_id=None,
    )
    canvases.append(body_canvas)
    nodes.update(body_nodes)
    resources.update(body_resources)
    diagnostics.extend(body_diagnostics)

    if options.include_headers_footers:
        main_relationships = relationships_for_part(source_bytes, main_part)
        related_parts = []
        for relationship in main_relationships.values():
            if relationship.external or not relationship.resolved_target:
                continue
            kind = None
            if relationship.relationship_type.endswith(_HEADER_REL_SUFFIX):
                kind = "header"
            elif relationship.relationship_type.endswith(_FOOTER_REL_SUFFIX):
                kind = "footer"
            if kind:
                related_parts.append(
                    (kind, relationship.resolved_target, relationship.relationship_id)
                )
        related_parts.sort(
            key=lambda item: (0 if item[0] == "header" else 1, item[1], item[2])
        )
        counters = {"header": 0, "footer": 0}
        for kind, part_uri, relationship_id in related_parts:
            counters[kind] += 1
            canvas, part_nodes, part_resources, part_diagnostics = _build_part(
                source_bytes=source_bytes,
                members=members,
                part_uri=part_uri,
                kind=kind,
                canvas_index=len(canvases),
                ordinal=counters[kind],
                relationship_id=relationship_id,
            )
            canvases.append(canvas)
            nodes.update(part_nodes)
            resources.update(part_resources)
            diagnostics.extend(part_diagnostics)

    filename = (
        getattr(stream_info, "filename", None) if stream_info is not None else None
    )
    mimetype = (
        getattr(stream_info, "mimetype", None) if stream_info is not None else None
    )
    document = DocumentIR(
        document_id=f"docx-document-{source_digest[:24]}",
        source=SourceDescriptor(
            format="docx",
            filename=filename,
            mimetype=mimetype,
            sha256=source_digest,
            size_bytes=len(source_bytes),
            preserved_source_ref=f"docx:sha256:{source_digest}",
        ),
        metadata=_core_metadata(members),
        canvases=tuple(canvases),
        nodes=nodes,
        resources=resources if options.include_resources else {},
        diagnostics=tuple(diagnostics),
    )
    validate_document(document)
    return document


class DocxIRReader(DocumentIRReader):
    def accepts(self, file_stream: BinaryIO, stream_info: Any, **kwargs: Any) -> bool:
        extension = (getattr(stream_info, "extension", None) or "").lower()
        mimetype = (getattr(stream_info, "mimetype", None) or "").lower()
        return extension == ".docx" or mimetype.startswith(
            "application/vnd.openxmlformats-officedocument.wordprocessingml"
        )

    def read(
        self, file_stream: BinaryIO, stream_info: Any, **kwargs: Any
    ) -> DocumentIR:
        options = kwargs.pop("options", None)
        return read_docx_ir(file_stream, stream_info, options=options)
