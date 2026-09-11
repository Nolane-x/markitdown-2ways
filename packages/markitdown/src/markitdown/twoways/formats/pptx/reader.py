from __future__ import annotations

from hashlib import sha256
from io import BytesIO
from typing import Any, BinaryIO

from ..._errors import MissingOptionalDependencyError
from ...ir.document import (
    Canvas,
    DocumentIR,
    DocumentMetadata,
    SourceDescriptor,
)
from ...ir.serialization import validate_document
from ...readers.base import DocumentIRReader
from ...ooxml import snapshot_package
from ...ooxml.package import read_binary_stream
from .locators import slide_locator
from .model import PptxReadOptions
from .shapes import build_note_node, build_shape_tree


def _require_pptx():
    try:
        from pptx import Presentation
        from pptx.enum.shapes import MSO_SHAPE_TYPE
    except (ImportError, ModuleNotFoundError) as exc:
        raise MissingOptionalDependencyError(
            "PPTX 2Ways support requires the pptx optional feature.",
            details={"feature": "pptx", "dependencies": ["python-pptx", "lxml"]},
        ) from exc
    return Presentation, MSO_SHAPE_TYPE


def _presentation_relationship_id(presentation: Any, slide: Any) -> str | None:
    for relationship_id, relationship in presentation.part.rels.items():
        try:
            if relationship.target_part is slide.part:
                return relationship_id
        except ValueError:
            continue
    return None


def _shape_sort_key(item: tuple[int, Any]) -> tuple[int, int, int]:
    z_order, shape = item
    top = int(getattr(shape, "top", 0) or 0)
    left = int(getattr(shape, "left", 0) or 0)
    return (top, left, z_order)


def read_pptx_ir(
    file_stream: BinaryIO,
    stream_info: Any | None = None,
    *,
    options: PptxReadOptions | None = None,
) -> DocumentIR:
    options = options or PptxReadOptions()
    Presentation, MSO_SHAPE_TYPE = _require_pptx()
    source_bytes = read_binary_stream(file_stream, stream_label="PPTX input")
    snapshot_package(source_bytes, limits=options.limits)

    presentation = Presentation(BytesIO(source_bytes))
    source_digest = sha256(source_bytes).hexdigest()
    filename = (
        getattr(stream_info, "filename", None) if stream_info is not None else None
    )
    mimetype = (
        getattr(stream_info, "mimetype", None) if stream_info is not None else None
    )

    canvases: list[Canvas] = []
    nodes: dict[str, Any] = {}
    resources: dict[str, Any] = {}
    native_payloads: dict[str, Any] = {}

    for slide_index, slide in enumerate(presentation.slides):
        part_uri = str(slide.part.partname)
        canvas_id = f"pptx-slide-{slide_index + 1}"
        title_shape = slide.shapes.title
        built: list[tuple[int, str]] = []

        for z_order, shape in enumerate(slide.shapes):
            node, subtree_nodes, node_resources, subtree_payloads = build_shape_tree(
                shape,
                slide_index=slide_index,
                canvas_id=canvas_id,
                part_uri=part_uri,
                z_order=z_order,
                is_title=title_shape is not None and shape == title_shape,
                picture_shape_type=MSO_SHAPE_TYPE.PICTURE,
                group_shape_type=MSO_SHAPE_TYPE.GROUP,
            )
            nodes.update(subtree_nodes)
            resources.update(node_resources)
            native_payloads.update(subtree_payloads)
            built.append((z_order, node.node_id))

        shape_by_id = {node_id: nodes[node_id] for _, node_id in built}
        ordered_visual_nodes = [
            node_id
            for _, node_id in sorted(
                built,
                key=lambda item: (
                    int(
                        shape_by_id[item[1]].geometry.y
                        if shape_by_id[item[1]].geometry
                        else 0
                    ),
                    int(
                        shape_by_id[item[1]].geometry.x
                        if shape_by_id[item[1]].geometry
                        else 0
                    ),
                    item[0],
                ),
            )
        ]
        note_node_id = None
        if options.include_notes and slide.has_notes_slide:
            notes_slide = slide.notes_slide
            notes_shape = notes_slide.notes_placeholder
            if notes_shape is not None:
                note_node = build_note_node(
                    notes_shape,
                    slide_index=slide_index,
                    canvas_id=canvas_id,
                    part_uri=str(notes_slide.part.partname),
                    order=len(built),
                )
                nodes[note_node.node_id] = note_node
                note_node_id = note_node.node_id
        root_node_ids = tuple(
            ordered_visual_nodes + ([note_node_id] if note_node_id is not None else [])
        )
        canvases.append(
            Canvas(
                canvas_id=canvas_id,
                index=slide_index,
                kind="slide",
                width=float(presentation.slide_width),
                height=float(presentation.slide_height),
                unit="emu",
                root_node_ids=root_node_ids,
                native_locator=slide_locator(
                    slide,
                    index=slide_index,
                    relationship_id=_presentation_relationship_id(presentation, slide),
                ),
                metadata={"pptx:part_uri": part_uri},
            )
        )

    core = presentation.core_properties
    document = DocumentIR(
        document_id=f"pptx-document-{source_digest[:24]}",
        source=SourceDescriptor(
            format="pptx",
            filename=filename,
            mimetype=mimetype,
            sha256=source_digest,
            size_bytes=len(source_bytes),
            preserved_source_ref=f"pptx:sha256:{source_digest}",
        ),
        metadata=DocumentMetadata(
            title=core.title or None,
            subject=core.subject or None,
            author=core.author or None,
        ),
        canvases=tuple(canvases),
        nodes=nodes,
        resources=resources if options.include_resources else {},
        native_payloads=native_payloads if options.preserve_unknown_native else {},
    )
    validate_document(document)
    return document


class PptxIRReader(DocumentIRReader):
    def accepts(self, file_stream: BinaryIO, stream_info: Any, **kwargs: Any) -> bool:
        extension = (getattr(stream_info, "extension", None) or "").lower()
        mimetype = (getattr(stream_info, "mimetype", None) or "").lower()
        return extension == ".pptx" or mimetype.startswith(
            "application/vnd.openxmlformats-officedocument.presentationml"
        )

    def read(
        self, file_stream: BinaryIO, stream_info: Any, **kwargs: Any
    ) -> DocumentIR:
        options = kwargs.pop("options", None)
        return read_pptx_ir(file_stream, stream_info, options=options)
