from __future__ import annotations

from io import BytesIO

import pytest

from markitdown.twoways.formats.csv.reader import read_csv_ir
from markitdown.twoways.formats.csv.writer import patch_csv
from markitdown.twoways.ir.edits import EditOperation


def _edit(document, *, row: int, column: int, old_text: str, text: str) -> EditOperation:
    node_id = document.canvases[0].root_node_ids[0]
    return EditOperation(
        operation_id="edit-1",
        type="update_csv_cells",
        target_node_id=node_id,
        payload={
            "cells": [
                {
                    "row": row,
                    "column": column,
                    "old_text": old_text,
                    "text": text,
                }
            ]
        },
    )


def test_patch_preserves_mixed_physical_row_terminators_and_blank_record() -> None:
    source = b"a,b\r\n\r\nc,d\nx,y\r"
    document = read_csv_ir(BytesIO(source), filename="mixed.csv")
    output = BytesIO()

    patch_csv(
        document,
        BytesIO(source),
        output,
        edits=(
            _edit(document, row=2, column=1, old_text="d", text="z"),
        ),
    )

    assert output.getvalue() == b"a,b\r\n\r\nc,z\nx,y\r"


def test_patch_preserves_existing_multiline_quoted_neighbor_exactly() -> None:
    source = b'left,right\r\n"alpha\nbeta",tail\r\n'
    document = read_csv_ir(BytesIO(source), filename="multiline.csv")
    output = BytesIO()

    patch_csv(
        document,
        BytesIO(source),
        output,
        edits=(
            _edit(document, row=1, column=1, old_text="tail", text="done"),
        ),
    )

    assert output.getvalue() == b'left,right\r\n"alpha\nbeta",done\r\n'


def test_unencodable_replacement_fails_before_destination_output() -> None:
    source = "name,city\r\nAndré,Paris\r\n".encode("cp1252")
    document = read_csv_ir(
        BytesIO(source),
        filename="people.csv",
        encoding="cp1252",
    )
    output = BytesIO()

    with pytest.raises(UnicodeEncodeError):
        patch_csv(
            document,
            BytesIO(source),
            output,
            edits=(
                _edit(document, row=1, column=1, old_text="Paris", text="東京"),
            ),
        )

    assert output.getvalue() == b""
