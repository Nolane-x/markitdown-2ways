from __future__ import annotations

from markitdown.twoways.formats.xlsx.cells import read_worksheet_grid
from markitdown.twoways.formats.xlsx.patch import patch_worksheet_cells
from markitdown.twoways.ooxml import parse_xml_part

from ._xlsx_fixtures import SHEET1


def _values(xml: bytes) -> dict[str, object]:
    grid = read_worksheet_grid(parse_xml_part(xml), shared_strings=("North",))
    return {cell.address: cell.value for cell in grid.cells}


def test_patches_string_as_local_inline_string_without_touching_shared_strings() -> None:
    output = patch_worksheet_cells(
        SHEET1.encode(),
        shared_strings=("North",),
        updates=({"row": 0, "column": 0, "old_value": "North", "value": "South"},),
    )
    values = _values(output)
    assert values["A1"] == "South"
    assert values["B1"] == 7
    root = parse_xml_part(output)
    target = root.xpath("//*[local-name()='c' and @r='A1']")[0]
    assert target.get("t") == "inlineStr"


def test_patches_number_boolean_and_blank_cells() -> None:
    output = patch_worksheet_cells(
        SHEET1.encode(),
        shared_strings=("North",),
        updates=(
            {"row": 0, "column": 1, "old_value": 7, "value": 9.5},
            {"row": 1, "column": 0, "old_value": True, "value": False},
            {"row": 1, "column": 1, "old_value": "East", "value": None},
        ),
    )
    values = _values(output)
    assert values["B1"] == 9.5
    assert values["A2"] is False
    assert values["B2"] is None


def test_preserves_style_attribute_on_target_cell() -> None:
    output = patch_worksheet_cells(
        SHEET1.encode(),
        shared_strings=("North",),
        updates=({"row": 0, "column": 0, "old_value": "North", "value": "South"},),
    )
    root = parse_xml_part(output)
    target = root.xpath("//*[local-name()='c' and @r='A1']")[0]
    assert target.get("s") == "1"
