from __future__ import annotations

import pytest

from markitdown.twoways.formats.xls import XlsFormatError, XlsLimits, parse_xls

from ._xls_fixtures import make_xls_cfb


def test_parses_biff8_number_owner_and_sheet_identity() -> None:
    fixture = make_xls_cfb(values=((2, 3, 42.5, 7),))
    parsed = parse_xls(fixture.data)

    assert parsed.workbook_stream.name == "Workbook"
    assert len(parsed.sheets) == 1
    sheet = parsed.sheets[0]
    assert sheet.name == "Sheet1"
    assert sheet.sheet_type == 0
    assert sheet.bof_offset == fixture.sheet_offset
    assert sheet.is_dialog is False
    assert len(sheet.number_owners) == 1

    owner = sheet.number_owners[0]
    assert owner.row == 2
    assert owner.column == 3
    assert owner.xf_index == 7
    assert owner.value == 42.5
    assert owner.value_logical_offset == fixture.number_value_offsets[0]
    assert sum(item.length for item in owner.value_physical_ranges) == 8
    assert len(owner.record_sha256) == 64
    assert len(owner.value_sha256) == 64
    assert parsed.blockers == ()


def test_formula_makes_workbook_read_only() -> None:
    parsed = parse_xls(make_xls_cfb(include_formula=True).data)
    assert "xls.workbook.formulas_present" in parsed.blockers


def test_filepass_blocks_encrypted_workbook() -> None:
    parsed = parse_xls(make_xls_cfb(include_filepass=True).data)
    assert "xls.workbook.encrypted" in parsed.blockers


def test_competing_book_stream_blocks_authority() -> None:
    parsed = parse_xls(make_xls_cfb(competing_book=True).data)
    assert "xls.container.competing_book_stream" in parsed.blockers


def test_duplicate_number_coordinate_blocks_sheet() -> None:
    parsed = parse_xls(make_xls_cfb(duplicate_coordinate=True).data)
    assert "xls.cell.duplicate_owner" in parsed.blockers


def test_invalid_boundsheet_pointer_fails_closed() -> None:
    with pytest.raises(XlsFormatError, match="BoundSheet|BOF|pointer"):
        parse_xls(make_xls_cfb(invalid_sheet_pointer=True).data)


def test_nonfinite_number_is_read_only() -> None:
    parsed = parse_xls(make_xls_cfb(values=((0, 0, float("inf"), 0),)).data)
    assert "xls.cell.non_finite" in parsed.blockers


def test_record_limit_fails_closed() -> None:
    with pytest.raises(XlsFormatError, match="record.*limit|resource"):
        parse_xls(make_xls_cfb().data, limits=XlsLimits(max_biff_records=2))
