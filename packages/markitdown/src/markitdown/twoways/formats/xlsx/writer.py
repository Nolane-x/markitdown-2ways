from __future__ import annotations

from collections.abc import Sequence
from hashlib import sha256
from io import BytesIO
from typing import Any, BinaryIO
from zipfile import ZipFile

from ..._errors import PatchPreconditionError, UnsupportedEditError
from ..._results import FidelityEvidence, FidelityReport, FidelityStatus, WriterResult
from ...ir.document import DocumentIR
from ...ir.edits import EditOperation
from ...ir.nodes import TablePayload
from ...ir.semantics import validate_edit_preconditions
from ...ir.serialization import validate_document
from ...ir.sheet_edits import validate_sheet_cell_updates
from ...ooxml import parse_xml_part, snapshot_package, write_package
from ...ooxml.package import read_binary_stream, validate_source_authority
from ...writers.base import DocumentWriter, TargetInfo
from .cells import read_shared_string_table
from .model import XlsxPatchOptions
from .package import discover_xlsx_parts
from .patch import patch_worksheet_cells
from .verify import verify_xlsx_output


def _shared_strings(
    source_bytes: bytes,
    part_uri: str | None,
) -> tuple[tuple[str, ...], frozenset[int]]:
    if part_uri is None:
        return (), frozenset()
    with ZipFile(BytesIO(source_bytes), "r") as archive:
        try:
            data = archive.read(part_uri.lstrip("/"))
        except KeyError as exc:
            raise PatchPreconditionError(
                "XLSX shared strings part is missing from the source package.",
                details={"reason": "missing_shared_strings_part", "part_uri": part_uri},
            ) from exc
    return read_shared_string_table(parse_xml_part(data))


def _prepare_updates(
    document: DocumentIR,
    source_bytes: bytes,
    edits: tuple[EditOperation, ...],
) -> tuple[dict[str, tuple[object, tuple[dict[str, object], ...]]], tuple[str, ...],]:
    parts = discover_xlsx_parts(source_bytes)
    authoritative_parts = {worksheet.part_uri for worksheet in parts.worksheets}
    grouped: dict[str, tuple[object, list[dict[str, object]]]] = {}

    for edit in edits:
        if edit.type != "update_sheet_cells":
            raise UnsupportedEditError(
                "XLSX patch writer supports only update_sheet_cells in this tranche.",
                details={"reason": "unsupported_edit_type", "edit_type": edit.type},
            )
        if edit.target_node_id is None or edit.target_node_id not in document.nodes:
            raise PatchPreconditionError(
                "XLSX edit target node does not exist in the source IR.",
                details={
                    "reason": "missing_target",
                    "target_node_id": edit.target_node_id,
                },
            )
        node = document.nodes[edit.target_node_id]
        if not isinstance(node.payload, TablePayload):
            raise UnsupportedEditError(
                "update_sheet_cells requires an XLSX worksheet table node.",
                details={"reason": "wrong_node_kind", "target_node_id": node.node_id},
            )
        locator = node.native_locator
        if (
            locator is None
            or locator.backend != "xlsx"
            or not locator.part_uri
            or locator.part_uri not in authoritative_parts
        ):
            raise PatchPreconditionError(
                "XLSX edit target is not bound to an authoritative worksheet part.",
                details={
                    "reason": "missing_or_unauthorized_part_uri",
                    "target_node_id": node.node_id,
                    "part_uri": None if locator is None else locator.part_uri,
                },
            )
        validate_edit_preconditions(document, node, edit, format_label="XLSX")
        updates = validate_sheet_cell_updates(node.payload, edit.payload.get("cells"))
        existing = grouped.get(locator.part_uri)
        if existing is None:
            grouped[locator.part_uri] = (node, list(updates))
        else:
            existing[1].extend(updates)

    prepared: dict[str, tuple[object, tuple[dict[str, object], ...]]] = {}
    for part_uri in sorted(grouped):
        node, raw_updates = grouped[part_uri]
        assert isinstance(node.payload, TablePayload)
        combined = validate_sheet_cell_updates(node.payload, raw_updates)
        prepared[part_uri] = (node, combined)
    touched = tuple(part_uri.lstrip("/") for part_uri in sorted(prepared))
    return prepared, touched


def patch_xlsx(
    document: DocumentIR,
    source_stream: BinaryIO,
    output: BinaryIO,
    *,
    edits: Sequence[EditOperation],
    options: XlsxPatchOptions | None = None,
) -> WriterResult:
    options = options or XlsxPatchOptions()
    validate_document(document)
    source_bytes = read_binary_stream(source_stream, stream_label="XLSX source")
    validate_source_authority(document, source_bytes, expected_format="xlsx")
    snapshot = snapshot_package(source_bytes, limits=options.limits)
    edit_list = tuple(edits)

    if not edit_list:
        buffer = BytesIO()
        write_package(
            snapshot,
            source_bytes,
            buffer,
            replacements={},
            limits=options.limits,
        )
        output_bytes = buffer.getvalue()
        written = output.write(output_bytes)
        return WriterResult(
            format="xlsx",
            mode="patch",
            bytes_written=len(output_bytes) if written is None else written,
            fidelity=FidelityReport(
                claimed_tier="exact-preserve",
                evidence=(
                    FidelityEvidence(
                        check_code="archive.byte_identity",
                        status=FidelityStatus.PASSED,
                        description="No-op XLSX patch preserves source bytes exactly.",
                        expected=snapshot.source_sha256,
                        actual=sha256(output_bytes).hexdigest(),
                    ),
                ),
            ),
            metadata={"touched_parts": ()},
        )

    prepared, touched_parts = _prepare_updates(document, source_bytes, edit_list)
    parts = discover_xlsx_parts(source_bytes)
    shared_strings, rich_shared_string_indexes = _shared_strings(
        source_bytes,
        parts.shared_strings_part,
    )
    replacements: dict[str, bytes] = {}
    with ZipFile(BytesIO(source_bytes), "r") as archive:
        for part_uri in sorted(prepared):
            member = part_uri.lstrip("/")
            try:
                original = archive.read(member)
            except KeyError as exc:
                raise PatchPreconditionError(
                    "XLSX worksheet part referenced by the IR is missing.",
                    details={"reason": "missing_part", "part_uri": part_uri},
                ) from exc
            _, updates = prepared[part_uri]
            replacements[member] = patch_worksheet_cells(
                original,
                shared_strings=shared_strings,
                rich_shared_string_indexes=rich_shared_string_indexes,
                updates=updates,
            )

    buffer = BytesIO()
    write_package(
        snapshot,
        source_bytes,
        buffer,
        replacements=replacements,
        limits=options.limits,
    )
    output_bytes = buffer.getvalue()
    if options.verify_output:
        fidelity = verify_xlsx_output(
            document,
            source_bytes,
            output_bytes,
            edits=edit_list,
            touched_parts=touched_parts,
            limits=options.limits,
        )
    else:
        fidelity = FidelityReport(
            claimed_tier="unknown",
            warnings=("Round-trip verification was disabled by XlsxPatchOptions.",),
        )

    written = output.write(output_bytes)
    return WriterResult(
        format="xlsx",
        mode="patch",
        bytes_written=len(output_bytes) if written is None else written,
        fidelity=fidelity,
        metadata={"touched_parts": touched_parts},
    )


class XlsxPatchWriter(DocumentWriter):
    def accepts(self, document: DocumentIR, target: TargetInfo, **kwargs: Any) -> bool:
        return (
            document.source is not None
            and document.source.format == "xlsx"
            and (
                target.format.lower() == "xlsx"
                or (target.extension or "").lower() == ".xlsx"
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
        options = kwargs.pop("options", None)
        if source_stream is None or edits is None:
            raise TypeError("XlsxPatchWriter.write requires source_stream= and edits=")
        if kwargs:
            raise TypeError(f"unexpected XLSX writer options: {sorted(kwargs)}")
        return patch_xlsx(
            document,
            source_stream,
            output,
            edits=tuple(edits),
            options=options,
        )
