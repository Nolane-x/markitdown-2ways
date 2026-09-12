from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from io import BytesIO
from typing import Iterable
from zipfile import ZipFile

from ..._errors import RoundTripVerificationError
from ..._results import FidelityEvidence, FidelityReport, FidelityStatus
from ...ir.document import DocumentIR
from ...ir.edits import EditOperation
from ...ir.nodes import TablePayload
from ...ir.semantics import node_semantic_digest, node_semantic_text
from ...ir.table_edits import table_semantic_text_after_updates
from ...ooxml import OOXMLPackageLimits, parse_xml_part
from ...ooxml.package import inspect_package_preservation
from .locators import resolve_shape_element

_XML_SPACE = "{http://www.w3.org/XML/1998/namespace}space"
_TARGET_NATIVE_EDIT_TYPES = frozenset(
    {
        "replace_text",
        "set_alt_text",
        "update_table_cells",
        "set_text_style",
        "move_resize",
    }
)


def _fail(check: str, message: str, *, expected=None, actual=None) -> None:
    raise RoundTripVerificationError(
        message,
        details={
            "check": check,
            "expected": expected,
            "actual": actual,
        },
    )


def _edited_nodes_and_ancestors(
    document: DocumentIR,
    edited_ids: set[str],
) -> set[str]:
    excluded = set(edited_ids)
    for node_id in tuple(edited_ids):
        current = document.nodes.get(node_id)
        while current is not None and current.parent_id is not None:
            excluded.add(current.parent_id)
            current = document.nodes.get(current.parent_id)
    return excluded


def _canonical_subtree(element) -> bytes:
    from lxml import etree

    return etree.tostring(element, method="c14n", with_comments=True)


def _local_name(element) -> str | None:
    tag = getattr(element, "tag", None)
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else None


def _direct_children(element, name: str) -> list[object]:
    return [child for child in element if _local_name(child) == name]


def _mask_text_update(shape_element) -> bool:
    text_nodes = list(shape_element.xpath('.//*[local-name()="t"]'))
    if not text_nodes:
        return False
    for text_node in text_nodes:
        text_node.text = ""
        text_node.attrib.pop(_XML_SPACE, None)
    return True


def _mask_alt_text_update(shape_element) -> bool:
    c_nv_prs = list(shape_element.xpath('.//*[local-name()="cNvPr"]'))
    if len(c_nv_prs) != 1:
        return False
    c_nv_prs[0].attrib.pop("descr", None)
    return True


def _table_cell(shape_element, row: int, column: int):
    tables = [item for item in shape_element.iter() if _local_name(item) == "tbl"]
    if len(tables) != 1:
        return None
    rows = [child for child in tables[0] if _local_name(child) == "tr"]
    if row < 0 or row >= len(rows):
        return None
    cells = [child for child in rows[row] if _local_name(child) == "tc"]
    if column < 0 or column >= len(cells):
        return None
    return cells[column]


def _mask_table_update_values(shape_element, edit: EditOperation) -> bool:
    updates = edit.payload.get("cells")
    if not isinstance(updates, (list, tuple)):
        return False
    for update in updates:
        if not isinstance(update, Mapping):
            return False
        row = update.get("row")
        column = update.get("column")
        if type(row) is not int or type(column) is not int:
            return False
        cell = _table_cell(shape_element, row, column)
        if cell is None:
            return False
        for text_node in cell.xpath('.//*[local-name()="t"]'):
            text_node.text = ""
            text_node.attrib.pop(_XML_SPACE, None)
    return True


def _native_runs(shape_element) -> list[object]:
    return list(shape_element.xpath('.//*[local-name()="p"]/*[local-name()="r"]'))


def _strip_permitted_latin_style(rpr) -> bool:
    latin = _direct_children(rpr, "latin")
    if len(latin) > 1:
        return False
    if not latin:
        return True
    target = latin[0]
    target.attrib.pop("typeface", None)
    if not target.attrib and len(target) == 0:
        rpr.remove(target)
    return True


def _strip_permitted_rgb_style(rpr) -> bool:
    fills = _direct_children(rpr, "solidFill")
    if len(fills) > 1:
        return False
    if not fills:
        return True
    fill = fills[0]
    colors = _direct_children(fill, "srgbClr")
    if len(colors) != 1 or len(fill) != 1:
        return False
    color = colors[0]
    color.attrib.pop("val", None)
    if not color.attrib and len(color) == 0:
        fill.remove(color)
    if not fill.attrib and len(fill) == 0:
        rpr.remove(fill)
    return True


def _mask_style_update(shape_element, edit: EditOperation) -> bool:
    run_index = edit.payload.get("run_index")
    if type(run_index) is not int:
        return False
    runs = _native_runs(shape_element)
    if run_index < 0 or run_index >= len(runs):
        return False
    run = runs[run_index]
    rpr_nodes = _direct_children(run, "rPr")
    if len(rpr_nodes) > 1:
        return False
    if not rpr_nodes:
        return True
    rpr = rpr_nodes[0]
    for name in ("b", "i", "u", "sz"):
        rpr.attrib.pop(name, None)
    if not _strip_permitted_latin_style(rpr):
        return False
    if not _strip_permitted_rgb_style(rpr):
        return False
    if not rpr.attrib and len(rpr) == 0:
        run.remove(rpr)
    return True


def _mask_geometry_update(shape_element) -> bool:
    xfrms = [item for item in shape_element.iter() if _local_name(item) == "xfrm"]
    if len(xfrms) != 1:
        return False
    xfrm = xfrms[0]
    offsets = _direct_children(xfrm, "off")
    extents = _direct_children(xfrm, "ext")
    if len(offsets) != 1 or len(extents) != 1:
        return False
    offsets[0].set("x", "0")
    offsets[0].set("y", "0")
    extents[0].set("cx", "0")
    extents[0].set("cy", "0")
    return True


def _normalize_target(shape_element, edits: tuple[EditOperation, ...]):
    clone = deepcopy(shape_element)
    for edit in edits:
        if edit.type == "replace_text":
            if not _mask_text_update(clone):
                return None
        elif edit.type == "set_alt_text":
            if not _mask_alt_text_update(clone):
                return None
        elif edit.type == "update_table_cells":
            if not _mask_table_update_values(clone, edit):
                return None
        elif edit.type == "set_text_style":
            if not _mask_style_update(clone, edit):
                return None
        elif edit.type == "move_resize":
            if not _mask_geometry_update(clone):
                return None
    return clone


def _roots_for_touched_parts(
    source_bytes: bytes,
    output_bytes: bytes,
    touched_parts: tuple[str, ...],
) -> dict[str, tuple[object, object]]:
    roots: dict[str, tuple[object, object]] = {}
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


def _verify_edited_targets(
    document: DocumentIR,
    source_bytes: bytes,
    output_bytes: bytes,
    *,
    edits: tuple[EditOperation, ...],
    touched_parts: tuple[str, ...],
) -> tuple[str, ...]:
    edits_by_target: dict[str, list[EditOperation]] = {}
    for edit in edits:
        if edit.type not in _TARGET_NATIVE_EDIT_TYPES or edit.target_node_id is None:
            continue
        edits_by_target.setdefault(edit.target_node_id, []).append(edit)
    if not edits_by_target:
        return ()

    roots = _roots_for_touched_parts(source_bytes, output_bytes, touched_parts)
    changed: list[str] = []
    verified: list[str] = []
    for target_node_id in sorted(edits_by_target):
        node = document.nodes.get(target_node_id)
        if node is None or node.native_locator is None:
            changed.append(target_node_id)
            continue
        part_uri = node.native_locator.part_uri
        if not part_uri or part_uri not in roots:
            changed.append(target_node_id)
            continue
        before_root, after_root = roots[part_uri]
        before_shape = resolve_shape_element(
            before_root,
            node.native_locator,
            part_uri=part_uri,
            strict=True,
        )
        after_shape = resolve_shape_element(
            after_root,
            node.native_locator,
            part_uri=part_uri,
            strict=True,
        )
        target_edits = tuple(edits_by_target[target_node_id])
        before_normalized = _normalize_target(before_shape, target_edits)
        after_normalized = _normalize_target(after_shape, target_edits)
        if (
            before_normalized is None
            or after_normalized is None
            or _canonical_subtree(before_normalized)
            != _canonical_subtree(after_normalized)
        ):
            changed.append(target_node_id)
            continue
        verified.append(target_node_id)

    if changed:
        _fail(
            "native.target_structure",
            "PPTX target native structure changed beyond requested edit fields.",
            expected=[],
            actual=sorted(changed),
        )
    return tuple(verified)


def _verify_unrelated_native_subtrees(
    document: DocumentIR,
    source_bytes: bytes,
    output_bytes: bytes,
    *,
    touched_parts: tuple[str, ...],
    edited_ids: set[str],
) -> None:
    touched_uris = {f"/{name.lstrip('/')}" for name in touched_parts}
    if not touched_uris:
        return
    excluded = _edited_nodes_and_ancestors(document, edited_ids)
    roots = _roots_for_touched_parts(source_bytes, output_bytes, touched_parts)

    changed: list[str] = []
    for node_id, node in document.nodes.items():
        locator = node.native_locator
        if (
            node_id in excluded
            or locator is None
            or locator.part_uri not in touched_uris
        ):
            continue
        before_root, after_root = roots[locator.part_uri]
        before_shape = resolve_shape_element(
            before_root,
            locator,
            part_uri=locator.part_uri,
            strict=True,
        )
        after_shape = resolve_shape_element(
            after_root,
            locator,
            part_uri=locator.part_uri,
            strict=True,
        )
        if _canonical_subtree(before_shape) != _canonical_subtree(after_shape):
            changed.append(node_id)

    if changed:
        _fail(
            "native.unrelated_subtrees",
            "Unrelated PPTX native shape subtrees changed during patch.",
            expected=[],
            actual=sorted(changed),
        )


def _expected_edit_value(original_document: DocumentIR, edit: EditOperation) -> object:
    if edit.type == "replace_text":
        return edit.payload.get("text")
    if edit.type == "set_alt_text":
        return edit.payload.get("alt_text")
    if (
        edit.type in {"set_text_style", "move_resize"}
        and edit.target_node_id is not None
    ):
        source_node = original_document.nodes.get(edit.target_node_id)
        if source_node is not None:
            return node_semantic_text(source_node)
    if edit.type == "update_table_cells" and edit.target_node_id is not None:
        source_node = original_document.nodes.get(edit.target_node_id)
        if source_node is not None and isinstance(source_node.payload, TablePayload):
            return table_semantic_text_after_updates(
                source_node.payload,
                edit.payload.get("cells"),
                format_label="PPTX",
            )
    return None


def verify_pptx_output(
    original_document: DocumentIR,
    source_bytes: bytes,
    output_bytes: bytes,
    *,
    edits: Iterable[EditOperation],
    touched_parts: tuple[str, ...],
    limits: OOXMLPackageLimits,
) -> FidelityReport:
    preservation = inspect_package_preservation(
        source_bytes,
        output_bytes,
        touched_parts=touched_parts,
        limits=limits,
    )
    if not preservation.inventory_matches:
        _fail(
            "package.inventory",
            "PPTX package inventory changed during patch.",
            expected=preservation.before_names,
            actual=preservation.after_names,
        )
    if preservation.changed_untouched:
        _fail(
            "package.untouched_members",
            "Untouched PPTX package members changed during patch.",
            expected=[],
            actual=list(preservation.changed_untouched),
        )

    try:
        from pptx import Presentation

        Presentation(BytesIO(output_bytes))
    except Exception as exc:
        raise RoundTripVerificationError(
            "Patched PPTX cannot be reopened by python-pptx.",
            details={"check": "pptx.reopen", "error": repr(exc)},
        ) from exc

    from .reader import read_pptx_ir

    output_document = read_pptx_ir(BytesIO(output_bytes))
    edit_list = tuple(edits)
    edited_ids = {edit.target_node_id for edit in edit_list if edit.target_node_id}

    for edit in edit_list:
        if (
            edit.target_node_id is None
            or edit.target_node_id not in output_document.nodes
        ):
            _fail(
                "semantic.target_identity",
                "Edited PPTX node identity did not survive round trip.",
                expected=edit.target_node_id,
                actual=None,
            )
        output_node = output_document.nodes[edit.target_node_id]
        expected_value = _expected_edit_value(original_document, edit)
        actual_value = node_semantic_text(output_node)
        if actual_value != expected_value:
            _fail(
                "semantic.readback",
                "Patched PPTX semantic value did not read back correctly.",
                expected=expected_value,
                actual=actual_value,
            )

    target_native_affected = _verify_edited_targets(
        original_document,
        source_bytes,
        output_bytes,
        edits=edit_list,
        touched_parts=touched_parts,
    )
    _verify_unrelated_native_subtrees(
        original_document,
        source_bytes,
        output_bytes,
        touched_parts=touched_parts,
        edited_ids=edited_ids,
    )

    from .geometry import verify_geometry_readback
    from .style import verify_text_style_readback

    style_affected = verify_text_style_readback(
        original_document,
        output_document,
        edit_list,
    )
    geometry_affected = verify_geometry_readback(
        original_document,
        output_document,
        edit_list,
    )

    changed_unrelated: list[str] = []
    for node_id, node in original_document.nodes.items():
        if node_id in edited_ids:
            continue
        output_node = output_document.nodes.get(node_id)
        if output_node is None or node_semantic_digest(
            output_node
        ) != node_semantic_digest(node):
            changed_unrelated.append(node_id)
    if changed_unrelated:
        _fail(
            "semantic.unrelated_nodes",
            "Unrelated PPTX semantic nodes changed during patch.",
            expected=[],
            actual=changed_unrelated,
        )

    evidence: tuple[FidelityEvidence, ...] = (
        FidelityEvidence(
            check_code="package.inventory",
            status=FidelityStatus.PASSED,
            description="PPTX package member inventory is unchanged.",
        ),
        FidelityEvidence(
            check_code="package.untouched_members",
            status=FidelityStatus.PASSED,
            description="Untouched package members preserve identical uncompressed bytes.",
        ),
        FidelityEvidence(
            check_code="pptx.reopen",
            status=FidelityStatus.PASSED,
            description="Patched PPTX reopens successfully with python-pptx.",
        ),
        FidelityEvidence(
            check_code="semantic.readback",
            status=FidelityStatus.PASSED,
            description="Requested edits read back with the expected semantic values.",
            affected_node_ids=tuple(sorted(edited_ids)),
        ),
        FidelityEvidence(
            check_code="native.target_structure",
            status=FidelityStatus.PASSED,
            description=(
                "Edited PPTX targets preserve native structure outside explicitly "
                "authorized text, alt-text, table, direct-style, or geometry fields."
            ),
            affected_node_ids=target_native_affected,
        ),
        FidelityEvidence(
            check_code="native.unrelated_subtrees",
            status=FidelityStatus.PASSED,
            description="Unedited native shape subtrees in touched parts remain canonically identical.",
        ),
        FidelityEvidence(
            check_code="semantic.unrelated_nodes",
            status=FidelityStatus.PASSED,
            description="Unedited semantic nodes retain identical semantic digests.",
        ),
    )
    if style_affected:
        evidence += (
            FidelityEvidence(
                check_code="pptx.style.readback",
                status=FidelityStatus.PASSED,
                description=(
                    "Requested PPTX direct run styles read back exactly while "
                    "semantic text remains unchanged."
                ),
                affected_node_ids=style_affected,
            ),
        )
    if geometry_affected:
        evidence += (
            FidelityEvidence(
                check_code="pptx.geometry.readback",
                status=FidelityStatus.PASSED,
                description=(
                    "Requested PPTX slide-shape geometry reads back exactly with "
                    "semantic content unchanged."
                ),
                affected_node_ids=geometry_affected,
            ),
        )
    return FidelityReport(claimed_tier="high", evidence=evidence)
