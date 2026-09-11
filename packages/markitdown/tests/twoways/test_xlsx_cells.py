from __future__ import annotations

import pytest

from markitdown.twoways.capabilities import CapabilityState
from markitdown.twoways.formats.xlsx.cells import (
    a1_to_indices,
    indices_to_a1,
    read_shared_strings,
    read_worksheet_grid,
)
from markitdown.twoways.ooxml import parse_xml_part

from ._xlsx_fixtures import SHARED_STRINGS, SHEET1


@pytest.mark.parametrize(
    ("address", "indices"),
    [
        ("A1", (0, 0)),
        ("Z9", (8, 25)),
        ("AA10", (9, 26)),
        ("XFD1048576", (1048575, 16383)),
    ],
)
def test_a1_round_trip(address: str, indices: tuple[int, int]) -> None:
    assert a1_to_indices(address) == indices
    assert indices_to_a1(*indices) == address


@pytest.mark.parametrize(
    "address", ["", "A0", "XFE1", "A1048577", "$A$1", "A1:B2", "1A", "a1"]
)
def test_a1_rejects_invalid_addresses(address: str) -> None:
    with pytest.raises(ValueError):
        a1_to_indices(address)


def test_reads_shared_inline_numeric_boolean_blank_and_formula_cells() -> None:
    shared = read_shared_strings(parse_xml_part(SHARED_STRINGS.encode()))
    grid = read_worksheet_grid(parse_xml_part(SHEET1.encode()), shared_strings=shared)
    cells = {cell.address: cell for cell in grid.cells}

    assert shared == ("North",)
    assert cells["A1"].value == "North"
    assert cells["A1"].style_id == 1
    assert cells["B1"].value == 7
    assert type(cells["B1"].value) is int
    assert cells["A2"].value is True
    assert cells["B2"].value == "East"
    assert cells["C2"].value is None
    assert cells["C1"].formula == "B1+1"
    assert cells["C1"].value == 8


def test_formula_cells_are_read_only() -> None:
    grid = read_worksheet_grid(
        parse_xml_part(SHEET1.encode()),
        shared_strings=("North",),
    )
    formula = next(cell for cell in grid.cells if cell.address == "C1")
    decision = formula.capability
    assert decision.state is CapabilityState.READ_ONLY
    assert decision.reason_code == "xlsx.cell.formula_requires_explicit_formula_edit"


def test_plain_scalar_cells_are_writable() -> None:
    grid = read_worksheet_grid(
        parse_xml_part(SHEET1.encode()),
        shared_strings=("North",),
    )
    for address in ("A1", "B1", "A2", "B2", "C2"):
        decision = next(
            cell for cell in grid.cells if cell.address == address
        ).capability
        assert decision.state is CapabilityState.WRITABLE, address


def test_rich_inline_string_is_read_only_to_preserve_runs() -> None:
    rich_xml = SHEET1.replace(
        '<c r="B2" t="inlineStr"><is><t>East</t></is></c>',
        '<c r="B2" t="inlineStr"><is>'
        "<r><rPr><b/></rPr><t>Ea</t></r><r><t>st</t></r>"
        "</is></c>",
    )
    grid = read_worksheet_grid(
        parse_xml_part(rich_xml.encode()),
        shared_strings=("North",),
    )
    cell = next(cell for cell in grid.cells if cell.address == "B2")

    assert cell.value == "East"
    assert cell.capability.state is CapabilityState.READ_ONLY
    assert (
        cell.capability.reason_code
        == "xlsx.cell.rich_text_requires_run_preserving_edit"
    )


def test_merged_cells_are_read_only() -> None:
    merged_xml = SHEET1.replace(
        "</worksheet>",
        '<mergeCells count="1"><mergeCell ref="A1:B1"/></mergeCells></worksheet>',
    )
    grid = read_worksheet_grid(
        parse_xml_part(merged_xml.encode()),
        shared_strings=("North",),
    )
    for address in ("A1", "B1"):
        cell = next(cell for cell in grid.cells if cell.address == address)
        assert cell.capability.state is CapabilityState.READ_ONLY
        assert cell.capability.reason_code == "xlsx.cell.merged_range"


def test_duplicate_cell_reference_fails_closed() -> None:
    xml = SHEET1.replace(
        '<c r="B1"><v>7</v></c>', '<c r="B1"><v>7</v></c><c r="B1"><v>8</v></c>'
    )
    with pytest.raises(ValueError, match="duplicate"):
        read_worksheet_grid(parse_xml_part(xml.encode()), shared_strings=("North",))
