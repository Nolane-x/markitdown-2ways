from __future__ import annotations

import codecs
from collections.abc import Mapping, Sequence
from hashlib import sha256
from io import BytesIO
from typing import Any, BinaryIO

from ..._errors import (
    PatchPreconditionError,
    RoundTripVerificationError,
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
from ..text.codec import decode_text_source, encode_text_source
from ..text.model import TextRepresentation
from .lexical import resolve_csv_text
from .reader import read_csv_ir


_CELL_KEYS = frozenset({"row", "column", "old_text", "text"})


def _read_source_bytes(source: BinaryIO) -> bytes:
    data = source.read()
    if isinstance(data, str):
        raise TypeError("CSV source stream must return bytes")
    if not isinstance(data, (bytes, bytearray, memoryview)):
        raise TypeError("CSV source stream returned a non-bytes value")
    return bytes(data)


def _validate_source_authority(document: DocumentIR, source_bytes: bytes) -> None:
    source = document.source
    actual_digest = sha256(source_bytes).hexdigest()
    if source is None or source.format != "csv" or not source.sha256:
        raise SourcePackageMismatchError(
            "DocumentIR does not contain authoritative CSV source metadata.",
            details={"reason": "missing_source_authority", "actual": actual_digest},
        )
    if source.sha256 != actual_digest:
        raise SourcePackageMismatchError(
            "Provided CSV source does not match the DocumentIR source authority.",
            details={
                "reason": "source_digest_mismatch",
                "expected": source.sha256,
                "actual": actual_digest,
            },
        )
    if source.size_bytes is not None and source.size_bytes != len(source_bytes):
        raise SourcePackageMismatchError(
            "Provided CSV source size does not match the DocumentIR source authority.",
            details={
                "reason": "source_size_mismatch",
                "expected": source.size_bytes,
                "actual": len(source_bytes),
            },
        )


def _authoritative_table(document: DocumentIR) -> Node:
    if len(document.canvases) != 1 or len(document.canvases[0].root_node_ids) != 1:
        raise PatchPreconditionError(
            "CSV IR no longer has one authoritative table root.",
            details={"reason": "invalid_csv_root"},
        )
    node_id = document.canvases[0].root_node_ids[0]
    node = document.nodes.get(node_id)
    if node is None or not isinstance(node.payload, TablePayload) or node.kind != "table":
        raise PatchPreconditionError(
            "CSV IR root is not an authoritative table.",
            details={"reason": "invalid_csv_table"},
        )
    locator = node.native_locator
    if (
        locator is None
        or locator.backend != "csv"
        or locator.part_uri != "/"
        or locator.object_id != "table"
    ):
        raise PatchPreconditionError(
            "CSV edit target is not bound to the authoritative source table.",
            details={"reason": "missing_or_unauthorized_csv_locator"},
        )
    return node


def _representation(node: Node) -> TextRepresentation:
    try:
        encoding = node.metadata["csv.encoding"]
        bom = node.metadata["csv.bom"]
        byte_roundtrip = node.metadata["csv.byte_roundtrip"]
    except KeyError as exc:
        raise PatchPreconditionError(
            "CSV table is missing source representation metadata.",
            details={"reason": "missing_representation_metadata", "field": str(exc)},
        ) from exc
    if not isinstance(encoding, str) or not isinstance(bom, str):
        raise PatchPreconditionError(
            "CSV table contains invalid source representation metadata.",
            details={"reason": "invalid_representation_metadata"},
        )
    if not isinstance(byte_roundtrip, bool):
        raise PatchPreconditionError(
            "CSV byte-roundtrip metadata is invalid.",
            details={"reason": "invalid_representation_metadata"},
        )
    try:
        return TextRepresentation(
            encoding=encoding,
            bom=bom,
            newline="mixed",
            byte_roundtrip=byte_roundtrip,
        )
    except ValueError as exc:
        raise PatchPreconditionError(
            "CSV table contains unsupported source representation metadata.",
            details={"reason": "invalid_representation_metadata"},
        ) from exc


def _cell_map(payload: TablePayload) -> dict[tuple[int, int], TableCell]:
    result: dict[tuple[int, int], TableCell] = {}
    for cell in payload.cells:
        coordinate = (cell.row, cell.column)
        if coordinate in result:
            raise PatchPreconditionError(
                "CSV IR contains duplicate cell coordinates.",
                details={"reason": "duplicate_ir_coordinate", "coordinate": coordinate},
            )
        result[coordinate] = cell
    return result


def _validate_source_model(
    node: Node,
    source_bytes: bytes,
    representation: TextRepresentation,
) -> tuple[str, dict[tuple[int, int], Any]]:
    delimiter = node.metadata.get("csv.delimiter")
    if not isinstance(delimiter, str) or len(delimiter) != 1:
        raise PatchPreconditionError(
            "CSV delimiter metadata is invalid.",
            details={"reason": "invalid_csv_delimiter"},
        )
    source_text, actual_representation = decode_text_source(
        source_bytes,
        encoding=representation.encoding,
    )
    if (
        actual_representation.encoding != representation.encoding
        or actual_representation.bom != representation.bom
        or actual_representation.byte_roundtrip != representation.byte_roundtrip
    ):
        raise PatchPreconditionError(
            "CSV source representation no longer matches the authoritative IR.",
            details={"reason": "source_representation_mismatch"},
        )
    if encode_text_source(source_text, representation) != source_bytes:
        raise PatchPreconditionError(
            "CSV source bytes are not exactly reproducible from the authoritative representation.",
            details={"reason": "source_encoding_roundtrip_mismatch"},
        )

    lexical = resolve_csv_text(source_text, delimiter=delimiter)
    payload = node.payload
    assert isinstance(payload, TablePayload)
    cells = _cell_map(payload)
    lexical_fields = {
        (field.row, field.column): field for row in lexical.rows for field in row.fields
    }
    if set(lexical_fields) != set(cells):
        raise PatchPreconditionError(
            "CSV native coordinate set no longer matches the authoritative IR.",
            details={"reason": "coordinate_set_mismatch"},
        )
    if len(lexical.rows) != payload.rows:
        raise PatchPreconditionError(
            "CSV native row count no longer matches the authoritative IR.",
            details={"reason": "row_count_mismatch"},
        )
    columns = max((len(row.fields) for row in lexical.rows), default=0)
    if columns != payload.columns:
        raise PatchPreconditionError(
            "CSV native column width no longer matches the authoritative IR.",
            details={"reason": "column_count_mismatch"},
        )

    for coordinate, field in lexical_fields.items():
        cell = cells[coordinate]
        metadata = cell.metadata
        if (
            (cell.text or "") != field.value
            or metadata.get("csv.char_start") != field.start
            or metadata.get("csv.char_end") != field.end
            or metadata.get("csv.quoted") is not field.quoted
            or metadata.get("csv.multiline") is not field.multiline
            or metadata.get("csv.raw_digest") != field.raw_digest
            or metadata.get("csv.present") is not True
        ):
            raise PatchPreconditionError(
                "CSV native field evidence no longer matches the authoritative IR.",
                details={
                    "reason": "field_evidence_mismatch",
                    "coordinate": coordinate,
                },
            )
    return source_text, lexical_fields


def _validate_cell_change(item: Any) -> tuple[int, int, str, str]:
    if not isinstance(item, Mapping) or set(item) != _CELL_KEYS:
        raise UnsupportedEditError(
            "Each CSV cell update must contain exactly row, column, old_text and text.",
            details={"reason": "invalid_csv_cell_payload"},
        )
    row = item.get("row")
    column = item.get("column")
    old_text = item.get("old_text")
    new_text = item.get("text")
    if (
        type(row) is not int
        or type(column) is not int
        or row < 0
        or column < 0
        or not isinstance(old_text, str)
        or not isinstance(new_text, str)
    ):
        raise UnsupportedEditError(
            "CSV cell coordinates must be non-negative integers and texts must be strings.",
            details={"reason": "invalid_csv_cell_value"},
        )
    if old_text == new_text:
        raise UnsupportedEditError(
            "CSV cell update must change semantic text.",
            details={"reason": "csv_cell_noop", "coordinate": (row, column)},
        )
    if "\r" in new_text or "\n" in new_text:
        raise UnsupportedEditError(
            "CSV H2 does not permit newline insertion in replacement fields.",
            details={"reason": "csv.cell.multiline_replacement_unsupported"},
        )
    return row, column, old_text, new_text


def _prepare_changes(
    document: DocumentIR,
    node: Node,
    source_text: str,
    lexical_fields: dict[tuple[int, int], Any],
    edits: tuple[EditOperation, ...],
) -> tuple[tuple[int, int, Any, str], ...]:
    del source_text
    if len(edits) != 1:
        raise UnsupportedEditError(
            "CSV H2 supports one update_csv_cells operation per patch call.",
            details={"reason": "invalid_csv_edit_count", "count": len(edits)},
        )
    edit = edits[0]
    if edit.type != "update_csv_cells":
        raise UnsupportedEditError(
            "CSV patch writer supports only update_csv_cells.",
            details={"reason": "unsupported_edit_type", "edit_type": edit.type},
        )
    if edit.target_node_id != node.node_id:
        raise PatchPreconditionError(
            "CSV edit target does not match the authoritative table.",
            details={"reason": "target_mismatch"},
        )
    decision = capabilities_for_node(node).for_operation("update_csv_cells")
    if decision.state is not CapabilityState.WRITABLE:
        raise UnsupportedEditError(
            "CSV update_csv_cells capability is read-only for this source.",
            details={"reason": decision.reason_code or "capability.read_only"},
        )
    validate_edit_preconditions(document, node, edit, format_label="csv")

    if set(edit.payload) != {"cells"} or not isinstance(edit.payload.get("cells"), list):
        raise UnsupportedEditError(
            "update_csv_cells payload must contain exactly one cells list.",
            details={"reason": "invalid_csv_edit_payload"},
        )
    items = edit.payload["cells"]
    if not items:
        raise UnsupportedEditError(
            "update_csv_cells requires at least one changed coordinate.",
            details={"reason": "empty_csv_cell_updates"},
        )

    prepared: list[tuple[int, int, Any, str]] = []
    previous: tuple[int, int] | None = None
    for item in items:
        row, column, old_text, new_text = _validate_cell_change(item)
        coordinate = (row, column)
        if previous is not None and coordinate <= previous:
            raise UnsupportedEditError(
                "CSV cell updates must use unique ascending coordinates.",
                details={"reason": "csv_coordinates_not_strictly_ascending"},
            )
        previous = coordinate
        field = lexical_fields.get(coordinate)
        if field is None:
            raise PatchPreconditionError(
                "CSV edit coordinate has no native source field.",
                details={
                    "reason": "csv.cell.missing_native_field",
                    "coordinate": coordinate,
                },
            )
        if field.value != old_text:
            raise PatchPreconditionError(
                "CSV cell old_text is stale.",
                details={
                    "reason": "csv.cell.stale_old_text",
                    "coordinate": coordinate,
                    "actual": field.value,
                },
            )
        prepared.append((row, column, field, new_text))
    return tuple(prepared)


def _render_field(field: Any, text: str, delimiter: str) -> str:
    escaped = text.replace('"', '""')
    if field.quoted or delimiter in text or '"' in text:
        return f'"{escaped}"'
    return text


def _build_candidate(
    source_text: str,
    changes: tuple[tuple[int, int, Any, str], ...],
    delimiter: str,
) -> tuple[str, tuple[tuple[int, int, int, int], ...], set[tuple[int, int]]]:
    parts: list[str] = []
    untouched: list[tuple[int, int, int, int]] = []
    cursor = 0
    candidate_cursor = 0
    targets: set[tuple[int, int]] = set()

    by_span = sorted(changes, key=lambda item: item[2].start)
    for row, column, field, new_text in by_span:
        if field.start < cursor:
            raise PatchPreconditionError(
                "CSV target spans overlap or are out of order.",
                details={"reason": "overlapping_csv_target_spans"},
            )
        prefix = source_text[cursor : field.start]
        parts.append(prefix)
        untouched.append(
            (cursor, field.start, candidate_cursor, candidate_cursor + len(prefix))
        )
        candidate_cursor += len(prefix)
        rendered = _render_field(field, new_text, delimiter)
        parts.append(rendered)
        candidate_cursor += len(rendered)
        cursor = field.end
        targets.add((row, column))

    suffix = source_text[cursor:]
    parts.append(suffix)
    untouched.append((cursor, len(source_text), candidate_cursor, candidate_cursor + len(suffix)))
    return "".join(parts), tuple(untouched), targets


def _encoded_payload_and_boundaries(text: str, encoding: str) -> tuple[bytes, tuple[int, ...]]:
    encoder_type = codecs.getincrementalencoder(encoding)
    encoder = encoder_type(errors="strict")
    payload = bytearray()
    boundaries = [0]
    for character in text:
        payload.extend(encoder.encode(character, final=False))
        boundaries.append(len(payload))
    payload.extend(encoder.encode("", final=True))
    boundaries[-1] = len(payload)
    encoded = bytes(payload)
    expected = text.encode(encoding, errors="strict")
    if encoded != expected:
        raise RoundTripVerificationError(
            "Incremental CSV encoding disagrees with strict whole-text encoding.",
            details={"reason": "incremental_encoding_mismatch", "encoding": encoding},
        )
    return encoded, tuple(boundaries)


def _verify_untouched_bytes(
    source_bytes: bytes,
    candidate_bytes: bytes,
    source_text: str,
    candidate_text: str,
    representation: TextRepresentation,
    untouched: tuple[tuple[int, int, int, int], ...],
) -> None:
    original_payload, original_bounds = _encoded_payload_and_boundaries(
        source_text, representation.encoding
    )
    candidate_payload, candidate_bounds = _encoded_payload_and_boundaries(
        candidate_text, representation.encoding
    )
    original_bom_length = len(source_bytes) - len(original_payload)
    candidate_bom_length = len(candidate_bytes) - len(candidate_payload)
    if original_bom_length < 0 or candidate_bom_length < 0:
        raise RoundTripVerificationError(
            "CSV encoded payload is larger than its source byte stream.",
            details={"reason": "invalid_encoded_payload_boundary"},
        )
    if (
        source_bytes[:original_bom_length] != candidate_bytes[:candidate_bom_length]
        or original_bom_length != candidate_bom_length
        or source_bytes[original_bom_length:] != original_payload
        or candidate_bytes[candidate_bom_length:] != candidate_payload
    ):
        raise RoundTripVerificationError(
            "CSV BOM or encoded payload boundary changed unexpectedly.",
            details={"reason": "csv_encoding_boundary_mismatch"},
        )

    for old_start, old_end, new_start, new_end in untouched:
        old_bytes = original_payload[original_bounds[old_start] : original_bounds[old_end]]
        new_bytes = candidate_payload[candidate_bounds[new_start] : candidate_bounds[new_end]]
        if old_bytes != new_bytes:
            raise RoundTripVerificationError(
                "CSV bytes outside authorized target fields changed.",
                details={
                    "reason": "csv_untouched_bytes_changed",
                    "source_span": (old_start, old_end),
                    "candidate_span": (new_start, new_end),
                },
            )


def _payload_cell_map(payload: TablePayload) -> dict[tuple[int, int], TableCell]:
    return {(cell.row, cell.column): cell for cell in payload.cells}


def _verify_candidate(
    document: DocumentIR,
    node: Node,
    candidate_bytes: bytes,
    representation: TextRepresentation,
    delimiter: str,
    requested: dict[tuple[int, int], str],
) -> None:
    assert document.source is not None
    reread = read_csv_ir(
        BytesIO(candidate_bytes),
        filename=document.source.filename,
        mimetype=document.source.mimetype,
        encoding=representation.encoding,
        delimiter=delimiter,
    )
    candidate_node = reread.nodes[reread.canvases[0].root_node_ids[0]]
    if not isinstance(candidate_node.payload, TablePayload):
        raise RoundTripVerificationError(
            "Re-read CSV output did not produce a table payload.",
            details={"reason": "missing_csv_table_payload"},
        )
    original_payload = node.payload
    assert isinstance(original_payload, TablePayload)
    if (
        candidate_node.payload.rows != original_payload.rows
        or candidate_node.payload.columns != original_payload.columns
    ):
        raise RoundTripVerificationError(
            "CSV output changed row/column structure.",
            details={"reason": "csv_structure_changed"},
        )
    original_cells = _payload_cell_map(original_payload)
    candidate_cells = _payload_cell_map(candidate_node.payload)
    if set(original_cells) != set(candidate_cells):
        raise RoundTripVerificationError(
            "CSV output changed the native coordinate set.",
            details={"reason": "csv_coordinate_set_changed"},
        )

    for coordinate, original_cell in original_cells.items():
        expected_text = requested.get(coordinate, original_cell.text or "")
        if (candidate_cells[coordinate].text or "") != expected_text:
            raise RoundTripVerificationError(
                "CSV output failed semantic cell verification.",
                details={
                    "reason": "csv_cell_readback_mismatch",
                    "coordinate": coordinate,
                    "expected": expected_text,
                    "actual": candidate_cells[coordinate].text,
                },
            )
        if coordinate not in requested:
            for key in ("csv.quoted", "csv.multiline", "csv.raw_digest"):
                if candidate_cells[coordinate].metadata.get(key) != original_cell.metadata.get(key):
                    raise RoundTripVerificationError(
                        "CSV output changed an unrequested field lexeme.",
                        details={
                            "reason": "csv_unrequested_field_changed",
                            "coordinate": coordinate,
                            "field": key,
                        },
                    )

    for key in (
        "csv.delimiter",
        "csv.encoding",
        "csv.bom",
        "csv.row_terminators",
    ):
        if candidate_node.metadata.get(key) != node.metadata.get(key):
            raise RoundTripVerificationError(
                "CSV output changed source representation metadata.",
                details={"reason": "csv_representation_changed", "field": key},
            )


def patch_csv(
    document: DocumentIR,
    source_stream: BinaryIO,
    output: BinaryIO,
    *,
    edits: Sequence[EditOperation] = (),
) -> WriterResult:
    validate_document(document)
    source_bytes = _read_source_bytes(source_stream)
    _validate_source_authority(document, source_bytes)
    node = _authoritative_table(document)
    edit_list = tuple(edits)

    if not edit_list:
        written = output.write(source_bytes)
        return WriterResult(
            format="csv",
            mode="patch",
            bytes_written=len(source_bytes) if written is None else written,
            fidelity=FidelityReport(
                claimed_tier="exact-preserve",
                evidence=(
                    FidelityEvidence(
                        check_code="csv.byte_identity",
                        status=FidelityStatus.PASSED,
                        description="No-op CSV patch preserves source bytes exactly.",
                        expected=sha256(source_bytes).hexdigest(),
                        actual=sha256(source_bytes).hexdigest(),
                    ),
                ),
            ),
        )

    representation = _representation(node)
    source_text, lexical_fields = _validate_source_model(
        node, source_bytes, representation
    )
    changes = _prepare_changes(document, node, source_text, lexical_fields, edit_list)
    delimiter = node.metadata.get("csv.delimiter")
    assert isinstance(delimiter, str)
    candidate_text, untouched, targets = _build_candidate(
        source_text, changes, delimiter
    )
    candidate_bytes = encode_text_source(candidate_text, representation)
    _verify_untouched_bytes(
        source_bytes,
        candidate_bytes,
        source_text,
        candidate_text,
        representation,
        untouched,
    )
    requested = {(row, column): text for row, column, _field, text in changes}
    _verify_candidate(
        document,
        node,
        candidate_bytes,
        representation,
        delimiter,
        requested,
    )

    written = output.write(candidate_bytes)
    affected = tuple(f"r{row}c{column}" for row, column in sorted(targets))
    return WriterResult(
        format="csv",
        mode="patch",
        bytes_written=len(candidate_bytes) if written is None else written,
        fidelity=FidelityReport(
            claimed_tier="high",
            evidence=(
                FidelityEvidence(
                    check_code="csv.target_cell_readback",
                    status=FidelityStatus.PASSED,
                    description="Requested CSV cell semantics were verified after re-read.",
                    expected=requested,
                    actual=requested,
                    affected_node_ids=(node.node_id,),
                ),
                FidelityEvidence(
                    check_code="csv.untouched_byte_segments",
                    status=FidelityStatus.PASSED,
                    description="All encoded byte segments outside target fields stayed exact.",
                    affected_node_ids=(node.node_id,),
                ),
            ),
        ),
        metadata={"touched_cells": affected, "touched_nodes": (node.node_id,)},
    )


class CsvPatchWriter(DocumentWriter):
    def accepts(self, document: DocumentIR, target: TargetInfo, **kwargs: Any) -> bool:
        del kwargs
        source_format = document.source.format if document.source is not None else None
        return source_format == "csv" and (
            target.format.lower() == "csv" or (target.extension or "").lower() == ".csv"
        )

    def write(
        self,
        document: DocumentIR,
        output: BinaryIO,
        target: TargetInfo,
        **kwargs: Any,
    ) -> WriterResult:
        del target
        source_stream = kwargs.pop("source_stream", None)
        edits = kwargs.pop("edits", None)
        if source_stream is None or edits is None:
            raise TypeError("CsvPatchWriter.write requires source_stream= and edits=")
        if kwargs:
            raise TypeError(f"unexpected CSV writer options: {sorted(kwargs)}")
        return patch_csv(
            document,
            source_stream,
            output,
            edits=tuple(edits),
        )
