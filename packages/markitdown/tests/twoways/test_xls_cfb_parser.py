from __future__ import annotations

import pytest

from markitdown.twoways.formats.xls import XlsFormatError, XlsLimits, parse_cfb

from ._xls_fixtures import make_cfb_with_streams, make_workbook, make_xls_cfb


def test_parses_unique_top_level_workbook_stream() -> None:
    fixture = make_xls_cfb()
    parsed = parse_cfb(fixture.data)
    workbook = parsed.stream("Workbook", parent_id=0)

    assert workbook.logical_bytes == fixture.workbook_bytes
    assert workbook.chain_kind == "mini"
    assert workbook.physical_ranges[0].start == fixture.workbook_physical_start
    assert sum(item.length for item in workbook.physical_ranges) == len(
        fixture.workbook_bytes
    )
    assert len(parsed.topology_sha256) == 64


def test_duplicate_workbook_stream_is_ambiguous() -> None:
    parsed = parse_cfb(make_xls_cfb(duplicate_workbook=True).data)
    with pytest.raises(XlsFormatError, match="ambiguous|duplicate"):
        parsed.stream("Workbook", parent_id=0)


def test_source_limit_fails_closed() -> None:
    source = make_xls_cfb().data
    with pytest.raises(XlsFormatError, match="source.*limit|resource"):
        parse_cfb(source, limits=XlsLimits(max_source_bytes=len(source) - 1))


def test_truncated_cfb_fails_closed() -> None:
    source = make_xls_cfb().data[:-100]
    with pytest.raises(XlsFormatError, match="truncated|sector|size"):
        parse_cfb(source)


def test_invalid_signature_fails_closed() -> None:
    source = bytearray(make_xls_cfb().data)
    source[0] ^= 0xFF
    with pytest.raises(XlsFormatError, match="signature"):
        parse_cfb(bytes(source))


def test_missing_workbook_is_representable_at_cfb_layer() -> None:
    workbook, _, _ = make_workbook()
    data, _ = make_cfb_with_streams((("Other", workbook),))
    parsed = parse_cfb(data)
    with pytest.raises(XlsFormatError, match="missing"):
        parsed.stream("Workbook", parent_id=0)
