from __future__ import annotations

from math import isfinite
import re
from typing import Any

from ...capabilities import CapabilityDecision, CapabilityState
from .model import (
    SPREADSHEETML_NAMESPACES,
    XlsxCell,
    XlsxWorksheetGrid,
)


_A1_RE = re.compile(r"^([A-Z]{1,3})([1-9][0-9]{0,6})$")
_MAX_ROWS = 1_048_576
_MAX_COLUMNS = 16_384


def _local_name(tag: object) -> str | None:
    if not isinstance(tag, str):
        return None
    return tag.rsplit("}", 1)[-1]


def _root_namespace(root: Any, expected_local: str) -> str:
    tag = getattr(root, "tag", None)
    if not isinstance(tag, str) or not tag.startswith("{") or "}" not in tag:
        raise ValueError("SpreadsheetML root namespace is invalid")
    namespace, local = tag[1:].split("}", 1)
    if namespace not in SPREADSHEETML_NAMESPACES or local != expected_local:
        raise ValueError("SpreadsheetML root namespace is invalid")
    return namespace


def a1_to_indices(address: str) -> tuple[int, int]:
    if not isinstance(address, str):
        raise ValueError("A1 address must be a string")
    match = _A1_RE.fullmatch(address)
    if match is None:
        raise ValueError("invalid A1 cell address")
    letters, row_text = match.groups()
    column = 0
    for letter in letters:
        column = column * 26 + (ord(letter) - ord("A") + 1)
    row = int(row_text)
    if column < 1 or column > _MAX_COLUMNS or row < 1 or row > _MAX_ROWS:
        raise ValueError("A1 cell address is outside XLSX bounds")
    return row - 1, column - 1


def indices_to_a1(row: int, column: int) -> str:
    if type(row) is not int or type(column) is not int:
        raise ValueError("row and column must be integers")
    if row < 0 or row >= _MAX_ROWS or column < 0 or column >= _MAX_COLUMNS:
        raise ValueError("cell coordinate is outside XLSX bounds")
    value = column + 1
    letters = ""
    while value:
        value, remainder = divmod(value - 1, 26)
        letters = chr(ord("A") + remainder) + letters
    return f"{letters}{row + 1}"


def _descendant_text(container: Any, namespace: str) -> str:
    values: list[str] = []
    for element in container.iter():
        if not isinstance(element.tag, str):
            continue
        if _local_name(element.tag) != "t":
            continue
        if element.tag != f"{{{namespace}}}t":
            raise ValueError("mixed SpreadsheetML namespace in string payload")
        values.append(element.text or "")
    return "".join(values)


def read_shared_strings(root: Any) -> tuple[str, ...]:
    namespace = _root_namespace(root, "sst")
    values: list[str] = []
    for element in root:
        if not isinstance(element.tag, str):
            continue
        if _local_name(element.tag) != "si":
            continue
        if element.tag != f"{{{namespace}}}si":
            raise ValueError("mixed SpreadsheetML namespace in shared strings")
        values.append(_descendant_text(element, namespace))
    return tuple(values)


def _single_direct_child(element: Any, namespace: str, local: str) -> Any | None:
    matches = []
    for child in element:
        if not isinstance(child.tag, str):
            continue
        if _local_name(child.tag) != local:
            continue
        if child.tag != f"{{{namespace}}}{local}":
            raise ValueError("mixed SpreadsheetML namespace in cell")
        matches.append(child)
    if len(matches) > 1:
        raise ValueError(f"duplicate {local} element in cell")
    return matches[0] if matches else None


def _parse_number(text: str) -> int | float:
    if re.fullmatch(r"[+-]?[0-9]+", text):
        return int(text)
    try:
        value = float(text)
    except ValueError as exc:
        raise ValueError("invalid numeric cell value") from exc
    if not isfinite(value):
        raise ValueError("numeric cell value must be finite")
    return value


def _range_addresses(reference: str) -> set[str]:
    if ":" not in reference:
        row, column = a1_to_indices(reference)
        return {indices_to_a1(row, column)}
    start, end = reference.split(":", 1)
    start_row, start_col = a1_to_indices(start)
    end_row, end_col = a1_to_indices(end)
    if end_row < start_row or end_col < start_col:
        raise ValueError("merged range is reversed")
    return {
        indices_to_a1(row, column)
        for row in range(start_row, end_row + 1)
        for column in range(start_col, end_col + 1)
    }


def _merged_addresses(root: Any, namespace: str) -> frozenset[str]:
    containers = []
    for child in root:
        if not isinstance(child.tag, str):
            continue
        if _local_name(child.tag) == "mergeCells":
            if child.tag != f"{{{namespace}}}mergeCells":
                raise ValueError("mixed SpreadsheetML namespace in mergeCells")
            containers.append(child)
    if len(containers) > 1:
        raise ValueError("duplicate mergeCells container")
    addresses: set[str] = set()
    if not containers:
        return frozenset()
    for element in containers[0]:
        if not isinstance(element.tag, str):
            continue
        if _local_name(element.tag) != "mergeCell":
            continue
        if element.tag != f"{{{namespace}}}mergeCell":
            raise ValueError("mixed SpreadsheetML namespace in mergeCell")
        reference = element.get("ref")
        if not reference:
            raise ValueError("mergeCell is missing ref")
        addresses.update(_range_addresses(reference))
    return frozenset(addresses)


def _cell_value(
    cell: Any,
    namespace: str,
    shared_strings: tuple[str, ...],
) -> tuple[object, str | None, str | None, bool]:
    cell_type = cell.get("t")
    value_element = _single_direct_child(cell, namespace, "v")
    inline_element = _single_direct_child(cell, namespace, "is")
    formula_element = _single_direct_child(cell, namespace, "f")
    formula = None if formula_element is None else (formula_element.text or "")
    raw_value = None if value_element is None else (value_element.text or "")
    supported = True

    if cell_type == "s":
        if raw_value is None or inline_element is not None:
            raise ValueError("shared-string cell has invalid value structure")
        try:
            index = int(raw_value)
        except ValueError as exc:
            raise ValueError("shared-string index must be an integer") from exc
        if index < 0 or index >= len(shared_strings):
            raise ValueError("shared-string index is out of range")
        value: object = shared_strings[index]
    elif cell_type == "inlineStr":
        if inline_element is None or value_element is not None:
            raise ValueError("inline-string cell has invalid value structure")
        value = _descendant_text(inline_element, namespace)
    elif cell_type == "b":
        if raw_value not in {"0", "1"}:
            raise ValueError("boolean cell value must be 0 or 1")
        value = raw_value == "1"
    elif cell_type in {None, "n"}:
        value = None if raw_value is None else _parse_number(raw_value)
    elif cell_type in {"str", "e", "d"}:
        value = raw_value or ""
        supported = cell_type == "str" and formula is None
    else:
        value = raw_value
        supported = False
    return value, cell_type, formula, supported


def _display_text(value: object) -> str:
    if value is None:
        return ""
    if value is True:
        return "TRUE"
    if value is False:
        return "FALSE"
    return str(value)


def read_worksheet_grid(
    root: Any,
    *,
    shared_strings: tuple[str, ...] = (),
) -> XlsxWorksheetGrid:
    namespace = _root_namespace(root, "worksheet")
    merged = _merged_addresses(root, namespace)
    sheet_data = []
    for child in root:
        if not isinstance(child.tag, str):
            continue
        if _local_name(child.tag) == "sheetData":
            if child.tag != f"{{{namespace}}}sheetData":
                raise ValueError("mixed SpreadsheetML namespace in sheetData")
            sheet_data.append(child)
    if len(sheet_data) != 1:
        raise ValueError("worksheet must contain exactly one sheetData")

    cells: list[XlsxCell] = []
    seen: set[str] = set()
    seen_rows: set[int] = set()
    max_row = -1
    max_column = -1
    for row_element in sheet_data[0]:
        if not isinstance(row_element.tag, str):
            continue
        if _local_name(row_element.tag) != "row":
            continue
        if row_element.tag != f"{{{namespace}}}row":
            raise ValueError("mixed SpreadsheetML namespace in row")
        raw_row = row_element.get("r")
        if raw_row is None:
            raise ValueError("worksheet row is missing r")
        try:
            row_number = int(raw_row)
        except ValueError as exc:
            raise ValueError("worksheet row r must be an integer") from exc
        if row_number < 1 or row_number > _MAX_ROWS or row_number in seen_rows:
            raise ValueError("duplicate or invalid worksheet row")
        seen_rows.add(row_number)
        for cell_element in row_element:
            if not isinstance(cell_element.tag, str):
                continue
            if _local_name(cell_element.tag) != "c":
                continue
            if cell_element.tag != f"{{{namespace}}}c":
                raise ValueError("mixed SpreadsheetML namespace in cell")
            address = cell_element.get("r")
            if not address:
                raise ValueError("worksheet cell is missing r")
            row, column = a1_to_indices(address)
            if row != row_number - 1:
                raise ValueError("worksheet cell address disagrees with row r")
            if address in seen:
                raise ValueError("duplicate worksheet cell reference")
            seen.add(address)
            value, data_type, formula, supported = _cell_value(
                cell_element,
                namespace,
                shared_strings,
            )
            raw_style = cell_element.get("s")
            style_id = None
            if raw_style is not None:
                try:
                    style_id = int(raw_style)
                except ValueError as exc:
                    raise ValueError("cell style id must be an integer") from exc
                if style_id < 0:
                    raise ValueError("cell style id must be non-negative")
            is_merged = address in merged
            if formula is not None:
                capability = CapabilityDecision(
                    operation="update_sheet_cells",
                    state=CapabilityState.READ_ONLY,
                    reason_code="xlsx.cell.formula_requires_explicit_formula_edit",
                )
            elif is_merged:
                capability = CapabilityDecision(
                    operation="update_sheet_cells",
                    state=CapabilityState.READ_ONLY,
                    reason_code="xlsx.cell.merged_range",
                )
            elif not supported or type(value) not in {
                str,
                int,
                float,
                bool,
                type(None),
            }:
                capability = CapabilityDecision(
                    operation="update_sheet_cells",
                    state=CapabilityState.READ_ONLY,
                    reason_code="xlsx.cell.unsupported_type",
                )
            else:
                capability = CapabilityDecision(
                    operation="update_sheet_cells",
                    state=CapabilityState.WRITABLE,
                    constraints={"preservation": "target-cell", "typed_value": True},
                )
            cells.append(
                XlsxCell(
                    address=address,
                    row=row,
                    column=column,
                    value=value,
                    display_text=_display_text(value),
                    data_type=data_type,
                    formula=formula,
                    style_id=style_id,
                    merged=is_merged,
                    capability=capability,
                )
            )
            max_row = max(max_row, row)
            max_column = max(max_column, column)

    for address in merged:
        row, column = a1_to_indices(address)
        max_row = max(max_row, row)
        max_column = max(max_column, column)
    return XlsxWorksheetGrid(
        rows=max_row + 1 if max_row >= 0 else 0,
        columns=max_column + 1 if max_column >= 0 else 0,
        cells=tuple(sorted(cells, key=lambda item: (item.row, item.column))),
        merged_addresses=merged,
    )
