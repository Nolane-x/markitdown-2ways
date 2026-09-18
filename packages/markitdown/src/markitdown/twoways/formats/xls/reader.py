from __future__ import annotations

from dataclasses import fields
from hashlib import sha256
from typing import Any, BinaryIO

from ...capabilities import (
    CAPABILITY_METADATA_KEY,
    CapabilityDecision,
    CapabilityState,
    encode_capabilities,
)
from ...ir.document import Canvas, DocumentIR, DocumentMetadata, SourceDescriptor
from ...ir.nodes import Node, TableCell, TablePayload
from ...ir.provenance import NativeLocator, Provenance
from ...ir.serialization import validate_document
from ...readers.base import DocumentIRReader
from .limits import XlsLimits
from .model import XlsNumberOwner, XlsSheet
from .biff import parse_xls

_XLS_READ_LIMITS_KEY = "xls.read_limits.v1"
_XLS_READ_LIMITS_SHA256_KEY = "xls.read_limits.sha256"
_MAX_MATERIALIZED_GRID_CELLS = 100_000
_GRID_TOO_LARGE_REASON = "xls.sheet.grid_too_large_to_materialize"


def _read_source_bytes(source: BinaryIO) -> bytes:
    data = source.read()
    if isinstance(data, str):
        raise TypeError("XLS source stream must return bytes")
    if not isinstance(data, (bytes, bytearray, memoryview)):
        raise TypeError("XLS source stream returned a non-bytes value")
    return bytes(data)


def _limit_field_names() -> tuple[str, ...]:
    return tuple(field.name for field in fields(XlsLimits))


def _limits_metadata(limits: XlsLimits) -> dict[str, int]:
    return {name: getattr(limits, name) for name in _limit_field_names()}


def _limits_fingerprint(limits: XlsLimits) -> str:
    payload = "\n".join(
        f"{name}={getattr(limits, name)}" for name in _limit_field_names()
    ).encode("ascii")
    return sha256(payload).hexdigest()


def _ranges_metadata(owner: XlsNumberOwner) -> list[dict[str, int]]:
    return [
        {"start": item.start, "length": item.length}
        for item in owner.value_physical_ranges
    ]


def _owner_cell(
    owner: XlsNumberOwner,
    *,
    writable: bool,
    reason: str | None,
) -> TableCell:
    return TableCell(
        row=owner.row,
        column=owner.column,
        text=str(owner.value),
        metadata={
            "xls.typed_value": owner.value,
            "xls.present": True,
            "xls.writable": writable,
            "xls.reason_code": None if writable else reason,
            "xls.native_record_kind": "NUMBER",
            "xls.row": owner.row,
            "xls.column": owner.column,
            "xls.xf_index": owner.xf_index,
            "xls.record_index": owner.record.index,
            "xls.record_offset": owner.record.header_offset,
            "xls.record_size": owner.record.payload_size,
            "xls.record_sha256": owner.record_sha256,
            "xls.value_logical_offset": owner.value_logical_offset,
            "xls.value_sha256": owner.value_sha256,
            "xls.value_physical_ranges": _ranges_metadata(owner),
        },
    )


def _missing_cell(row: int, column: int) -> TableCell:
    return TableCell(
        row=row,
        column=column,
        text="",
        metadata={
            "xls.typed_value": None,
            "xls.present": False,
            "xls.writable": False,
            "xls.reason_code": "xls.cell.missing_number_owner",
        },
    )


def _sheet_node(
    sheet: XlsSheet,
    *,
    source_digest: str,
    canvas_id: str,
    canvas_index: int,
    blocker: str | None,
    cfb_topology_sha256: str,
    biff_topology_sha256: str,
) -> Node:
    max_row = max((owner.row for owner in sheet.number_owners), default=0)
    max_column = max((owner.column for owner in sheet.number_owners), default=0)
    rows = max_row + 1
    columns = max_column + 1
    dense = rows * columns <= _MAX_MATERIALIZED_GRID_CELLS
    owner_by_coordinate = {
        (owner.row, owner.column): owner for owner in sheet.number_owners
    }

    forced_reason = blocker
    if not dense:
        forced_reason = _GRID_TOO_LARGE_REASON

    cells: list[TableCell] = []
    if dense:
        for row in range(rows):
            for column in range(columns):
                owner = owner_by_coordinate.get((row, column))
                if owner is None:
                    cells.append(_missing_cell(row, column))
                else:
                    cells.append(
                        _owner_cell(
                            owner,
                            writable=forced_reason is None,
                            reason=forced_reason,
                        )
                    )
    else:
        cells.extend(
            _owner_cell(
                owner,
                writable=False,
                reason=_GRID_TOO_LARGE_REASON,
            )
            for owner in sheet.number_owners
        )

    if forced_reason is not None:
        decision = CapabilityDecision(
            operation="update_sheet_cells",
            state=CapabilityState.READ_ONLY,
            reason_code=forced_reason,
        )
    elif sheet.number_owners:
        decision = CapabilityDecision(
            operation="update_sheet_cells",
            state=CapabilityState.WRITABLE,
            constraints={
                "identity_markdown": False,
                "existing_number_owner_only": True,
                "fixed_slot_bytes": 8,
                "record_topology_immutable": True,
                "cfb_topology_immutable": True,
                "source_preservation": "xls-exact-outside-number-slots",
                "writable_cells": len(sheet.number_owners),
            },
        )
    else:
        decision = CapabilityDecision(
            operation="update_sheet_cells",
            state=CapabilityState.READ_ONLY,
            reason_code="xls.sheet.no_writable_number_cells",
        )

    node_id = (
        "xls-sheet-"
        + sha256(
            f"{source_digest}:{canvas_index}:{sheet.name}:{sheet.bof_offset}".encode(
                "utf-8"
            )
        ).hexdigest()[:24]
    )
    locator = NativeLocator(
        backend="xls",
        part_uri="/Workbook",
        object_id=f"sheet-bof:{sheet.bof_offset}",
        name=sheet.name,
        attributes={
            "sheet_type": sheet.sheet_type,
            "hidden_state": sheet.hidden_state,
            "bof_offset": sheet.bof_offset,
            "eof_offset": sheet.eof_offset,
        },
    )
    return Node(
        node_id=node_id,
        kind="table",
        semantic_role="worksheet-grid",
        order=0,
        canvas_id=canvas_id,
        provenance=(
            Provenance(
                source_format="xls",
                canvas_index=canvas_index,
                part_uri="/Workbook",
                extraction_method="biff8-number-fixed-slot",
                metadata={"sheet_name": sheet.name, "bof_offset": sheet.bof_offset},
            ),
        ),
        native_locator=locator,
        payload=TablePayload(rows=rows, columns=columns, cells=tuple(cells)),
        metadata={
            "xls.sheet_name": sheet.name,
            "xls.sheet_index": canvas_index,
            "xls.sheet_type": sheet.sheet_type,
            "xls.hidden_state": sheet.hidden_state,
            "xls.bof_offset": sheet.bof_offset,
            "xls.eof_offset": sheet.eof_offset,
            "xls.is_dialog": sheet.is_dialog,
            "xls.cfb_topology_sha256": cfb_topology_sha256,
            "xls.biff_topology_sha256": biff_topology_sha256,
            CAPABILITY_METADATA_KEY: encode_capabilities((decision,)),
        },
    )


def read_xls_ir(
    source: BinaryIO,
    *,
    filename: str | None = None,
    mimetype: str | None = None,
    limits: XlsLimits | None = None,
) -> DocumentIR:
    active_limits = limits or XlsLimits()
    source_bytes = _read_source_bytes(source)
    parsed = parse_xls(source_bytes, limits=active_limits)
    source_digest = sha256(source_bytes).hexdigest()
    blocker = parsed.blockers[0] if parsed.blockers else None

    nodes: dict[str, Node] = {}
    canvases: list[Canvas] = []
    root_node_ids: list[str] = []
    for index, sheet in enumerate(parsed.sheets):
        canvas_id = f"xls-worksheet-{index}"
        node = _sheet_node(
            sheet,
            source_digest=source_digest,
            canvas_id=canvas_id,
            canvas_index=index,
            blocker=blocker,
            cfb_topology_sha256=parsed.cfb.topology_sha256,
            biff_topology_sha256=parsed.biff_topology_sha256,
        )
        nodes[node.node_id] = node
        root_node_ids.append(node.node_id)
        canvases.append(
            Canvas(
                canvas_id=canvas_id,
                index=index,
                kind="worksheet",
                name=sheet.name,
                root_node_ids=(node.node_id,),
                native_locator=node.native_locator,
            )
        )

    document = DocumentIR(
        document_id=f"xls-document-{source_digest[:24]}",
        source=SourceDescriptor(
            format="xls",
            filename=filename,
            mimetype=mimetype,
            sha256=source_digest,
            size_bytes=len(source_bytes),
            preserved_source_ref=f"xls:sha256:{source_digest}",
        ),
        metadata=DocumentMetadata(
            custom={
                _XLS_READ_LIMITS_KEY: _limits_metadata(active_limits),
                _XLS_READ_LIMITS_SHA256_KEY: _limits_fingerprint(active_limits),
                "xls.cfb_topology_sha256": parsed.cfb.topology_sha256,
                "xls.biff_topology_sha256": parsed.biff_topology_sha256,
            }
        ),
        canvases=tuple(canvases),
        nodes=nodes,
        root_node_ids=tuple(root_node_ids),
    )
    validate_document(document)
    return document


class XlsIRReader(DocumentIRReader):
    def accepts(self, file_stream: BinaryIO, stream_info: Any, **kwargs: Any) -> bool:
        extension = (getattr(stream_info, "extension", None) or "").lower()
        mimetype = (
            (getattr(stream_info, "mimetype", None) or "")
            .split(";", 1)[0]
            .strip()
            .lower()
        )
        return extension == ".xls" or mimetype in {
            "application/vnd.ms-excel",
            "application/excel",
        }

    def read(
        self,
        file_stream: BinaryIO,
        stream_info: Any,
        **kwargs: Any,
    ) -> DocumentIR:
        limits = kwargs.pop("limits", None)
        if kwargs:
            raise TypeError(f"unexpected XLS reader options: {sorted(kwargs)}")
        return read_xls_ir(
            file_stream,
            filename=getattr(stream_info, "filename", None),
            mimetype=getattr(stream_info, "mimetype", None),
            limits=limits,
        )
