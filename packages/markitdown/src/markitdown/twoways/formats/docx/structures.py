from __future__ import annotations

from hashlib import sha256
import mimetypes
import posixpath
from typing import Any, Mapping

from ..._errors import UnsupportedEditError
from ...ir.document import Diagnostic
from ...ir.nodes import ImagePayload, Node, TableCell, TablePayload, TextPayload
from ...ir.provenance import NativeLocator, Provenance
from ...ir.resources import Resource
from .locators import paragraph_locator, picture_locator, stable_docx_node_id
from .relationships import DocxRelationship
from .text import extract_paragraph_payload, paragraph_patch_compatible

_R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _provenance(*, canvas_index: int, part_uri: str) -> tuple[Provenance, ...]:
    return (
        Provenance(
            source_format="docx",
            canvas_index=canvas_index,
            part_uri=part_uri,
            extraction_method="wordprocessingml",
        ),
    )


def build_paragraph_node(
    paragraph_element: Any,
    *,
    part_uri: str,
    canvas_id: str,
    canvas_index: int,
    paragraph_index: int,
    path: str,
    order: int,
) -> Node:
    locator = paragraph_locator(
        part_uri,
        paragraph_index=paragraph_index,
        path=path,
    )
    compatible = paragraph_patch_compatible(paragraph_element)
    try:
        payload = extract_paragraph_payload(paragraph_element, locator)
    except UnsupportedEditError:
        payload = TextPayload(
            text="".join(paragraph_element.xpath('.//*[local-name()="t"]/text()')),
        )
    return Node(
        node_id=stable_docx_node_id(locator, "text"),
        kind="text",
        canvas_id=canvas_id,
        order=order,
        native_locator=locator,
        provenance=_provenance(canvas_index=canvas_index, part_uri=part_uri),
        payload=payload,
        metadata={
            "docx:patch_text_compatible": compatible,
            "docx:patch_capabilities": ("replace_text",) if compatible else (),
        },
    )


def build_table_node(
    table_element: Any,
    *,
    part_uri: str,
    canvas_id: str,
    canvas_index: int,
    table_index: int,
    path: str,
    order: int,
) -> Node:
    rows = table_element.xpath('./*[local-name()="tr"]')
    cells: list[TableCell] = []
    max_columns = 0
    for row_index, row in enumerate(rows):
        row_cells = row.xpath('./*[local-name()="tc"]')
        max_columns = max(max_columns, len(row_cells))
        for column_index, cell in enumerate(row_cells):
            paragraphs = cell.xpath('./*[local-name()="p"]')
            text = "\n".join(
                "".join(paragraph.xpath('.//*[local-name()="t"]/text()'))
                for paragraph in paragraphs
            )
            cells.append(TableCell(row=row_index, column=column_index, text=text))
    locator = NativeLocator(
        backend="docx-ooxml",
        part_uri=part_uri,
        object_id=f"table:{table_index}",
        path=path,
        attributes={"table_index": table_index},
    )
    return Node(
        node_id=stable_docx_node_id(locator, "table"),
        kind="table",
        semantic_role="table",
        canvas_id=canvas_id,
        order=order,
        native_locator=locator,
        provenance=_provenance(canvas_index=canvas_index, part_uri=part_uri),
        payload=TablePayload(rows=len(rows), columns=max_columns, cells=tuple(cells)),
        metadata={"docx:patch_capabilities": ()},
    )


def _picture_relationship_id(docpr: Any) -> str | None:
    parent = docpr.getparent()
    while parent is not None and _local_name(parent.tag) not in {"inline", "anchor"}:
        parent = parent.getparent()
    if parent is None:
        return None
    blips = parent.xpath('.//*[local-name()="blip"]')
    if len(blips) != 1:
        return None
    return blips[0].get(f"{{{_R_NS}}}embed")


def build_picture_nodes(
    paragraph_element: Any,
    *,
    part_uri: str,
    canvas_id: str,
    canvas_index: int,
    paragraph_path: str,
    order_start: int,
    relationships: Mapping[str, DocxRelationship],
    package_members: Mapping[str, bytes],
) -> tuple[list[Node], dict[str, Resource], list[Diagnostic]]:
    nodes: list[Node] = []
    resources: dict[str, Resource] = {}
    diagnostics: list[Diagnostic] = []
    for picture_index, docpr in enumerate(paragraph_element.xpath('.//*[local-name()="docPr"]')):
        docpr_id = docpr.get("id")
        relationship_id = _picture_relationship_id(docpr)
        relationship = relationships.get(relationship_id) if relationship_id else None
        if not docpr_id or relationship is None or relationship.external or not relationship.resolved_target:
            diagnostics.append(
                Diagnostic(
                    code="docx.picture.unresolved",
                    severity="warning",
                    message="DOCX picture could not be resolved to one package resource.",
                    canvas_id=canvas_id,
                    details={"part_uri": part_uri, "docpr_id": docpr_id},
                )
            )
            continue
        member_name = relationship.resolved_target.lstrip("/")
        content = package_members.get(member_name)
        if content is None:
            diagnostics.append(
                Diagnostic(
                    code="docx.picture.resource_missing",
                    severity="warning",
                    message="DOCX picture relationship target is missing from the package.",
                    canvas_id=canvas_id,
                    details={"target": relationship.resolved_target},
                )
            )
            continue
        digest = sha256(content).hexdigest()
        resource_id = f"docx-image-{digest[:24]}"
        content_type = mimetypes.guess_type(member_name)[0]
        resources[resource_id] = Resource(
            resource_id=resource_id,
            sha256=digest,
            content_type=content_type,
            filename=posixpath.basename(member_name),
            size_bytes=len(content),
            storage_ref=relationship.resolved_target,
            metadata={"docx:relationship_id": relationship_id},
        )
        locator = picture_locator(
            part_uri,
            docpr_id=docpr_id,
            relationship_id=relationship_id,
            path=(
                f"{paragraph_path}//*[local-name()='docPr' and @id='{docpr_id}']"
            ),
        )
        node = Node(
            node_id=stable_docx_node_id(locator, "image"),
            kind="image",
            semantic_role="image",
            canvas_id=canvas_id,
            order=order_start + picture_index,
            native_locator=locator,
            provenance=_provenance(canvas_index=canvas_index, part_uri=part_uri),
            payload=ImagePayload(
                resource_id=resource_id,
                alt_text=docpr.get("descr") or None,
            ),
            metadata={"docx:patch_capabilities": ("set_alt_text",)},
        )
        nodes.append(node)
    return nodes, resources, diagnostics
