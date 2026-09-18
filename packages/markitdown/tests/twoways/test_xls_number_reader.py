from __future__ import annotations

from io import BytesIO
from types import SimpleNamespace

from markitdown.twoways import CapabilityState, capabilities_for_node
from markitdown.twoways.formats.xls import XlsIRReader, XlsLimits, read_xls_ir
from markitdown.twoways.ir.nodes import TablePayload

from ._xls_fixtures import make_xls_cfb


def _sheet_node(document):
    return next(iter(document.nodes.values()))


def test_reader_projects_number_cells_with_native_authority() -> None:
    fixture = make_xls_cfb(values=((0, 0, 1.5, 4), (1, 2, 9.25, 7)))
    document = read_xls_ir(BytesIO(fixture.data), filename="legacy.xls")

    assert document.source is not None
    assert document.source.format == "xls"
    assert document.source.filename == "legacy.xls"
    assert len(document.canvases) == 1
    assert document.canvases[0].kind == "worksheet"
    assert document.canvases[0].name == "Sheet1"

    node = _sheet_node(document)
    assert isinstance(node.payload, TablePayload)
    assert node.payload.rows == 2
    assert node.payload.columns == 3
    assert node.metadata["xls.sheet_name"] == "Sheet1"
    assert node.metadata["xls.bof_offset"] == fixture.sheet_offset

    target = next(
        cell for cell in node.payload.cells if (cell.row, cell.column) == (1, 2)
    )
    assert target.text == "9.25"
    assert target.metadata["xls.typed_value"] == 9.25
    assert target.metadata["xls.native_record_kind"] == "NUMBER"
    assert target.metadata["xls.xf_index"] == 7
    assert target.metadata["xls.writable"] is True
    assert (
        sum(item["length"] for item in target.metadata["xls.value_physical_ranges"])
        == 8
    )

    decision = capabilities_for_node(node).for_operation("update_sheet_cells")
    assert decision.state is CapabilityState.WRITABLE


def test_missing_dense_cells_are_read_only_not_native_number_owners() -> None:
    document = read_xls_ir(
        BytesIO(make_xls_cfb(values=((1, 1, 2.0, 0),)).data),
        filename="legacy.xls",
    )
    node = _sheet_node(document)
    missing = next(
        cell for cell in node.payload.cells if (cell.row, cell.column) == (0, 0)
    )
    assert missing.metadata["xls.present"] is False
    assert missing.metadata["xls.writable"] is False
    assert missing.metadata["xls.reason_code"] == "xls.cell.missing_number_owner"


def test_formula_blocks_number_write_capability() -> None:
    document = read_xls_ir(
        BytesIO(make_xls_cfb(include_formula=True).data),
        filename="legacy.xls",
    )
    node = _sheet_node(document)
    decision = capabilities_for_node(node).for_operation("update_sheet_cells")

    assert decision.state is CapabilityState.READ_ONLY
    assert decision.reason_code == "xls.workbook.formulas_present"
    assert all(cell.metadata["xls.writable"] is False for cell in node.payload.cells)


def test_read_limits_are_bound_into_document_metadata() -> None:
    limits = XlsLimits(max_biff_records=100)
    document = read_xls_ir(
        BytesIO(make_xls_cfb().data),
        filename="legacy.xls",
        limits=limits,
    )

    assert document.metadata.custom["xls.read_limits.v1"]["max_biff_records"] == 100
    assert len(document.metadata.custom["xls.read_limits.sha256"]) == 64
    assert len(document.metadata.custom["xls.cfb_topology_sha256"]) == 64
    assert len(document.metadata.custom["xls.biff_topology_sha256"]) == 64


def test_xls_ir_reader_accepts_extension_and_mime() -> None:
    reader = XlsIRReader()
    empty = BytesIO()

    assert reader.accepts(empty, SimpleNamespace(extension=".xls", mimetype=None))
    assert reader.accepts(
        empty,
        SimpleNamespace(extension=None, mimetype="application/vnd.ms-excel"),
    )
    assert not reader.accepts(
        empty,
        SimpleNamespace(extension=".xlsx", mimetype=None),
    )
