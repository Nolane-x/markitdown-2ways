from __future__ import annotations

from io import BytesIO

import pytest

from markitdown.twoways._errors import RoundTripVerificationError
from markitdown.twoways.formats.xls import patch_xls, read_xls_ir
from markitdown.twoways.formats.xls.verification import verify_xls_candidate
from markitdown.twoways.ir.edits import EditOperation

from ._xls_fixtures import make_xls_cfb


def _candidate(source: bytes):
    document = read_xls_ir(BytesIO(source), filename="legacy.xls")
    node = next(iter(document.nodes.values()))
    cell = next(cell for cell in node.payload.cells if cell.metadata["xls.present"])
    edit = EditOperation(
        operation_id="cell",
        type="update_sheet_cells",
        target_node_id=node.node_id,
        payload={
            "cells": [
                {
                    "row": cell.row,
                    "column": cell.column,
                    "old_value": cell.metadata["xls.typed_value"],
                    "value": 7.25,
                }
            ]
        },
    )
    output = BytesIO()
    patch_xls(document, BytesIO(source), output, edits=(edit,))
    ranges = tuple(
        (item["start"], item["start"] + item["length"])
        for item in cell.metadata["xls.value_physical_ranges"]
    )
    return output.getvalue(), ranges


def test_verifier_accepts_exact_number_slot_change() -> None:
    source = make_xls_cfb().data
    candidate, ranges = _candidate(source)

    verify_xls_candidate(
        source,
        candidate,
        requested_values={("Sheet1", 0, 0): 7.25},
        authorized_ranges=ranges,
    )


def test_verifier_rejects_drift_outside_authorized_ranges() -> None:
    source = make_xls_cfb().data
    candidate, ranges = _candidate(source)
    drifted = bytearray(candidate)
    drifted[10] ^= 0x01

    with pytest.raises(
        RoundTripVerificationError, match="outside|header|topology|drift"
    ):
        verify_xls_candidate(
            source,
            bytes(drifted),
            requested_values={("Sheet1", 0, 0): 7.25},
            authorized_ranges=ranges,
        )


def test_verifier_rejects_wrong_requested_value() -> None:
    source = make_xls_cfb().data
    candidate, ranges = _candidate(source)

    with pytest.raises(RoundTripVerificationError, match="semantic|value|requested"):
        verify_xls_candidate(
            source,
            candidate,
            requested_values={("Sheet1", 0, 0): 99.0},
            authorized_ranges=ranges,
        )


def test_verifier_rejects_wrong_authorized_range() -> None:
    source = make_xls_cfb().data
    candidate, ranges = _candidate(source)
    shifted = tuple((start + 1, end + 1) for start, end in ranges)

    with pytest.raises(RoundTripVerificationError, match="range|authorized"):
        verify_xls_candidate(
            source,
            candidate,
            requested_values={("Sheet1", 0, 0): 7.25},
            authorized_ranges=shifted,
        )


def test_verifier_rejects_candidate_length_drift() -> None:
    source = make_xls_cfb().data
    candidate, ranges = _candidate(source)

    with pytest.raises(RoundTripVerificationError, match="length|size"):
        verify_xls_candidate(
            source,
            candidate + b"\x00",
            requested_values={("Sheet1", 0, 0): 7.25},
            authorized_ranges=ranges,
        )
