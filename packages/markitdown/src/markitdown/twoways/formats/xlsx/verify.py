from __future__ import annotations

from collections.abc import Iterable, Mapping
from copy import deepcopy
from io import BytesIO
from typing import Any
from zipfile import ZipFile

from ..._errors import RoundTripVerificationError
from ..._results import FidelityEvidence, FidelityReport, FidelityStatus
from ...ir.document import DocumentIR
from ...ir.edits import EditOperation
from ...ir.nodes import TablePayload
from ...ir.sheet_edits import validate_sheet_cell_updates
from ...ooxml import OOXMLPackageLimits, parse_xml_part
from ...ooxml.package import inspect_package_preservation
from .reader import read_xlsx_ir


def _fail(
    check: str, message: str, *, expected: object = None, actual: object = None
) -> None:
    raise RoundTripVerificationError(
        message,
        details={"check": check, "expected": expected, "actual": actual},
    )


def _typed_values(payload: TablePayload) -> dict[tuple[int, int], object]:
    values: dict[tuple[int, int], object] = {}
    for cell in payload.cells:
        if "xlsx.typed_value" not in cell.metadata:
            _fail(
                "semantic.typed_values",
                "XLSX verification requires authoritative typed cell values.",
                actual=(cell.row, cell.column),
            )
        values[(cell.row, cell.column)] = cell.metadata["xlsx.typed_value"]
    return values


def _sheet_node_by_index(document: DocumentIR, index: int):
    for node in document.nodes.values():
        if node.metadata.get("xlsx.sheet_index") == index:
            return node
    return None


def _group_updates(
    document: DocumentIR,
    edits: tuple[EditOperation, ...],
) -> dict[int, tuple[dict[str, object], ...]]:
    grouped: dict[int, list[dict[str, object]]] = {}
    for edit in edits:
        if edit.target_node_id is None:
            _fail("semantic.target_identity", "XLSX edit target is missing.")
        node = document.nodes.get(edit.target_node_id)
        if node is None or not isinstance(node.payload, TablePayload):
            _fail(
                "semantic.target_identity",
                "XLSX edit target is not a source worksheet node.",
                expected=edit.target_node_id,
            )
        sheet_index = node.metadata.get("xlsx.sheet_index")
        if type(sheet_index) is not int:
            _fail(
                "semantic.target_identity",
                "XLSX worksheet target is missing a deterministic sheet index.",
                expected=edit.target_node_id,
            )
        updates = validate_sheet_cell_updates(node.payload, edit.payload.get("cells"))
        grouped.setdefault(sheet_index, []).extend(updates)

    result: dict[int, tuple[dict[str, object], ...]] = {}
    for sheet_index, raw_updates in grouped.items():
        node = _sheet_node_by_index(document, sheet_index)
        assert node is not None and isinstance(node.payload, TablePayload)
        result[sheet_index] = validate_sheet_cell_updates(node.payload, raw_updates)
    return result


def _canonical_xml(root: Any) -> bytes:
    from lxml import etree

    return etree.tostring(root, method="c14n", with_comments=True)


def _normalized_worksheet(
    xml_bytes: bytes, updates: tuple[dict[str, object], ...]
) -> bytes:
    root = deepcopy(parse_xml_part(xml_bytes))
    tag = getattr(root, "tag", None)
    if not isinstance(tag, str) or not tag.startswith("{") or "}" not in tag:
        _fail("native.worksheet_structure", "XLSX worksheet namespace is invalid.")
    namespace = tag[1:].split("}", 1)[0]
    requested = {(int(update["row"]), int(update["column"])) for update in updates}
    for cell in root.iter(f"{{{namespace}}}c"):
        address = cell.get("r")
        if not address:
            continue
        from .cells import a1_to_indices

        coordinate = a1_to_indices(address)
        if coordinate not in requested:
            continue
        cell.attrib.pop("t", None)
        for child in tuple(cell):
            if child.tag in {f"{{{namespace}}}v", f"{{{namespace}}}is"}:
                cell.remove(child)
    return _canonical_xml(root)


def _verify_touched_native_structure(
    source_bytes: bytes,
    output_bytes: bytes,
    document: DocumentIR,
    grouped: Mapping[int, tuple[dict[str, object], ...]],
) -> None:
    with ZipFile(BytesIO(source_bytes), "r") as before, ZipFile(
        BytesIO(output_bytes), "r"
    ) as after:
        for sheet_index, updates in grouped.items():
            node = _sheet_node_by_index(document, sheet_index)
            if (
                node is None
                or node.native_locator is None
                or not node.native_locator.part_uri
            ):
                _fail(
                    "native.worksheet_structure",
                    "XLSX worksheet target lost native part authority.",
                    expected=sheet_index,
                )
            member = node.native_locator.part_uri.lstrip("/")
            try:
                before_xml = before.read(member)
                after_xml = after.read(member)
            except KeyError as exc:
                raise RoundTripVerificationError(
                    "XLSX worksheet part disappeared during patch.",
                    details={"check": "native.worksheet_structure", "member": member},
                ) from exc
            if _normalized_worksheet(before_xml, updates) != _normalized_worksheet(
                after_xml, updates
            ):
                _fail(
                    "native.worksheet_structure",
                    "XLSX worksheet changed outside requested cell values.",
                    expected=member,
                    actual=member,
                )


def verify_xlsx_output(
    original_document: DocumentIR,
    source_bytes: bytes,
    output_bytes: bytes,
    *,
    edits: Iterable[EditOperation],
    touched_parts: tuple[str, ...],
    limits: OOXMLPackageLimits,
) -> FidelityReport:
    edit_list = tuple(edits)
    grouped = _group_updates(original_document, edit_list)
    preservation = inspect_package_preservation(
        source_bytes,
        output_bytes,
        touched_parts=touched_parts,
        limits=limits,
    )
    if not preservation.inventory_matches:
        _fail(
            "package.inventory",
            "XLSX package inventory changed during sparse patch.",
            expected=preservation.before_names,
            actual=preservation.after_names,
        )
    if preservation.changed_untouched:
        _fail(
            "package.untouched_members",
            "Untouched XLSX package members changed during patch.",
            expected=[],
            actual=list(preservation.changed_untouched),
        )

    output_document = read_xlsx_ir(BytesIO(output_bytes))
    if len(output_document.canvases) != len(original_document.canvases):
        _fail(
            "semantic.sheet_inventory",
            "XLSX worksheet inventory changed during patch.",
            expected=len(original_document.canvases),
            actual=len(output_document.canvases),
        )

    for sheet_index, original_canvas in enumerate(original_document.canvases):
        output_canvas = output_document.canvases[sheet_index]
        if output_canvas.name != original_canvas.name:
            _fail(
                "semantic.sheet_inventory",
                "XLSX worksheet ordering or names changed during patch.",
                expected=original_canvas.name,
                actual=output_canvas.name,
            )
        original_node = _sheet_node_by_index(original_document, sheet_index)
        output_node = _sheet_node_by_index(output_document, sheet_index)
        if (
            original_node is None
            or output_node is None
            or not isinstance(original_node.payload, TablePayload)
            or not isinstance(output_node.payload, TablePayload)
        ):
            _fail(
                "semantic.sheet_identity",
                "XLSX worksheet semantic node did not survive round trip.",
                expected=sheet_index,
            )
        if (
            output_node.payload.rows != original_node.payload.rows
            or output_node.payload.columns != original_node.payload.columns
        ):
            _fail(
                "semantic.sheet_shape",
                "XLSX worksheet grid shape changed during patch.",
                expected=(original_node.payload.rows, original_node.payload.columns),
                actual=(output_node.payload.rows, output_node.payload.columns),
            )

        expected = _typed_values(original_node.payload)
        for update in grouped.get(sheet_index, ()):
            expected[(int(update["row"]), int(update["column"]))] = update["value"]
        actual = _typed_values(output_node.payload)
        if actual != expected:
            _fail(
                "semantic.readback",
                "Patched XLSX typed values did not read back exactly.",
                expected=expected,
                actual=actual,
            )

    _verify_touched_native_structure(
        source_bytes,
        output_bytes,
        original_document,
        grouped,
    )

    affected = tuple(
        sorted(
            edit.target_node_id for edit in edit_list if edit.target_node_id is not None
        )
    )
    return FidelityReport(
        claimed_tier="high",
        evidence=(
            FidelityEvidence(
                check_code="package.inventory",
                status=FidelityStatus.PASSED,
                description="XLSX package member inventory is unchanged.",
            ),
            FidelityEvidence(
                check_code="package.untouched_members",
                status=FidelityStatus.PASSED,
                description="Untouched XLSX package members preserve identical bytes.",
            ),
            FidelityEvidence(
                check_code="semantic.readback",
                status=FidelityStatus.PASSED,
                description="Requested XLSX typed cell values read back exactly.",
                affected_node_ids=affected,
            ),
            FidelityEvidence(
                check_code="native.worksheet_structure",
                status=FidelityStatus.PASSED,
                description="Touched worksheets preserve native XML outside authorized cell values.",
                affected_node_ids=affected,
            ),
        ),
    )
