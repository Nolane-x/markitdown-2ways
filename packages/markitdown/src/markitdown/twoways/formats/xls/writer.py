from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, fields
from hashlib import sha256
import math
import struct
from typing import Any, BinaryIO

from ..._errors import (
    PatchPreconditionError,
    SourcePackageMismatchError,
    UnsupportedEditError,
)
from ..._results import FidelityEvidence, FidelityReport, FidelityStatus, WriterResult
from ...capabilities import CapabilityState, capabilities_for_node
from ...ir.document import DocumentIR
from ...ir.edits import EditOperation
from ...ir.nodes import Node, TableCell, TablePayload
from ...ir.semantics import validate_edit_preconditions
from ...ir.serialization import validate_document
from ...writers.base import DocumentWriter, TargetInfo
from .biff import parse_xls
from .limits import XlsLimits
from .model import ParsedXls, XlsFormatError, XlsNumberOwner, XlsSheet
from .verification import verify_xls_candidate

_XLS_READ_LIMITS_KEY = "xls.read_limits.v1"
_XLS_READ_LIMITS_SHA256_KEY = "xls.read_limits.sha256"

_BLOCKER_MESSAGES = {
    "xls.container.competing_book_stream": (
        "XLS has competing Book/Workbook stream authority and is read-only."
    ),
    "xls.workbook.encrypted": "XLS encrypted workbooks are read-only in H17.",
    "xls.workbook.formulas_present": (
        "XLS workbooks containing formulas are read-only in H17."
    ),
    "xls.sheet.unsupported_type": "XLS non-worksheet/dialog sheets are read-only in H17.",
    "xls.cell.duplicate_owner": "XLS has duplicate cell ownership and is read-only.",
    "xls.cell.non_finite": "XLS contains a non-finite NUMBER owner and is read-only.",
}


@dataclass(frozen=True)
class _PreparedCell:
    node: Node
    sheet: XlsSheet
    owner: XlsNumberOwner
    row: int
    column: int
    old_value: float
    value: float
    replacement: bytes

    @property
    def ranges(self) -> tuple[tuple[int, int], ...]:
        return tuple(
            (item.start, item.end) for item in self.owner.value_physical_ranges
        )

    @property
    def key(self) -> tuple[str, int, int]:
        return (self.sheet.name, self.row, self.column)


def _read_source_bytes(source: BinaryIO) -> bytes:
    data = source.read()
    if isinstance(data, str):
        raise TypeError("XLS source stream must return bytes")
    if not isinstance(data, (bytes, bytearray, memoryview)):
        raise TypeError("XLS source stream returned a non-bytes value")
    return bytes(data)


def _validate_source_authority(document: DocumentIR, source_bytes: bytes) -> None:
    source = document.source
    actual_digest = sha256(source_bytes).hexdigest()
    if source is None or source.format != "xls" or not source.sha256:
        raise SourcePackageMismatchError(
            "DocumentIR does not contain authoritative XLS source metadata.",
            details={"reason": "missing_source_authority", "actual": actual_digest},
        )
    if source.sha256 != actual_digest:
        raise SourcePackageMismatchError(
            "Provided XLS source does not match the DocumentIR source authority.",
            details={
                "reason": "source_digest_mismatch",
                "expected": source.sha256,
                "actual": actual_digest,
            },
        )
    if source.size_bytes is not None and source.size_bytes != len(source_bytes):
        raise SourcePackageMismatchError(
            "Provided XLS source size does not match the DocumentIR source authority.",
            details={
                "reason": "source_size_mismatch",
                "expected": source.size_bytes,
                "actual": len(source_bytes),
            },
        )


def _limit_field_names() -> tuple[str, ...]:
    return tuple(field.name for field in fields(XlsLimits))


def _limits_fingerprint(limits: XlsLimits) -> str:
    payload = "\n".join(
        f"{name}={getattr(limits, name)}" for name in _limit_field_names()
    ).encode("ascii")
    return sha256(payload).hexdigest()


def _read_time_limits(document: DocumentIR) -> XlsLimits:
    names = _limit_field_names()
    raw = document.metadata.custom.get(_XLS_READ_LIMITS_KEY)
    if not isinstance(raw, Mapping) or set(raw) != set(names):
        raise PatchPreconditionError(
            "XLS DocumentIR is missing authoritative read-time limits.",
            details={"reason": "xls_read_limits_missing_or_invalid"},
        )
    try:
        read_time = XlsLimits(**{name: raw[name] for name in names})
    except (KeyError, TypeError, ValueError) as exc:
        raise PatchPreconditionError(
            "XLS DocumentIR contains invalid authoritative read-time limits.",
            details={"reason": "xls_read_limits_missing_or_invalid"},
        ) from exc

    recorded = document.metadata.custom.get(_XLS_READ_LIMITS_SHA256_KEY)
    actual = _limits_fingerprint(read_time)
    if not isinstance(recorded, str) or recorded != actual:
        raise PatchPreconditionError(
            "XLS authoritative read-time limits are stale or forged.",
            details={
                "reason": "xls_read_limits_stale_or_forged",
                "expected": recorded,
                "actual": actual,
            },
        )
    return read_time


def _intersect_limits(requested: XlsLimits, read_time: XlsLimits) -> XlsLimits:
    return XlsLimits(
        **{
            name: min(getattr(requested, name), getattr(read_time, name))
            for name in _limit_field_names()
        }
    )


def _fresh_parse(source_bytes: bytes, limits: XlsLimits) -> ParsedXls:
    try:
        return parse_xls(source_bytes, limits=limits)
    except XlsFormatError as exc:
        raise PatchPreconditionError(
            "Authoritative XLS source no longer satisfies the H17 structural contract.",
            details={"reason": "xls.structure.invalid", "error": str(exc)},
        ) from exc


def _reject_fresh_authority(fresh: ParsedXls) -> None:
    if not fresh.blockers:
        return
    reason = fresh.blockers[0]
    raise UnsupportedEditError(
        _BLOCKER_MESSAGES.get(reason, "XLS source is read-only for H17 mutation."),
        details={"reason": reason},
    )


def _ranges_metadata(owner: XlsNumberOwner) -> list[dict[str, int]]:
    return [
        {"start": item.start, "length": item.length}
        for item in owner.value_physical_ranges
    ]


def _sheet_for_node(node: Node, fresh: ParsedXls) -> XlsSheet:
    if not isinstance(node.payload, TablePayload):
        raise UnsupportedEditError(
            "XLS update_sheet_cells requires a worksheet table node.",
            details={"reason": "wrong_node_kind", "target_node_id": node.node_id},
        )
    locator = node.native_locator
    if (
        locator is None
        or locator.backend != "xls"
        or locator.part_uri != "/Workbook"
        or not locator.name
    ):
        raise PatchPreconditionError(
            "XLS worksheet native locator is missing or stale.",
            details={"reason": "xls.sheet.stale_owner", "target_node_id": node.node_id},
        )

    matches = tuple(sheet for sheet in fresh.sheets if sheet.name == locator.name)
    if len(matches) != 1:
        raise PatchPreconditionError(
            "XLS worksheet native authority cannot be resolved uniquely.",
            details={"reason": "xls.sheet.stale_owner", "target_node_id": node.node_id},
        )
    sheet = matches[0]
    expected_attributes = {
        "sheet_type": sheet.sheet_type,
        "hidden_state": sheet.hidden_state,
        "bof_offset": sheet.bof_offset,
        "eof_offset": sheet.eof_offset,
    }
    for key, expected in expected_attributes.items():
        if locator.attributes.get(key) != expected:
            raise PatchPreconditionError(
                "XLS worksheet native locator is stale or forged.",
                details={
                    "reason": "xls.sheet.stale_owner",
                    "locator_key": key,
                    "expected": expected,
                    "actual": locator.attributes.get(key),
                },
            )

    expected_metadata = {
        "xls.sheet_name": sheet.name,
        "xls.sheet_type": sheet.sheet_type,
        "xls.hidden_state": sheet.hidden_state,
        "xls.bof_offset": sheet.bof_offset,
        "xls.eof_offset": sheet.eof_offset,
        "xls.is_dialog": sheet.is_dialog,
        "xls.cfb_topology_sha256": fresh.cfb.topology_sha256,
        "xls.biff_topology_sha256": fresh.biff_topology_sha256,
    }
    for key, expected in expected_metadata.items():
        if node.metadata.get(key) != expected:
            raise PatchPreconditionError(
                "XLS worksheet immutable native evidence is stale or forged.",
                details={
                    "reason": "xls.sheet.stale_owner",
                    "metadata_key": key,
                    "expected": expected,
                    "actual": node.metadata.get(key),
                },
            )

    decision = capabilities_for_node(node).for_operation("update_sheet_cells")
    if decision.state is not CapabilityState.WRITABLE:
        raise UnsupportedEditError(
            "XLS worksheet is read-only for update_sheet_cells.",
            details={
                "reason": decision.reason_code or "xls.capability.read_only",
                "target_node_id": node.node_id,
            },
        )
    return sheet


def _table_cell(node: Node, row: int, column: int) -> TableCell:
    assert isinstance(node.payload, TablePayload)
    matches = tuple(
        cell for cell in node.payload.cells if cell.row == row and cell.column == column
    )
    if len(matches) != 1:
        raise UnsupportedEditError(
            "XLS edit target does not resolve to one materialized cell.",
            details={
                "reason": "xls.cell.missing_number_owner",
                "row": row,
                "column": column,
            },
        )
    return matches[0]


def _owner_for_coordinate(
    sheet: XlsSheet,
    *,
    row: int,
    column: int,
) -> XlsNumberOwner:
    matches = tuple(
        owner
        for owner in sheet.number_owners
        if owner.row == row and owner.column == column
    )
    if len(matches) != 1:
        raise UnsupportedEditError(
            "XLS target coordinate does not have one writable NUMBER owner.",
            details={
                "reason": "xls.cell.missing_number_owner",
                "row": row,
                "column": column,
            },
        )
    return matches[0]


def _validate_cell_binding(
    cell: TableCell,
    owner: XlsNumberOwner,
) -> None:
    if (
        cell.metadata.get("xls.present") is not True
        or cell.metadata.get("xls.writable") is not True
        or cell.metadata.get("xls.native_record_kind") != "NUMBER"
    ):
        raise UnsupportedEditError(
            "XLS target coordinate is not a writable native NUMBER owner.",
            details={
                "reason": cell.metadata.get("xls.reason_code")
                or "xls.cell.unsupported_record_type",
                "row": owner.row,
                "column": owner.column,
            },
        )

    expected = {
        "xls.typed_value": owner.value,
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
    }
    for key, expected_value in expected.items():
        if cell.metadata.get(key) != expected_value:
            raise PatchPreconditionError(
                "XLS NUMBER native owner evidence is stale or forged.",
                details={
                    "reason": "xls.cell.stale_owner",
                    "metadata_key": key,
                    "expected": expected_value,
                    "actual": cell.metadata.get(key),
                    "row": owner.row,
                    "column": owner.column,
                },
            )


def _normalize_numeric(value: object) -> float:
    if isinstance(value, bool) or type(value) not in {int, float}:
        raise UnsupportedEditError(
            "XLS NUMBER replacement must be a numeric scalar and cannot be bool.",
            details={"reason": "xls.cell.invalid_numeric_value"},
        )
    if type(value) is int:
        try:
            normalized = float(value)
        except OverflowError as exc:
            raise UnsupportedEditError(
                "XLS integer replacement is outside finite binary64 range.",
                details={"reason": "xls.cell.numeric_out_of_range"},
            ) from exc
        if not math.isfinite(normalized) or int(normalized) != value:
            raise UnsupportedEditError(
                "XLS integer replacement must be exactly representable as binary64.",
                details={"reason": "xls.cell.integer_not_exact_binary64"},
            )
        return normalized

    normalized = float(value)
    if not math.isfinite(normalized):
        raise UnsupportedEditError(
            "XLS NUMBER replacement must be finite.",
            details={"reason": "xls.cell.non_finite"},
        )
    return normalized


def _prepare_edits(
    document: DocumentIR,
    fresh: ParsedXls,
    edits: tuple[EditOperation, ...],
) -> tuple[_PreparedCell, ...]:
    _reject_fresh_authority(fresh)
    prepared: list[_PreparedCell] = []
    seen: set[tuple[str, int, int]] = set()

    for edit in edits:
        if edit.type != "update_sheet_cells":
            raise UnsupportedEditError(
                "XLS H17 supports only update_sheet_cells.",
                details={"reason": "unsupported_edit_type", "edit_type": edit.type},
            )
        if edit.target_node_id is None or edit.target_node_id not in document.nodes:
            raise PatchPreconditionError(
                "XLS edit target node does not exist in the source IR.",
                details={
                    "reason": "missing_target",
                    "target_node_id": edit.target_node_id,
                },
            )
        node = document.nodes[edit.target_node_id]
        sheet = _sheet_for_node(node, fresh)
        validate_edit_preconditions(document, node, edit, format_label="XLS")

        raw_cells = edit.payload.get("cells")
        if not isinstance(raw_cells, (list, tuple)) or not raw_cells:
            raise UnsupportedEditError(
                "XLS update_sheet_cells requires a non-empty cells sequence.",
                details={"reason": "invalid_edit_payload"},
            )

        for raw in raw_cells:
            if not isinstance(raw, Mapping):
                raise UnsupportedEditError(
                    "XLS cell updates must be mappings.",
                    details={"reason": "invalid_edit_payload"},
                )
            row = raw.get("row")
            column = raw.get("column")
            if type(row) is not int or type(column) is not int:
                raise UnsupportedEditError(
                    "XLS cell coordinates must be integers.",
                    details={"reason": "invalid_edit_payload"},
                )
            if row < 0 or column < 0:
                raise UnsupportedEditError(
                    "XLS cell coordinates must be non-negative.",
                    details={"reason": "cell_out_of_range"},
                )

            key = (sheet.name, row, column)
            if key in seen:
                raise UnsupportedEditError(
                    "XLS edit set contains a duplicate coordinate.",
                    details={
                        "reason": "duplicate_cell_coordinate",
                        "sheet": sheet.name,
                        "row": row,
                        "column": column,
                    },
                )
            seen.add(key)

            cell = _table_cell(node, row, column)
            owner = _owner_for_coordinate(sheet, row=row, column=column)
            _validate_cell_binding(cell, owner)

            old_raw = raw.get("old_value")
            if isinstance(old_raw, bool) or type(old_raw) not in {int, float}:
                raise PatchPreconditionError(
                    "XLS old_value is not the authoritative numeric source value.",
                    details={"reason": "cell_old_value_mismatch"},
                )
            old_value = float(old_raw)
            if old_value != owner.value:
                raise PatchPreconditionError(
                    "XLS cell old_value no longer matches the source owner.",
                    details={
                        "reason": "cell_old_value_mismatch",
                        "sheet": sheet.name,
                        "row": row,
                        "column": column,
                        "expected": owner.value,
                        "actual": old_raw,
                    },
                )

            value = _normalize_numeric(raw.get("value"))
            if value == owner.value:
                raise UnsupportedEditError(
                    "XLS NUMBER edit must change the numeric value.",
                    details={
                        "reason": "no_op_cell_update",
                        "sheet": sheet.name,
                        "row": row,
                        "column": column,
                    },
                )
            replacement = struct.pack("<d", value)
            if struct.unpack("<d", replacement)[0] != value:
                raise UnsupportedEditError(
                    "XLS NUMBER replacement did not round-trip through binary64.",
                    details={"reason": "xls.cell.numeric_roundtrip_failed"},
                )

            prepared.append(
                _PreparedCell(
                    node=node,
                    sheet=sheet,
                    owner=owner,
                    row=row,
                    column=column,
                    old_value=old_value,
                    value=value,
                    replacement=replacement,
                )
            )

    ordered = tuple(sorted(prepared, key=lambda item: item.key))
    all_ranges: list[tuple[int, int]] = []
    for item in ordered:
        all_ranges.extend(item.ranges)
    previous_end = -1
    for start, end in sorted(all_ranges):
        if start < previous_end:
            raise PatchPreconditionError(
                "XLS NUMBER edit slots overlap unexpectedly.",
                details={"reason": "xls.cell.native_range_overlap"},
            )
        previous_end = end
    return ordered


def _apply_replacement(
    candidate: bytearray,
    prepared: _PreparedCell,
) -> None:
    cursor = 0
    for start, end in prepared.ranges:
        length = end - start
        candidate[start:end] = prepared.replacement[cursor : cursor + length]
        cursor += length
    if cursor != len(prepared.replacement):
        raise PatchPreconditionError(
            "XLS NUMBER physical mapping is incomplete.",
            details={"reason": "xls.cell.physical_mapping_incomplete"},
        )


def patch_xls(
    document: DocumentIR,
    source_stream: BinaryIO,
    output: BinaryIO,
    *,
    edits: Sequence[EditOperation],
    limits: XlsLimits | None = None,
) -> WriterResult:
    validate_document(document)
    source_bytes = _read_source_bytes(source_stream)
    _validate_source_authority(document, source_bytes)
    read_time_limits = _read_time_limits(document)
    active_limits = (
        read_time_limits
        if limits is None
        else _intersect_limits(limits, read_time_limits)
    )
    fresh = _fresh_parse(source_bytes, active_limits)
    edit_list = tuple(edits)

    if not edit_list:
        written = output.write(source_bytes)
        return WriterResult(
            format="xls",
            mode="patch",
            bytes_written=len(source_bytes) if written is None else written,
            fidelity=FidelityReport(
                claimed_tier="exact-preserve",
                evidence=(
                    FidelityEvidence(
                        check_code="xls.byte_identity",
                        status=FidelityStatus.PASSED,
                        description="No-op XLS patch preserves source bytes exactly.",
                        expected=sha256(source_bytes).hexdigest(),
                        actual=sha256(source_bytes).hexdigest(),
                    ),
                ),
            ),
            metadata={"touched_cells": (), "authorized_ranges": ()},
        )

    prepared = _prepare_edits(document, fresh, edit_list)
    candidate = bytearray(source_bytes)
    for item in prepared:
        _apply_replacement(candidate, item)
    candidate_bytes = bytes(candidate)

    authorized_ranges = tuple(
        sorted(range_item for item in prepared for range_item in item.ranges)
    )
    requested_values = {item.key: item.value for item in prepared}
    verify_xls_candidate(
        source_bytes,
        candidate_bytes,
        requested_values=requested_values,
        authorized_ranges=authorized_ranges,
        limits=active_limits,
    )
    fidelity = FidelityReport(
        claimed_tier="exact-preserve",
        evidence=(
            FidelityEvidence(
                check_code="xls.exact_outside_number_slots",
                status=FidelityStatus.PASSED,
                description=(
                    "Only authorized existing BIFF8 NUMBER value slots changed."
                ),
            ),
            FidelityEvidence(
                check_code="xls.semantic_readback",
                status=FidelityStatus.PASSED,
                description="Requested NUMBER values passed strict BIFF8 re-read.",
            ),
        ),
    )

    written = output.write(candidate_bytes)
    return WriterResult(
        format="xls",
        mode="patch",
        bytes_written=len(candidate_bytes) if written is None else written,
        fidelity=fidelity,
        metadata={
            "touched_cells": tuple(item.key for item in prepared),
            "authorized_ranges": authorized_ranges,
        },
    )


class XlsPatchWriter(DocumentWriter):
    def accepts(self, document: DocumentIR, target: TargetInfo, **kwargs: Any) -> bool:
        return (
            document.source is not None
            and document.source.format == "xls"
            and (
                target.format.lower() == "xls"
                or (target.extension or "").lower() == ".xls"
            )
        )

    def write(
        self,
        document: DocumentIR,
        output: BinaryIO,
        target: TargetInfo,
        **kwargs: Any,
    ) -> WriterResult:
        source_stream = kwargs.pop("source_stream", None)
        edits = kwargs.pop("edits", None)
        limits = kwargs.pop("limits", None)
        if source_stream is None or edits is None:
            raise TypeError("XlsPatchWriter.write requires source_stream= and edits=")
        if kwargs:
            raise TypeError(f"unexpected XLS writer options: {sorted(kwargs)}")
        return patch_xls(
            document,
            source_stream,
            output,
            edits=tuple(edits),
            limits=limits,
        )
