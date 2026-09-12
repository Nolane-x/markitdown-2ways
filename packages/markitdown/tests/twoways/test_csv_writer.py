from __future__ import annotations

import codecs
from dataclasses import replace
from io import BytesIO

import pytest

from markitdown.twoways._errors import (
    PatchPreconditionError,
    SourcePackageMismatchError,
    UnsupportedEditError,
)
from markitdown.twoways.formats.csv.reader import read_csv_ir
from markitdown.twoways.formats.csv.writer import patch_csv
from markitdown.twoways.ir.edits import EditOperation, EditPrecondition
from markitdown.twoways.ir.provenance import NativeLocator
from markitdown.twoways.ir.semantics import native_locator_digest, node_semantic_digest


def _table(document):
    return document.nodes[document.canvases[0].root_node_ids[0]]


def _edit(document, cells) -> EditOperation:
    node = _table(document)
    return EditOperation(
        operation_id="edit-1",
        type="update_csv_cells",
        target_node_id=node.node_id,
        precondition=EditPrecondition(
            expected_semantic_digest=node_semantic_digest(node),
            expected_native_locator_digest=native_locator_digest(node),
        ),
        payload={"cells": cells},
    )


def test_zero_edit_patch_is_byte_identical() -> None:
    source = codecs.BOM_UTF8 + b"name,city\r\nAda,North\r\n"
    document = read_csv_ir(BytesIO(source), filename="people.csv")
    output = BytesIO()

    result = patch_csv(document, BytesIO(source), output, edits=())

    assert output.getvalue() == source
    assert result.format == "csv"
    assert result.mode == "patch"
    assert result.bytes_written == len(source)
    assert result.fidelity.claimed_tier == "exact-preserve"


def test_source_digest_mismatch_fails_before_output() -> None:
    source = b"a,b\nc,d\n"
    document = read_csv_ir(BytesIO(source), filename="data.csv")
    output = BytesIO()

    with pytest.raises(SourcePackageMismatchError):
        patch_csv(document, BytesIO(b"a,b\nx,y\n"), output, edits=())

    assert output.getvalue() == b""


def test_source_size_metadata_mismatch_fails_before_output() -> None:
    source = b"a,b\nc,d\n"
    document = read_csv_ir(BytesIO(source), filename="data.csv")
    assert document.source is not None
    forged = replace(
        document,
        source=replace(document.source, size_bytes=len(source) + 1),
    )
    output = BytesIO()

    with pytest.raises(SourcePackageMismatchError, match="size"):
        patch_csv(forged, BytesIO(source), output, edits=())

    assert output.getvalue() == b""


def test_unquoted_target_is_patched_without_rebuilding_neighbors() -> None:
    source = b"name,city\r\nAda,North\r\nBob,West\r\n"
    document = read_csv_ir(BytesIO(source), filename="people.csv")
    output = BytesIO()

    patch_csv(
        document,
        BytesIO(source),
        output,
        edits=(
            _edit(
                document,
                [{"row": 1, "column": 1, "old_text": "North", "text": "South"}],
            ),
        ),
    )

    assert output.getvalue() == b"name,city\r\nAda,South\r\nBob,West\r\n"


def test_quoted_target_remains_quoted() -> None:
    source = b'name,city\nBob,"New,York"\n'
    document = read_csv_ir(BytesIO(source), filename="people.csv")
    output = BytesIO()

    patch_csv(
        document,
        BytesIO(source),
        output,
        edits=(
            _edit(
                document,
                [
                    {
                        "row": 1,
                        "column": 1,
                        "old_text": "New,York",
                        "text": "Los,Angeles",
                    }
                ],
            ),
        ),
    )

    assert output.getvalue() == b'name,city\nBob,"Los,Angeles"\n'


def test_unquoted_target_gets_quotes_only_when_required() -> None:
    source = b"name,city\nAda,North\nBob,West\n"
    document = read_csv_ir(BytesIO(source), filename="people.csv")
    output = BytesIO()

    patch_csv(
        document,
        BytesIO(source),
        output,
        edits=(
            _edit(
                document,
                [
                    {
                        "row": 1,
                        "column": 1,
                        "old_text": "North",
                        "text": "South,East",
                    }
                ],
            ),
        ),
    )

    assert output.getvalue() == b'name,city\nAda,"South,East"\nBob,West\n'


def test_quote_characters_are_doubled_in_target_lexeme() -> None:
    source = b"name,city\nAda,North\n"
    document = read_csv_ir(BytesIO(source), filename="people.csv")
    output = BytesIO()

    patch_csv(
        document,
        BytesIO(source),
        output,
        edits=(
            _edit(
                document,
                [{"row": 1, "column": 1, "old_text": "North", "text": 'A"B'}],
            ),
        ),
    )

    assert output.getvalue() == b'name,city\nAda,"A""B"\n'


def test_multiple_cells_are_patched_without_offset_corruption() -> None:
    source = b'name,city\nAda,North\nBob,"New,York"\n'
    document = read_csv_ir(BytesIO(source), filename="people.csv")
    output = BytesIO()

    patch_csv(
        document,
        BytesIO(source),
        output,
        edits=(
            _edit(
                document,
                [
                    {"row": 1, "column": 0, "old_text": "Ada", "text": "Evelyn"},
                    {
                        "row": 2,
                        "column": 1,
                        "old_text": "New,York",
                        "text": "Old,York",
                    },
                ],
            ),
        ),
    )

    assert output.getvalue() == b'name,city\nEvelyn,North\nBob,"Old,York"\n'


def test_replacement_newline_is_rejected_before_output() -> None:
    source = b"a,b\nc,d\n"
    document = read_csv_ir(BytesIO(source), filename="data.csv")
    output = BytesIO()

    with pytest.raises(UnsupportedEditError, match="newline"):
        patch_csv(
            document,
            BytesIO(source),
            output,
            edits=(
                _edit(
                    document,
                    [{"row": 1, "column": 1, "old_text": "d", "text": "x\ny"}],
                ),
            ),
        )

    assert output.getvalue() == b""


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"cells": "not-a-list"},
        {"cells": [{"row": 1, "column": 1, "old_text": "d", "text": "x", "x": 1}]},
        {"cells": [{"row": True, "column": 1, "old_text": "d", "text": "x"}]},
        {"cells": [{"row": -1, "column": 1, "old_text": "d", "text": "x"}]},
        {"cells": [{"row": 1, "column": 1, "old_text": 1, "text": "x"}]},
        {"cells": [{"row": 1, "column": 1, "old_text": "d", "text": 1}]},
        {"cells": [{"row": 1, "column": 1, "old_text": "d", "text": "d"}]},
        {"cells": [], "unexpected": True},
    ],
)
def test_malformed_cell_payloads_fail_closed(payload) -> None:
    source = b"a,b\nc,d\n"
    document = read_csv_ir(BytesIO(source), filename="data.csv")
    node = _table(document)
    output = BytesIO()
    edit = EditOperation(
        operation_id="bad",
        type="update_csv_cells",
        target_node_id=node.node_id,
        payload=payload,
    )

    with pytest.raises(UnsupportedEditError):
        patch_csv(document, BytesIO(source), output, edits=(edit,))

    assert output.getvalue() == b""


def test_duplicate_and_out_of_order_coordinates_fail_closed() -> None:
    source = b"a,b\nc,d\n"
    document = read_csv_ir(BytesIO(source), filename="data.csv")

    bad_cell_sets = (
        [
            {"row": 1, "column": 0, "old_text": "c", "text": "x"},
            {"row": 1, "column": 0, "old_text": "c", "text": "y"},
        ],
        [
            {"row": 1, "column": 1, "old_text": "d", "text": "y"},
            {"row": 1, "column": 0, "old_text": "c", "text": "x"},
        ],
    )
    for cells in bad_cell_sets:
        output = BytesIO()
        with pytest.raises(UnsupportedEditError):
            patch_csv(
                document,
                BytesIO(source),
                output,
                edits=(_edit(document, cells),),
            )
        assert output.getvalue() == b""


def test_stale_or_missing_cell_fails_before_output() -> None:
    source = b"a,b\nc,d\n"
    document = read_csv_ir(BytesIO(source), filename="data.csv")

    for cell in (
        {"row": 1, "column": 1, "old_text": "stale", "text": "x"},
        {"row": 9, "column": 9, "old_text": "missing", "text": "x"},
    ):
        output = BytesIO()
        with pytest.raises(PatchPreconditionError):
            patch_csv(
                document,
                BytesIO(source),
                output,
                edits=(_edit(document, [cell]),),
            )
        assert output.getvalue() == b""


def test_read_only_single_column_source_rejects_mutation() -> None:
    source = b"alpha\nbeta\n"
    document = read_csv_ir(BytesIO(source), filename="single.csv")
    output = BytesIO()

    with pytest.raises(UnsupportedEditError, match="read-only"):
        patch_csv(
            document,
            BytesIO(source),
            output,
            edits=(
                _edit(
                    document,
                    [{"row": 0, "column": 0, "old_text": "alpha", "text": "gamma"}],
                ),
            ),
        )

    assert output.getvalue() == b""


def test_forged_csv_locator_fails_before_output() -> None:
    source = b"a,b\nc,d\n"
    document = read_csv_ir(BytesIO(source), filename="data.csv")
    node = _table(document)
    forged_node = replace(
        node,
        native_locator=NativeLocator(
            backend="csv",
            part_uri="/other",
            object_id="table",
        ),
    )
    forged = replace(document, nodes={node.node_id: forged_node})
    output = BytesIO()
    edit = EditOperation(
        operation_id="edit",
        type="update_csv_cells",
        target_node_id=node.node_id,
        payload={
            "cells": [
                {"row": 1, "column": 1, "old_text": "d", "text": "x"}
            ]
        },
    )

    with pytest.raises(PatchPreconditionError, match="authoritative"):
        patch_csv(forged, BytesIO(source), output, edits=(edit,))

    assert output.getvalue() == b""


@pytest.mark.parametrize(
    ("source", "encoding", "replacement", "expected"),
    [
        (
            codecs.BOM_UTF8 + "name,city\r\nAndré,Paris\r\n".encode("utf-8"),
            None,
            "Lyon",
            codecs.BOM_UTF8 + "name,city\r\nAndré,Lyon\r\n".encode("utf-8"),
        ),
        (
            codecs.BOM_UTF16_LE + "name,city\r\nAndré,Paris\r\n".encode("utf-16-le"),
            None,
            "Lyon",
            codecs.BOM_UTF16_LE + "name,city\r\nAndré,Lyon\r\n".encode("utf-16-le"),
        ),
        (
            "name,city\r\nAndré,Paris\r\n".encode("cp1252"),
            "cp1252",
            "Lyon",
            "name,city\r\nAndré,Lyon\r\n".encode("cp1252"),
        ),
    ],
)
def test_csv_patch_preserves_source_encoding_and_bom(
    source: bytes,
    encoding: str | None,
    replacement: str,
    expected: bytes,
) -> None:
    document = read_csv_ir(
        BytesIO(source), filename="people.csv", encoding=encoding
    )
    output = BytesIO()

    patch_csv(
        document,
        BytesIO(source),
        output,
        edits=(
            _edit(
                document,
                [
                    {
                        "row": 1,
                        "column": 1,
                        "old_text": "Paris",
                        "text": replacement,
                    }
                ],
            ),
        ),
    )

    assert output.getvalue() == expected
