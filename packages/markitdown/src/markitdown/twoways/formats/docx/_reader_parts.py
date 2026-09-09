from __future__ import annotations

from io import BytesIO
from typing import Any, BinaryIO
from zipfile import ZipFile

from ..._errors import MissingOptionalDependencyError
from ...ir.document import Canvas, DocumentMetadata
from ...ir.provenance import NativeLocator
from ...ooxml import parse_xml_part
from .relationships import relationships_for_part
from .structures import build_paragraph_node, build_picture_nodes, build_table_node

_CONTENT_TYPES_NS = "http://schemas.openxmlformats.org/package/2006/content-types"
_CONTENT_TYPES_TAG = f"{{{_CONTENT_TYPES_NS}}}Types"
_OVERRIDE_TAG = f"{{{_CONTENT_TYPES_NS}}}Override"
_MAIN_CONTENT_TYPE = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"
)
_WORDPROCESSING_NAMESPACES = frozenset(
    {
        "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
        "http://purl.oclc.org/ooxml/wordprocessingml/main",
    }
)
_PART_ROOT_NAMES = {"document": "document", "header": "hdr", "footer": "ftr"}
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
    if root.tag != _CONTENT_TYPES_TAG:
        raise ValueError("DOCX Content Types namespace is invalid")
    candidates: list[str] = []
    override_types: dict[str, str] = {}
    for element in root:
        if not isinstance(element.tag, str):
            continue
        if element.tag.rsplit("}", 1)[-1] != "Override":
            continue
        if element.tag != _OVERRIDE_TAG:
            raise ValueError("DOCX Override namespace is invalid")
        part_name = element.get("PartName")
        content_type = element.get("ContentType") or ""
        if part_name:
            previous = override_types.get(part_name)
            if previous is not None and previous != content_type:
                raise ValueError("DOCX Content Types contains conflicting Overrides")
            override_types[part_name] = content_type
        if content_type == _MAIN_CONTENT_TYPE:
            if not part_name:
                raise ValueError("DOCX main document Override is missing PartName")
            if not part_name.startswith("/") or part_name.startswith("//"):
                raise ValueError("DOCX main document PartName must be absolute")
            candidates.append(part_name)
    distinct = tuple(dict.fromkeys(candidates))
    if len(distinct) > 1:
        raise ValueError("DOCX package exposes multiple main document parts")
    if distinct:
        part_uri = distinct[0]
        if part_uri.lstrip("/") not in members:
            raise ValueError("DOCX main document part is missing from the package")
        return part_uri
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
        if not isinstance(element.tag, str):
            continue
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


def _validate_part_root(root: Any, kind: str) -> None:
    expected_name = _PART_ROOT_NAMES.get(kind)
    tag = root.tag
    if not isinstance(tag, str) or not tag.startswith("{") or "}" not in tag:
        raise ValueError("DOCX WordprocessingML root namespace is invalid")
    namespace, local_name = tag[1:].split("}", 1)
    if (
        expected_name is None
        or local_name != expected_name
        or namespace not in _WORDPROCESSING_NAMESPACES
    ):
        raise ValueError("DOCX WordprocessingML root namespace is invalid")


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
    _validate_part_root(root, kind)
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
        if not isinstance(child.tag, str):
            continue
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
