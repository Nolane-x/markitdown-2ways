from __future__ import annotations

import codecs
from io import BytesIO

import pytest

from markitdown.twoways._errors import RoundTripVerificationError
from markitdown.twoways.formats.csv import writer as csv_writer
from markitdown.twoways.formats.csv.reader import read_csv_ir
from markitdown.twoways.formats.csv.writer import patch_csv
from markitdown.twoways.ir.edits import EditOperation


def _table(document):
    return document.nodes[document.canvases[0].root_node_ids[0]]


def _edit(document, *, row: int, column: int, old_text: str, text: str) -> EditOperation:
    return EditOperation(
        operation_id="edit-1",
        type="update_csv_cells",
        target_node_id=_table(document).node_id,
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


def test_utf16_be_bom_is_preserved_by_target_only_patch() -> None:
    source = codecs.BOM_UTF16_BE + "name,city\r\nAndré,Paris\r\n".encode("utf-16-be")
    document = read_csv_ir(BytesIO(source), filename="people.csv")
    output = BytesIO()

    patch_csv(
        document,
        BytesIO(source),
        output,
        edits=(
            _edit(document, row=1, column=1, old_text="Paris", text="Lyon"),
        ),
    )

    assert output.getvalue() == (
        codecs.BOM_UTF16_BE + "name,city\r\nAndré,Lyon\r\n".encode("utf-16-be")
    )


def test_stateful_encoding_leakage_outside_target_is_rejected_before_output() -> None:
    text = "name,city\nA,東京\n"
    source = text.encode("iso2022_jp")
    document = read_csv_ir(
        BytesIO(source),
        filename="people.csv",
        encoding="iso2022_jp",
    )
    output = BytesIO()

    with pytest.raises(RoundTripVerificationError, match="outside authorized target"):
        patch_csv(
            document,
            BytesIO(source),
            output,
            edits=(
                _edit(document, row=1, column=0, old_text="A", text="日本"),
            ),
        )

    assert output.getvalue() == b""


def test_candidate_verifier_rejects_unrequested_cell_change() -> None:
    source = b"a,b\nc,d\n"
    document = read_csv_ir(BytesIO(source), filename="data.csv")
    node = _table(document)
    representation = csv_writer._representation(node)

    with pytest.raises(RoundTripVerificationError, match="cell verification"):
        csv_writer._verify_candidate(
            document,
            node,
            b"a,B\nc,x\n",
            representation,
            ",",
            {(1, 1): "x"},
        )


def test_candidate_verifier_rejects_structure_change() -> None:
    source = b"a,b\nc,d\n"
    document = read_csv_ir(BytesIO(source), filename="data.csv")
    node = _table(document)
    representation = csv_writer._representation(node)

    with pytest.raises(RoundTripVerificationError, match="row/column structure"):
        csv_writer._verify_candidate(
            document,
            node,
            b"a,b\nc,x\nextra,row\n",
            representation,
            ",",
            {(1, 1): "x"},
        )


def test_candidate_verifier_rejects_bom_drift() -> None:
    source = codecs.BOM_UTF8 + b"a,b\nc,d\n"
    document = read_csv_ir(BytesIO(source), filename="data.csv")
    node = _table(document)
    representation = csv_writer._representation(node)

    with pytest.raises(RoundTripVerificationError, match="representation"):
        csv_writer._verify_candidate(
            document,
            node,
            b"a,b\nc,x\n",
            representation,
            ",",
            {(1, 1): "x"},
        )
