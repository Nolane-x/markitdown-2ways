from __future__ import annotations

from hashlib import sha256
from io import BytesIO
import posixpath
from typing import Any, BinaryIO
from zipfile import ZipFile

from ..._errors import MissingOptionalDependencyError
from ...ir.document import Canvas, DocumentIR, DocumentMetadata, SourceDescriptor
from ...ir.provenance import NativeLocator
from ...ir.serialization import validate_document
from ...ooxml import parse_xml_part, snapshot_package
from ...readers.base import DocumentIRReader
from .model import DocxReadOptions
from .relationships import relationships_for_part
from .structures import build_paragraph_node, build_picture_nodes, build_table_node

_MAIN_CONTENT_TYPE_SUFFIX = "wordprocessingml.document.main+xml"
_HEADER_REL_SUFFIX = "/header"
_FOOTER_REL_SUFFIX = "/footer"


def _require_lxml() -> None:
    try:
        import lxml  # noqa: F401
    except (ImportError, ModuleNotFoundError) as exc:
        raise MissingOptionalDependencyError(
            "DOCX 2Ways support requires the docx optional feature.",
            details={"feature": "docx", "dependencies": ["lxml"]},
        ) from exc


def _read_all(file_stream: BinaryIO) -> bytes:
    data = file_stream.read()
    if not isinstance(data, bytes):
        raise TypeError("DOCX input stream must yield bytes")
    return data


def _read_members(source_bytes: bytes) -> dict[str, bytes]:
    with ZipFile(BytesIO(source_bytes), "r") as archive:
        return {info.filename: archive.read(info) for info in archive.infolist()}


def _main_part_uri(members: dict[str, bytes]) -> str:
    root = parse_xml_part(members["[Content_Types].xml"])
    for element in root:
        if element.tag.rsplit("}", 1)[-1] != "Override":
            continue
        content_type = element.get("ContentType") or ""
        if content_type.endswith(_MAIN_CONTENT_TYPE_SUFFIX):
            part_name = element.get("PartName")
            if part_name:
                return part_name
    if "word/document.xml" in members:
        return "/word/document.xml"
    raise ValueError("DOCX package does not expose a main document part")


def _core_metadata(members: dict[str, bytes]) -> DocumentMetadata:
    data = members.get("docProps/core.xml")
    if data is None:
        return DocumentMetadata()
    root = parse_xml_part(data)
    values: dict[str, str] = {}
    for element in root.iter():
        name = element.tag.rsplit("}", 1)[-1]
        if name in {"title", "subject", "creator", "language"} and element.text:
            values[name] = element.text
    return DocumentMetadata(
        title=values.get("title"),
        subject=values.get("subject"),
        author=values.get("creator"),
        language=values.get("language"),
    )


def _part_canvas_id(kind: str, ordinal: int) -> str:
    return "docx-body" if kind == "document" else f"docx-{kind}-{ordinal}"


def _root_prefix(root: Any) -> str:
    name = root.tag.rsplit("}", 1)[-1]
    if name == "document":
        return "/*[local-name()='document']/*[local-name()='body']"
    return f"/*[local-name()='{name}']"


def _build_part(
    *,
    source_bytes: bytes,
    members: dict[str, bytes],
    part_uri: str,
    kind: str,
    canvas_index: int,
    ordinal: int,
    relationship_id: str | None,
) -> tuple[Canvas, dict[str, Any], dict[str, Any], list[Any]]:
    member_name = part_uri.lstrip("/")
    root = parse_xml_part(members[member_name])
    relationships = relationships_for_part(source_bytes, part_uri)
    canvas_id = _part_canvas_id(kind, ordinal)
    nodes: dict[str, Any] = {}
    resources: dict[str, Any] = {}
    diagnostics: list[Any] = []
    root_ids: list[str] = []
    prefix = _root_prefix(root)
    container = root
    if kind == "document":
        bodies = root.xpath('./*[local-name()="body"]')
        if len(bodies) != 1:
            raise ValueError("DOCX main document must contain one body")
        container = bodies[0]

    paragraph_index = 0
    table_index = 0
    order = 0
    for child in container:
        name = child.tag.rsplit("}", 1)[-1]
        if name == "sectPr":
            continue
        if name == "p":
            paragraph_path = f"{prefix}/*[local-name()='p'][{paragraph_index + 1}]"
            picture_docprs = child.xpath('.//*[local-name()="docPr"]')
            text = "".join(child.xpath('.//*[local-name()="t"]/text()'))
            if text or not picture_docprs:
                node = build_paragraph_node(
                    child,
                    part_uri=part_uri,
                    canvas_id=canvas_id,
                    canvas_index=canvas_index,
                    paragraph_index=paragraph_index,
                    path=paragraph_path,
                    order=order,
                )
                nodes[node.node_id] = node
                root_ids.append(node.node_id)
                order += 1
            picture_nodes, picture_resources, picture_diagnostics = build_picture_nodes(
                child,
                part_uri=part_uri,
                canvas_id=canvas_id,
                canvas_index=canvas_index,
                paragraph_path=paragraph_path,
                order_start=order,
                relationships=relationships,
                package_members=members,
            )
            for node in picture_nodes:
                nodes[node.node_id] = node
                root_ids.append(node.node_id)
                order += 1
            resources.update(picture_resources)
            diagnostics.extend(picture_diagnostics)
            paragraph_index += 1
            continue
        if name == "tbl":
            table_path = f"{prefix}/*[local-name()='tbl'][{table_index + 1}]"
            node = build_table_node(
                child,
                part_uri=part_uri,
                canvas_id=canvas_id,
                canvas_index=canvas_index,
                table_index=table_index,
                path=table_path,
                order=order,
            )
            nodes[node.node_id] = node
            root_ids.append(node.node_id)
            table_index += 1
            order += 1
            continue

    canvas = Canvas(
        canvas_id=canvas_id,
        index=canvas_index,
        kind=kind,
        root_node_ids=tuple(root_ids),
        native_locator=NativeLocator(
            backend="docx-ooxml",
            part_uri=part_uri,
            relationship_id=relationship_id,
            attributes={"part_kind": kind},
        ),
        metadata={"docx:part_uri": part_uri},
    )
    return canvas, nodes, resources, diagnostics


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
                related_parts.append((kind, relationship.resolved_target, relationship.relationship_id))
        related_parts.sort(key=lambda item: (0 if item[0] == "header" else 1, item[1], item[2]))
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

    filename = getattr(stream_info, "filename", None) if stream_info is not None else None
    mimetype = getattr(stream_info, "mimetype", None) if stream_info is not None else None
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

    def read(self, file_stream: BinaryIO, stream_info: Any, **kwargs: Any) -> DocumentIR:
        options = kwargs.pop("options", None)
        return read_docx_ir(file_stream, stream_info, options=options)
