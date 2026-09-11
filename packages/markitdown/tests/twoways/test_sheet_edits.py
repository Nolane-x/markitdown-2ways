from __future__ import annotations

import math

import pytest

from markitdown.twoways._errors import PatchPreconditionError, UnsupportedEditError
from markitdown.twoways.ir.edits import INITIAL_EDIT_TYPES
from markitdown.twoways.ir.nodes import TableCell, TablePayload
from markitdown.twoways.ir.sheet_edits import (
    semantic_sheet_values_after_updates,
    validate_sheet_cell_updates,
)


def _sheet() -> TablePayload:
    return TablePayload(
        rows=2,
        columns=2,
        cells=(
            TableCell(
                row=0,
                column=0,
                text="North",
                metadata={"xlsx.typed_value": "North"},
            ),
            TableCell(
                row=0,
                column=1,
                text="7",
                metadata={"xlsx.typed_value": 7},
            ),
            TableCell(
                row=1,
                column=0,
                text="TRUE",
                metadata={"xlsx.typed_value": True},
            ),
            TableCell(
                row=1,
                column=1,
                text="",
                metadata={"xlsx.typed_value": None},
            ),
        ),
    )


def test_update_sheet_cells_is_a_known_edit_type() -> None:
    assert "update_sheet_cells" in INITIAL_EDIT_TYPES


def test_sheet_cell_updates_are_sorted_and_keep_typed_values() -> None:
    updates = validate_sheet_cell_updates(
        _sheet(),
        [
            {"row": 1, "column": 0, "old_value": True, "value": False},
            {"row": 0, "column": 1, "old_value": 7, "value": 9},
        ],
    )

    assert updates == (
        {"row": 0, "column": 1, "old_value": 7, "value": 9},
        {"row": 1, "column": 0, "old_value": True, "value": False},
    )


def test_sheet_semantics_apply_updates_without_stringifying_values() -> None:
    values = semantic_sheet_values_after_updates(
        _sheet(),
        [{"row": 1, "column": 1, "old_value": None, "value": 3.5}],
    )

    assert values == (("North", 7), (True, 3.5))


@pytest.mark.parametrize("raw_updates", [None, [], (), "not-a-sequence"])
def test_sheet_updates_require_a_non_empty_sequence(raw_updates: object) -> None:
    with pytest.raises(UnsupportedEditError, match="non-empty"):
        validate_sheet_cell_updates(_sheet(), raw_updates)


@pytest.mark.parametrize("coordinate", [True, False, 1.0, "1", None])
def test_sheet_coordinates_reject_bool_and_non_int_values(coordinate: object) -> None:
    with pytest.raises(UnsupportedEditError, match="coordinates must be integers"):
        validate_sheet_cell_updates(
            _sheet(),
            [{"row": coordinate, "column": 0, "old_value": "North", "value": "South"}],
        )


@pytest.mark.parametrize(("row", "column"), [(-1, 0), (0, -1), (2, 0), (0, 2)])
def test_sheet_updates_reject_out_of_range_coordinates(row: int, column: int) -> None:
    with pytest.raises(UnsupportedEditError) as exc_info:
        validate_sheet_cell_updates(
            _sheet(),
            [{"row": row, "column": column, "old_value": "North", "value": "South"}],
        )

    assert exc_info.value.details["reason"] == "cell_out_of_range"


def test_sheet_updates_reject_duplicate_coordinates() -> None:
    with pytest.raises(UnsupportedEditError) as exc_info:
        validate_sheet_cell_updates(
            _sheet(),
            [
                {"row": 0, "column": 0, "old_value": "North", "value": "South"},
                {"row": 0, "column": 0, "old_value": "North", "value": "West"},
            ],
        )

    assert exc_info.value.details["reason"] == "duplicate_cell_coordinate"


@pytest.mark.parametrize(
    ("row", "column", "old_value"),
    [
        (0, 0, "Stale"),
        (0, 1, 7.0),
        (1, 0, 1),
        (1, 1, ""),
    ],
)
def test_sheet_updates_require_exact_typed_old_value(
    row: int, column: int, old_value: object
) -> None:
    with pytest.raises(PatchPreconditionError) as exc_info:
        validate_sheet_cell_updates(
            _sheet(),
            [
                {
                    "row": row,
                    "column": column,
                    "old_value": old_value,
                    "value": "changed",
                }
            ],
        )

    assert exc_info.value.details["reason"] == "cell_old_value_mismatch"


@pytest.mark.parametrize(
    "value",
    [
        object(),
        ["list"],
        {"mapping": True},
        complex(1, 2),
        math.nan,
        math.inf,
        -math.inf,
    ],
)
def test_sheet_updates_reject_unsupported_values(value: object) -> None:
    with pytest.raises(UnsupportedEditError) as exc_info:
        validate_sheet_cell_updates(
            _sheet(),
            [{"row": 0, "column": 0, "old_value": "North", "value": value}],
        )

    assert exc_info.value.details["reason"] == "invalid_cell_value"


@pytest.mark.parametrize(
    ("row", "column", "value"),
    [
        (0, 0, "North"),
        (0, 1, 7),
        (1, 0, True),
        (1, 1, None),
    ],
)
def test_sheet_updates_reject_typed_no_ops(
    row: int, column: int, value: object
) -> None:
    with pytest.raises(UnsupportedEditError) as exc_info:
        validate_sheet_cell_updates(
            _sheet(),
            [{"row": row, "column": column, "old_value": value, "value": value}],
        )

    assert exc_info.value.details["reason"] == "no_op_cell_update"
