from __future__ import annotations

from dataclasses import replace
from io import BytesIO

import pytest

from markitdown.twoways._errors import PatchPreconditionError, UnsupportedEditError
from markitdown.twoways.capabilities import (
    CAPABILITY_METADATA_KEY,
    CapabilityDecision,
    CapabilityState,
    encode_capabilities,
)
from markitdown.twoways.formats.xls import XlsLimits, patch_xls, read_xls_ir
from markitdown.twoways.ir.edits import EditOperation

from ._xls_fixtures import make_xls_cfb


def _sheet_node(document):
    return next(iter(document.nodes.values()))


def _edit(document, value: float = 2.5) -> EditOperation:
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


def _force_writable(document):
    node = _sheet_node(document)
    writable = encode_capabilities(
        (
            CapabilityDecision(
                operation="update_sheet_cells",
                state=CapabilityState.WRITABLE,
            ),
        )
    )
    forged_node = replace(
        node,
        metadata={**node.metadata, CAPABILITY_METADATA_KEY: writable},
    )
    return replace(
        document,
        nodes={**document.nodes, node.node_id: forged_node},
    )


def test_forged_writable_cannot_bypass_fresh_formula_blocker() -> None:
    source = make_xls_cfb(include_formula=True).data
    document = _force_writable(read_xls_ir(BytesIO(source), filename="legacy.xls"))
    output = BytesIO()

    with pytest.raises(UnsupportedEditError, match="formula|read-only"):
        patch_xls(
            document,
            BytesIO(source),
            output,
            edits=(_edit(document),),
        )

    assert output.getvalue() == b""


@pytest.mark.parametrize(
    ("metadata_key", "forged_value"),
    (
        ("xls.bof_offset", 999),
        ("xls.eof_offset", 999),
        ("xls.cfb_topology_sha256", "0" * 64),
        ("xls.biff_topology_sha256", "1" * 64),
    ),
)
def test_forged_sheet_native_evidence_fails_without_output(
    metadata_key: str,
    forged_value: object,
) -> None:
    source = make_xls_cfb().data
    document = read_xls_ir(BytesIO(source), filename="legacy.xls")
    node = _sheet_node(document)
    forged_node = replace(
        node,
        metadata={**node.metadata, metadata_key: forged_value},
    )
    forged = replace(
        document,
        nodes={**document.nodes, node.node_id: forged_node},
    )
    output = BytesIO()

    with pytest.raises(PatchPreconditionError, match="stale|forged|owner|evidence"):
        patch_xls(
            forged,
            BytesIO(source),
            output,
            edits=(_edit(forged),),
        )

    assert output.getvalue() == b""


def test_forged_persisted_read_limits_fail_without_output() -> None:
    source = make_xls_cfb().data
    limits = XlsLimits(max_biff_records=100)
    document = read_xls_ir(
        BytesIO(source),
        filename="legacy.xls",
        limits=limits,
    )
    custom = dict(document.metadata.custom)
    forged_limits = dict(custom["xls.read_limits.v1"])
    forged_limits["max_biff_records"] = 999
    custom["xls.read_limits.v1"] = forged_limits
    forged = replace(
        document,
        metadata=replace(document.metadata, custom=custom),
    )
    output = BytesIO()

    with pytest.raises(PatchPreconditionError, match="read.*limit|stale|forged"):
        patch_xls(
            forged,
            BytesIO(source),
            output,
            edits=(_edit(forged),),
        )

    assert output.getvalue() == b""


def test_caller_cannot_widen_read_time_record_budget() -> None:
    source = make_xls_cfb().data
    read_limits = XlsLimits(max_biff_records=100)
    document = read_xls_ir(
        BytesIO(source),
        filename="legacy.xls",
        limits=read_limits,
    )
    output = BytesIO()

    patch_xls(
        document,
        BytesIO(source),
        output,
        edits=(_edit(document),),
        limits=XlsLimits(max_biff_records=1000),
    )

    assert len(output.getvalue()) == len(source)


def test_tighter_caller_source_budget_fails_without_output() -> None:
    source = make_xls_cfb().data
    document = read_xls_ir(BytesIO(source), filename="legacy.xls")
    output = BytesIO()

    with pytest.raises(PatchPreconditionError, match="structure|source|limit"):
        patch_xls(
            document,
            BytesIO(source),
            output,
            edits=(_edit(document),),
            limits=XlsLimits(max_source_bytes=len(source) - 1),
        )

    assert output.getvalue() == b""
