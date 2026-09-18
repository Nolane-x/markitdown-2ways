from __future__ import annotations

from io import BytesIO
from pathlib import Path

import pytest

from markitdown import MarkItDown
from markitdown._stream_info import StreamInfo
from markitdown.converters._xlsx_converter import XlsConverter
from markitdown.twoways.formats.xls import patch_xls, read_xls_ir
from markitdown.twoways.ir.edits import EditOperation

from ._xls_fixtures import make_xls_cfb


def _sheet_node(document):
    return next(iter(document.nodes.values()))


def _edit(document, value: float) -> EditOperation:
    node = _sheet_node(document)
    cell = next(cell for cell in node.payload.cells if cell.metadata["xls.present"])
    return EditOperation(
        operation_id="cell",
        type="update_sheet_cells",
        target_node_id=node.node_id,
        payload={
            "cells": [
                {
                    "row": cell.row,
                    "column": cell.column,
                    "old_value": cell.metadata["xls.typed_value"],
                    "value": value,
                }
            ]
        },
    )


def test_xlrd_reads_source_and_candidate_number_semantics() -> None:
    xlrd = pytest.importorskip("xlrd")
    source = make_xls_cfb(values=((0, 0, 1.5, 0),)).data
    document = read_xls_ir(BytesIO(source), filename="legacy.xls")
    output = BytesIO()

    patch_xls(
        document,
        BytesIO(source),
        output,
        edits=(_edit(document, 7.25),),
    )
    candidate = output.getvalue()

    before = xlrd.open_workbook(file_contents=source)
    after = xlrd.open_workbook(file_contents=candidate)

    assert before.sheet_by_name("Sheet1").cell_value(0, 0) == 1.5
    assert after.sheet_by_name("Sheet1").cell_value(0, 0) == 7.25


def test_h17_does_not_change_one_way_xls_acceptance() -> None:
    converter = XlsConverter()
    source = BytesIO(b"")
    info = StreamInfo(
        filename="legacy.xls",
        extension=".xls",
        mimetype="application/vnd.ms-excel",
    )

    assert converter.accepts(source, info) is True


def test_real_xls_fixture_still_converts_through_one_way_path() -> None:
    pytest.importorskip("xlrd")
    pytest.importorskip("pandas")
    fixture = Path(__file__).parents[1] / "test_files" / "test.xls"

    result = MarkItDown().convert(fixture)

    assert result.markdown.strip()
