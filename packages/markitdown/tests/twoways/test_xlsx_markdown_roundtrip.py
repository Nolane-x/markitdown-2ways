from __future__ import annotations

from io import BytesIO

import pytest

from markitdown.twoways import (
    MarkdownImportError,
    MarkdownProjectionMode,
    MarkdownProjectionOptions,
)
from markitdown.twoways.formats.xlsx.reader import read_xlsx_ir
from markitdown.twoways.formats.xlsx.writer import patch_xlsx
from markitdown.twoways.markdown import import_identity_markdown, project_markdown

from ._xlsx_fixtures import make_xlsx


_TEXT_SHEET = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <sheetData>
    <row r="1">
      <c r="A1" t="inlineStr"><is><t>Region</t></is></c>
      <c r="B1" t="inlineStr"><is><t>Revenue</t></is></c>
    </row>
    <row r="2">
      <c r="A2" t="inlineStr"><is><t>APAC</t></is></c>
      <c r="B2" t="inlineStr"><is><t>38%</t></is></c>
    </row>
  </sheetData>
</worksheet>
"""


def _text_document():
    source = make_xlsx(replacements={"xl/worksheets/sheet1.xml": _TEXT_SHEET})
    return source, read_xlsx_ir(BytesIO(source))


def _identity_projection(document):
    return project_markdown(
        document,
        options=MarkdownProjectionOptions(mode=MarkdownProjectionMode.IDENTITY),
    )


def _data_block(projection):
    return next(
        block
        for block in projection.manifest.blocks
        if block.node_id.startswith("xlsx-sheet-")
        and "| Region | Revenue |" in projection.markdown
        and block.editable_capabilities
    )


def test_all_text_xlsx_sheet_advertises_update_sheet_cells() -> None:
    _, document = _text_document()
    projection = _identity_projection(document)
    block = _data_block(projection)

    assert block.editable_capabilities == ("update_sheet_cells",)
    assert "| Region | Revenue |" in projection.markdown
    assert "| APAC | 38% |" in projection.markdown


def test_xlsx_identity_cell_change_generates_typed_sheet_edit() -> None:
    _, document = _text_document()
    projection = _identity_projection(document)
    block = _data_block(projection)
    edited = projection.markdown.replace("| APAC | 38% |", "| APAC | 42% |", 1)

    result = import_identity_markdown(
        edited,
        original_document=document,
        manifest=projection.manifest,
    )

    edit = next(item for item in result.edits if item.target_node_id == block.node_id)
    assert edit.type == "update_sheet_cells"
    assert edit.payload == {
        "cells": [{"row": 1, "column": 1, "old_value": "38%", "value": "42%"}]
    }
    assert edit.precondition is not None
    assert edit.precondition.expected_semantic_digest
    assert edit.precondition.expected_native_locator_digest
    assert edit.source_label == "markdown.identity.v1"


def test_xlsx_identity_edit_round_trips_through_native_writer() -> None:
    source, document = _text_document()
    projection = _identity_projection(document)
    edited = projection.markdown.replace("| APAC | 38% |", "| APAC | 42% |", 1)
    imported = import_identity_markdown(
        edited,
        original_document=document,
        manifest=projection.manifest,
    )
    output = BytesIO()

    patch_xlsx(document, BytesIO(source), output, edits=imported.edits)
    reread = read_xlsx_ir(BytesIO(output.getvalue()))
    data_sheet = reread.nodes[reread.canvases[0].root_node_ids[0]]
    cell = next(
        cell for cell in data_sheet.payload.cells if (cell.row, cell.column) == (1, 1)
    )

    assert cell.metadata["xlsx.typed_value"] == "42%"


def test_mixed_type_xlsx_sheet_stays_identity_read_only() -> None:
    document = read_xlsx_ir(BytesIO(make_xlsx()))
    projection = _identity_projection(document)
    data_node_id = document.canvases[0].root_node_ids[0]
    block = next(
        item for item in projection.manifest.blocks if item.node_id == data_node_id
    )

    assert block.editable_capabilities == ()


@pytest.mark.parametrize("unsafe_text", [" Region", "Region ", "A|B", "A\nB"])
def test_unsafe_xlsx_text_cell_stays_identity_read_only(unsafe_text: str) -> None:
    escaped = (
        unsafe_text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    )
    sheet = _TEXT_SHEET.replace("Region</t>", f"{escaped}</t>", 1)
    source = make_xlsx(replacements={"xl/worksheets/sheet1.xml": sheet})
    document = read_xlsx_ir(BytesIO(source))
    projection = _identity_projection(document)
    data_node_id = document.canvases[0].root_node_ids[0]
    block = next(
        item for item in projection.manifest.blocks if item.node_id == data_node_id
    )

    assert block.editable_capabilities == ()


def test_xlsx_identity_structure_change_fails_closed() -> None:
    _, document = _text_document()
    projection = _identity_projection(document)
    edited = projection.markdown.replace("| APAC | 38% |\n", "", 1)

    with pytest.raises(MarkdownImportError):
        import_identity_markdown(
            edited,
            original_document=document,
            manifest=projection.manifest,
        )
