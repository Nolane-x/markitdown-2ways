from __future__ import annotations

from dataclasses import replace

import pytest

from markitdown.twoways import (
    MarkdownImportError,
    MarkdownProjectionMode,
    MarkdownProjectionOptions,
    NativeLocator,
    TableCell,
    TablePayload,
)
from markitdown.twoways.markdown import import_identity_markdown, project_markdown

from ._fixtures import make_representative_document


def _capable_table_document():
    document = make_representative_document()
    table = replace(
        document.nodes["table1"],
        native_locator=NativeLocator(
            backend="docx-ooxml",
            part_uri="/word/document.xml",
            object_id="table:0",
            path="/*[local-name()='document']/*[local-name()='body']/*[local-name()='tbl'][1]",
            attributes={"table_index": 0},
        ),
        payload=TablePayload(
            rows=2,
            columns=2,
            cells=(
                TableCell(row=0, column=0, text="Region"),
                TableCell(row=0, column=1, text="Revenue"),
                TableCell(row=1, column=0, text="APAC"),
                TableCell(row=1, column=1, text="38%"),
            ),
        ),
        metadata={"docx:patch_capabilities": ("update_table_cells",)},
    )
    return replace(document, nodes={**document.nodes, "table1": table})


def _identity_projection(document):
    return project_markdown(
        document,
        options=MarkdownProjectionOptions(mode=MarkdownProjectionMode.IDENTITY),
    )


def test_capable_table_projection_advertises_cell_updates():
    projection = _identity_projection(_capable_table_document())
    block = next(item for item in projection.manifest.blocks if item.node_id == "table1")

    assert block.editable_capabilities == ("update_table_cells",)
    assert "| Region | Revenue |" in projection.markdown
    assert "| APAC | 38% |" in projection.markdown


def test_single_cell_change_generates_update_table_cells_with_stale_write_evidence():
    document = _capable_table_document()
    projection = _identity_projection(document)
    edited = projection.markdown.replace("| APAC | 38% |", "| APAC | 42% |", 1)

    result = import_identity_markdown(
        edited,
        original_document=document,
        manifest=projection.manifest,
    )

    assert len(result.edits) == 1
    edit = result.edits[0]
    assert edit.type == "update_table_cells"
    assert edit.target_node_id == "table1"
    assert edit.payload == {
        "cells": [
            {"row": 1, "column": 1, "old_text": "38%", "text": "42%"}
        ]
    }
    assert edit.precondition is not None
    assert edit.precondition.expected_old_value == "Region\tRevenue\nAPAC\t38%"
    assert edit.precondition.expected_semantic_digest
    assert edit.precondition.expected_native_locator_digest
    assert edit.source_label == "markdown.identity.v1"


def test_multi_cell_change_is_sorted_and_operation_id_is_deterministic():
    document = _capable_table_document()
    projection = _identity_projection(document)
    edited = projection.markdown.replace("Region", "Market", 1).replace(
        "38%", "42%", 1
    )

    first = import_identity_markdown(
        edited,
        original_document=document,
        manifest=projection.manifest,
    )
    second = import_identity_markdown(
        edited,
        original_document=document,
        manifest=projection.manifest,
    )

    assert first.edits[0].payload["cells"] == [
        {"row": 0, "column": 0, "old_text": "Region", "text": "Market"},
        {"row": 1, "column": 1, "old_text": "38%", "text": "42%"},
    ]
    assert first.edits[0].operation_id == second.edits[0].operation_id


def test_table_structure_change_fails_closed():
    document = _capable_table_document()
    projection = _identity_projection(document)
    edited = projection.markdown.replace("| APAC | 38% |\n", "", 1)

    with pytest.raises(MarkdownImportError) as raised:
        import_identity_markdown(
            edited,
            original_document=document,
            manifest=projection.manifest,
        )

    assert raised.value.code == "markdown.semantic.parse_error"


def test_pipe_or_multiline_cell_never_becomes_identity_editable():
    document = _capable_table_document()
    table = document.nodes["table1"]
    unsafe = replace(
        table,
        payload=TablePayload(
            rows=2,
            columns=2,
            cells=(
                TableCell(row=0, column=0, text="Region|Market"),
                TableCell(row=0, column=1, text="Revenue"),
                TableCell(row=1, column=0, text="APAC"),
                TableCell(row=1, column=1, text="38%"),
            ),
        ),
    )
    document = replace(document, nodes={**document.nodes, "table1": unsafe})
    projection = _identity_projection(document)
    block = next(item for item in projection.manifest.blocks if item.node_id == "table1")

    assert block.editable_capabilities == ()
