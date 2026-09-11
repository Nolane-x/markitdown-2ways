from __future__ import annotations

from collections.abc import Mapping, Sequence
from math import isfinite
from typing import Any

from ..._errors import PatchPreconditionError, UnsupportedEditError
from ...ooxml import parse_xml_part, serialize_xml_part
from .cells import indices_to_a1, read_worksheet_grid


_XML_NS = "http://www.w3.org/XML/1998/namespace"


def _same_typed(left: object, right: object) -> bool:
    return type(left) is type(right) and left == right


def _valid_scalar(value: object) -> bool:
    if value is None or type(value) in {str, int, bool}:
        return True
    return type(value) is float and isfinite(value)


def _direct_cell_elements(root: Any, namespace: str) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for element in root.iter(f"{{{namespace}}}c"):
        address = element.get("r")
        if not address:
            raise ValueError("worksheet cell is missing r")
        if address in result:
            raise ValueError("duplicate worksheet cell reference")
        result[address] = element
    return result


def _remove_value_children(cell: Any, namespace: str) -> int:
    removable = {f"{{{namespace}}}v", f"{{{namespace}}}is"}
    ext_list_tag = f"{{{namespace}}}extLst"
    insertion_index: int | None = None
    children = tuple(cell)
    for index, child in enumerate(children):
        if child.tag in removable:
            if insertion_index is None:
                insertion_index = index
        elif insertion_index is None and child.tag == ext_list_tag:
            insertion_index = index
    for child in children:
        if child.tag in removable:
            cell.remove(child)
    if insertion_index is None:
        return len(cell)
    return min(insertion_index, len(cell))


def _append_value(
    cell: Any,
    namespace: str,
    value: object,
    *,
    insertion_index: int,
) -> None:
    if value is None:
        cell.attrib.pop("t", None)
        return
    if type(value) is str:
        cell.set("t", "inlineStr")
        inline = cell.makeelement(f"{{{namespace}}}is")
        text = cell.makeelement(f"{{{namespace}}}t")
        text.text = value
        if value != value.strip():
            text.set(f"{{{_XML_NS}}}space", "preserve")
        inline.append(text)
        cell.insert(insertion_index, inline)
        return
    value_element = cell.makeelement(f"{{{namespace}}}v")
    if type(value) is bool:
        cell.set("t", "b")
        value_element.text = "1" if value else "0"
    elif type(value) is int:
        cell.set("t", "n")
        value_element.text = str(value)
    elif type(value) is float:
        cell.set("t", "n")
        value_element.text = repr(value)
    else:
        raise UnsupportedEditError(
            "XLSX patch value type is not supported.",
            details={"reason": "invalid_cell_value"},
        )
    cell.insert(insertion_index, value_element)


def patch_worksheet_cells(
    worksheet_xml: bytes,
    *,
    shared_strings: tuple[str, ...] = (),
    rich_shared_string_indexes: frozenset[int] = frozenset(),
    updates: Sequence[Mapping[str, object]],
) -> bytes:
    root = parse_xml_part(worksheet_xml)
    grid = read_worksheet_grid(
        root,
        shared_strings=shared_strings,
        rich_shared_string_indexes=rich_shared_string_indexes,
    )
    namespace = root.tag[1:].split("}", 1)[0]
    native = {(cell.row, cell.column): cell for cell in grid.cells}
    elements = _direct_cell_elements(root, namespace)
    seen: set[tuple[int, int]] = set()
    prepared: list[tuple[Any, object]] = []

    if not isinstance(updates, (list, tuple)) or not updates:
        raise UnsupportedEditError(
            "XLSX worksheet patch requires a non-empty update sequence.",
            details={"reason": "invalid_edit_payload"},
        )
    for raw in updates:
        if not isinstance(raw, Mapping):
            raise UnsupportedEditError(
                "XLSX worksheet update must be a mapping.",
                details={"reason": "invalid_edit_payload"},
            )
        row = raw.get("row")
        column = raw.get("column")
        old_value = raw.get("old_value")
        new_value = raw.get("value")
        if type(row) is not int or type(column) is not int:
            raise UnsupportedEditError(
                "XLSX worksheet coordinates must be integers.",
                details={"reason": "invalid_edit_payload"},
            )
        coordinate = (row, column)
        if coordinate in seen:
            raise UnsupportedEditError(
                "XLSX worksheet patch contains duplicate coordinates.",
                details={"reason": "duplicate_cell_coordinate"},
            )
        seen.add(coordinate)
        cell = native.get(coordinate)
        if cell is None:
            raise UnsupportedEditError(
                "XLSX worksheet patch requires an existing native cell.",
                details={"reason": "missing_native_cell"},
            )
        if cell.capability.state.value != "writable":
            raise UnsupportedEditError(
                "XLSX worksheet target cell is read-only.",
                details={
                    "reason": cell.capability.reason_code
                    or "unsupported_cell_structure",
                    "address": cell.address,
                },
            )
        if not _same_typed(old_value, cell.value):
            raise PatchPreconditionError(
                "XLSX worksheet old_value does not match native source.",
                details={
                    "reason": "cell_old_value_mismatch",
                    "address": cell.address,
                    "expected": cell.value,
                    "actual": old_value,
                },
            )
        if not _valid_scalar(new_value):
            raise UnsupportedEditError(
                "XLSX worksheet target value is not a supported finite scalar.",
                details={"reason": "invalid_cell_value", "address": cell.address},
            )
        if _same_typed(old_value, new_value):
            raise UnsupportedEditError(
                "XLSX worksheet update must change the typed value.",
                details={"reason": "no_op_cell_update", "address": cell.address},
            )
        address = indices_to_a1(row, column)
        element = elements.get(address)
        if element is None:
            raise UnsupportedEditError(
                "XLSX worksheet target has no authoritative cell element.",
                details={"reason": "missing_native_cell", "address": address},
            )
        prepared.append((element, new_value))

    for element, new_value in prepared:
        insertion_index = _remove_value_children(element, namespace)
        _append_value(
            element,
            namespace,
            new_value,
            insertion_index=insertion_index,
        )
    return serialize_xml_part(root)
