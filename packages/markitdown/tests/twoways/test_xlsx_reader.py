from __future__ import annotations

from io import BytesIO

from markitdown.twoways.capabilities import CapabilityState, capabilities_for_node
from markitdown.twoways.formats.xlsx.reader import read_xlsx_ir
from markitdown.twoways.ir.nodes import TablePayload
from markitdown.twoways.ir.serialization import canonical_json_digest, validate_document

from ._xlsx_fixtures import SHARED_STRINGS, make_xlsx


def test_reads_workbook_into_deterministic_worksheet_canvases() -> None:
    source = make_xlsx()
    first = read_xlsx_ir(BytesIO(source))
    second = read_xlsx_ir(BytesIO(source))

    validate_document(first)
    assert canonical_json_digest(first) == canonical_json_digest(second)
    assert first.source is not None
    assert first.source.format == "xlsx"
    assert [canvas.kind for canvas in first.canvases] == ["worksheet", "worksheet"]
    assert [canvas.name for canvas in first.canvases] == ["Data", "Other"]


def test_reader_preserves_typed_cell_metadata_and_native_sheet_locator() -> None:
    document = read_xlsx_ir(BytesIO(make_xlsx()))
    table = document.nodes[document.canvases[0].root_node_ids[0]]

    assert isinstance(table.payload, TablePayload)
    assert table.native_locator is not None
    assert table.native_locator.backend == "xlsx"
    assert table.native_locator.part_uri == "/xl/worksheets/sheet1.xml"
    assert table.metadata["xlsx.sheet_name"] == "Data"
    cells = {(cell.row, cell.column): cell for cell in table.payload.cells}
    assert cells[(0, 0)].metadata["xlsx.address"] == "A1"
    assert cells[(0, 0)].metadata["xlsx.typed_value"] == "North"
    assert cells[(0, 1)].metadata["xlsx.typed_value"] == 7
    assert cells[(1, 0)].metadata["xlsx.typed_value"] is True
    assert cells[(1, 2)].metadata["xlsx.typed_value"] is None


def test_reader_marks_rich_shared_string_cell_read_only() -> None:
    rich_shared_strings = SHARED_STRINGS.replace(
        "<si><t>North</t></si>",
        "<si><r><rPr><b/></rPr><t>Nor</t></r><r><t>th</t></r></si>",
    )
    document = read_xlsx_ir(
        BytesIO(
            make_xlsx(
                replacements={"xl/sharedStrings.xml": rich_shared_strings},
            )
        )
    )
    table = document.nodes[document.canvases[0].root_node_ids[0]]
    assert isinstance(table.payload, TablePayload)
    cell = next(
        cell for cell in table.payload.cells if cell.row == 0 and cell.column == 0
    )

    assert cell.metadata["xlsx.typed_value"] == "North"
    assert cell.metadata["xlsx.writable"] is False
    assert (
        cell.metadata["xlsx.reason_code"]
        == "xlsx.cell.rich_text_requires_run_preserving_edit"
    )


def test_reader_table_capability_is_writable_when_sheet_has_writable_cells() -> None:
    document = read_xlsx_ir(BytesIO(make_xlsx()))
    table = document.nodes[document.canvases[0].root_node_ids[0]]
    decision = capabilities_for_node(table).for_operation("update_sheet_cells")

    assert decision.state is CapabilityState.WRITABLE
    assert decision.constraints["typed_cells"] is True