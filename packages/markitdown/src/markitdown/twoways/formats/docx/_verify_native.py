from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from io import BytesIO
import posixpath
from zipfile import ZipFile

from ..._errors import RoundTripVerificationError
from ...ir.document import DocumentIR
from ...ir.edits import EditOperation
from ...ooxml import parse_xml_part
from .locators import (
    resolve_paragraph_element,
    resolve_picture_docpr,
    resolve_table_element,
)

_XML_SPACE = "{http://www.w3.org/XML/1998/namespace}space"


def _fail(check: str, message: str, *, expected=None, actual=None) -> None:
    raise RoundTripVerificationError(
        message,
        details={"check": check, "expected": expected, "actual": actual},
    )


def _canonical_subtree(element) -> bytes:
    from lxml import etree

    return etree.tostring(element, method="c14n", with_comments=True)


def _picture_container(docpr):
    current = docpr
    while current is not None:
        if current.tag.rsplit("}", 1)[-1] in {"inline", "anchor"}:
            return current
        current = current.getparent()
    return docpr


def _resolve_node_subtree(root, node, *, part_uri: str):
    locator = node.native_locator
    if locator is None:
        return None
    if node.kind == "text":
        return resolve_paragraph_element(root, locator, part_uri=part_uri)
    if node.kind == "image":
        return _picture_container(
            resolve_picture_docpr(root, locator, part_uri=part_uri)
        )
    if node.kind == "table":
        return resolve_table_element(root, locator, part_uri=part_uri)
    return None


def _table_cell(element, row: int, column: int):
    rows = [
        child
        for child in element
        if isinstance(getattr(child, "tag", None), str)
        and child.tag.rsplit("}", 1)[-1] == "tr"
    ]
    if row < 0 or row >= len(rows):
        return None
    cells = [
        child
        for child in rows[row]
        if isinstance(getattr(child, "tag", None), str)
        and child.tag.rsplit("}", 1)[-1] == "tc"
    ]
    if column < 0 or column >= len(cells):
        return None
    return cells[column]


def _mask_table_update_values(clone, edit: EditOperation) -> None:
    updates = edit.payload.get("cells")
    if not isinstance(updates, (list, tuple)):
        return
    for update in updates:
        if not isinstance(update, Mapping):
            continue
        row = update.get("row")
        column = update.get("column")
        if type(row) is not int or type(column) is not int:
            continue
        cell = _table_cell(clone, row, column)
        if cell is None:
            continue
        for text_node in cell.xpath('.//*[local-name()="t"]'):
            text_node.text = ""
            text_node.attrib.pop(_XML_SPACE, None)


def _normalized_target_structure(
    element,
    *,
    kind: str,
    edit_type: str,
    edit: EditOperation,
) -> bytes:
    del kind
    clone = deepcopy(element)
    if edit_type == "replace_text":
        for text_node in clone.xpath('.//*[local-name()="t"]'):
            text_node.text = ""
            text_node.attrib.pop(_XML_SPACE, None)
    elif edit_type == "set_alt_text":
        docprs = clone.xpath('.//*[local-name()="docPr"]')
        if not docprs and clone.tag.rsplit("}", 1)[-1] == "docPr":
            docprs = [clone]
        for docpr in docprs:
            docpr.set("descr", "")
    elif edit_type == "update_table_cells":
        _mask_table_update_values(clone, edit)
    return _canonical_subtree(clone)


def _roots_for_touched_parts(
    source_bytes: bytes,
    output_bytes: bytes,
    touched_parts: tuple[str, ...],
):
    roots = {}
    with ZipFile(BytesIO(source_bytes), "r") as before_zip, ZipFile(
        BytesIO(output_bytes), "r"
    ) as after_zip:
        for archive_name in touched_parts:
            part_uri = f"/{archive_name.lstrip('/')}"
            roots[part_uri] = (
                parse_xml_part(before_zip.read(archive_name)),
                parse_xml_part(after_zip.read(archive_name)),
            )
    return roots


def _verify_native_subtrees(
    document: DocumentIR,
    source_bytes: bytes,
    output_bytes: bytes,
    *,
    edits: tuple[EditOperation, ...],
    touched_parts: tuple[str, ...],
) -> None:
    roots = _roots_for_touched_parts(source_bytes, output_bytes, touched_parts)
    edited = {edit.target_node_id: edit for edit in edits if edit.target_node_id}
    changed_unrelated: list[str] = []
    target_structure_changed: list[str] = []

    for node_id, node in document.nodes.items():
        locator = node.native_locator
        if locator is None or locator.part_uri not in roots:
            continue
        before_root, after_root = roots[locator.part_uri]
        before_subtree = _resolve_node_subtree(
            before_root, node, part_uri=locator.part_uri
        )
        after_subtree = _resolve_node_subtree(
            after_root, node, part_uri=locator.part_uri
        )
        if before_subtree is None or after_subtree is None:
            continue
        edit = edited.get(node_id)
        if edit is None:
            if _canonical_subtree(before_subtree) != _canonical_subtree(after_subtree):
                changed_unrelated.append(node_id)
            continue
        before_structure = _normalized_target_structure(
            before_subtree,
            kind=node.kind,
            edit_type=edit.type,
            edit=edit,
        )
        after_structure = _normalized_target_structure(
            after_subtree,
            kind=node.kind,
            edit_type=edit.type,
            edit=edit,
        )
        if before_structure != after_structure:
            target_structure_changed.append(node_id)

    if changed_unrelated:
        _fail(
            "docx.native.unrelated_subtrees",
            "Unrelated DOCX native subtrees changed during patch.",
            expected=[],
            actual=sorted(changed_unrelated),
        )
    if target_structure_changed:
        _fail(
            "docx.native.target_structure",
            (
                "DOCX target native wrapper structure changed beyond "
                "the permitted value mutation."
            ),
            expected=[],
            actual=sorted(target_structure_changed),
        )


def _rels_member_for_part(part_uri: str) -> str:
    member = part_uri.lstrip("/")
    directory, filename = posixpath.split(member)
    return posixpath.join(directory, "_rels", f"{filename}.rels")


def _verify_relationships_and_media(
    source_bytes: bytes,
    output_bytes: bytes,
    *,
    touched_parts: tuple[str, ...],
) -> None:
    with ZipFile(BytesIO(source_bytes), "r") as before_zip, ZipFile(
        BytesIO(output_bytes), "r"
    ) as after_zip:
        before_names = set(before_zip.namelist())
        after_names = set(after_zip.namelist())
        for touched in touched_parts:
            rels_name = _rels_member_for_part(f"/{touched.lstrip('/')}")
            before = before_zip.read(rels_name) if rels_name in before_names else None
            after = after_zip.read(rels_name) if rels_name in after_names else None
            if before != after:
                _fail(
                    "docx.hyperlinks.relationships",
                    "DOCX relationships changed during text/value patch.",
                    expected="unchanged",
                    actual=rels_name,
                )
        media_names = sorted(
            name for name in before_names if name.startswith("word/media/")
        )
        if media_names != sorted(
            name for name in after_names if name.startswith("word/media/")
        ):
            _fail(
                "docx.media.unchanged",
                "DOCX media inventory changed during patch.",
            )
        changed_media = [
            name
            for name in media_names
            if before_zip.read(name) != after_zip.read(name)
        ]
        if changed_media:
            _fail(
                "docx.media.unchanged",
                "DOCX media bytes changed during text/alt-text patch.",
                expected=[],
                actual=changed_media,
            )
