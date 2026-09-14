from __future__ import annotations

from collections.abc import Sequence
from hashlib import sha256
from io import BytesIO
from typing import BinaryIO

from pypdf import PdfReader, PdfWriter

from ..._errors import (
    RoundTripVerificationError,
    SourcePackageMismatchError,
    UnsupportedEditError,
)
from ..._results import FidelityEvidence, FidelityReport, FidelityStatus, WriterResult
from ...ir.document import DocumentIR
from ...ir.edits import EditOperation
from ...ir.serialization import validate_document
from .limits import PdfNativeLimits
from .parser import parse_pdf_source
from .routing import PdfRoutedMetadataEdit, resolve_pdf_metadata_edit


def _read_source_bytes(source_stream: BinaryIO) -> bytes:
    source = source_stream.read()
    if isinstance(source, str):
        raise TypeError("PDF source stream must return bytes")
    if not isinstance(source, (bytes, bytearray, memoryview)):
        raise TypeError("PDF source stream returned a non-bytes value")
    return bytes(source)


def _validate_source_authority(document: DocumentIR, source: bytes) -> None:
    descriptor = document.source
    if descriptor is None:
        raise SourcePackageMismatchError(
            "PDF writeback requires source authority.",
            details={"reason": "missing_source_descriptor"},
        )
    if descriptor.format != "pdf":
        raise SourcePackageMismatchError(
            "PDF writeback source format does not match the DocumentIR.",
            details={"reason": "source_format", "actual": descriptor.format},
        )
    digest = sha256(source).hexdigest()
    if digest != descriptor.sha256:
        raise SourcePackageMismatchError(
            "PDF writeback source SHA-256 does not match the DocumentIR.",
            details={"reason": "source_sha256", "actual": digest},
        )
    if len(source) != descriptor.size_bytes:
        raise SourcePackageMismatchError(
            "PDF writeback source size does not match the DocumentIR.",
            details={"reason": "source_size", "actual": len(source)},
        )


def _validate_edit_set(edits: tuple[EditOperation, ...]) -> None:
    operation_ids: set[str] = set()
    for edit in edits:
        if edit.operation_id in operation_ids:
            raise UnsupportedEditError(
                "PDF metadata transaction contains a duplicate operation id.",
                details={
                    "reason": "pdf.metadata.duplicate_operation_id",
                    "operation_id": edit.operation_id,
                },
            )
        operation_ids.add(edit.operation_id)


def _route_all(
    document: DocumentIR,
    source: bytes,
    edits: tuple[EditOperation, ...],
    limits: PdfNativeLimits,
) -> tuple[PdfRoutedMetadataEdit, ...]:
    routed: list[PdfRoutedMetadataEdit] = []
    fields: set[str] = set()
    for edit in edits:
        item = resolve_pdf_metadata_edit(document, source, edit, limits=limits)
        if item.field in fields:
            raise UnsupportedEditError(
                "PDF metadata transaction contains a duplicate logical target.",
                details={"reason": "pdf.metadata.duplicate_target", "field": item.field},
            )
        fields.add(item.field)
        routed.append(item)

    parsed = parse_pdf_source(source, limits=limits)
    requested = {item.field: item.value for item in routed}
    final_total = sum(
        len(requested.get(field.field, field.value)) for field in parsed.fields
    )
    if final_total > limits.max_total_metadata_chars:
        raise UnsupportedEditError(
            "PDF metadata transaction exceeds the total text limit.",
            details={"reason": "pdf.metadata.total_too_large"},
        )
    return tuple(routed)


def _audit_increment(
    writer: PdfWriter,
    *,
    info_objgen: tuple[int, int],
) -> tuple[tuple[int, int], ...]:
    changed = tuple(
        (reference.idnum, reference.generation)
        for reference in writer.list_objects_in_increment()
    )
    if set(changed) != {info_objgen}:
        raise RoundTripVerificationError(
            "PDF incremental writer changed objects outside the authorized /Info owner.",
            details={
                "reason": "pdf.writer.unexpected_increment_object",
                "expected": (info_objgen,),
                "actual": changed,
            },
        )
    return changed


def _verify_basic_candidate(
    source: bytes,
    candidate: bytes,
    routed: tuple[PdfRoutedMetadataEdit, ...],
    *,
    limits: PdfNativeLimits,
) -> None:
    if not candidate.startswith(source) or len(candidate) <= len(source):
        raise RoundTripVerificationError(
            "PDF incremental candidate does not preserve the exact source prefix.",
            details={"reason": "pdf.candidate.source_prefix"},
        )
    suffix_size = len(candidate) - len(source)
    if suffix_size > limits.max_increment_bytes:
        raise RoundTripVerificationError(
            "PDF incremental suffix exceeds the configured safety limit.",
            details={
                "reason": "pdf.writer.increment_too_large",
                "suffix_size": suffix_size,
                "limit": limits.max_increment_bytes,
            },
        )

    try:
        metadata = PdfReader(BytesIO(candidate), strict=True).metadata
    except Exception as exc:
        raise RoundTripVerificationError(
            "PDF incremental candidate could not be re-read strictly.",
            details={"reason": "pdf.candidate.reread_failed"},
        ) from exc
    if metadata is None:
        raise RoundTripVerificationError(
            "PDF incremental candidate lost its Document Information dictionary.",
            details={"reason": "pdf.candidate.info_missing"},
        )
    for item in routed:
        actual = metadata.get(item.key)
        if actual != item.value:
            raise RoundTripVerificationError(
                "PDF requested metadata value did not survive strict re-read.",
                details={
                    "reason": "pdf.candidate.requested_semantic",
                    "field": item.field,
                    "expected": item.value,
                    "actual": actual,
                },
            )


def _result(bytes_written: int, *, zero_edit: bool) -> WriterResult:
    evidence = [
        FidelityEvidence(
            check_code="pdf.source_authority",
            status=FidelityStatus.PASSED,
            description="Source SHA-256 and byte size matched the DocumentIR authority.",
        )
    ]
    if zero_edit:
        evidence.append(
            FidelityEvidence(
                check_code="pdf.zero_edit_identity",
                status=FidelityStatus.PASSED,
                description="Zero-edit output reused the exact source PDF bytes.",
            )
        )
    else:
        evidence.extend(
            (
                FidelityEvidence(
                    check_code="pdf.incremental_source_prefix",
                    status=FidelityStatus.PASSED,
                    description="Mutation retained the exact source PDF as candidate prefix.",
                ),
                FidelityEvidence(
                    check_code="pdf.increment_object_audit",
                    status=FidelityStatus.PASSED,
                    description="Only the authorized Document Information object changed.",
                ),
                FidelityEvidence(
                    check_code="pdf.candidate_reread",
                    status=FidelityStatus.PASSED,
                    description="Requested metadata survived strict candidate re-read.",
                ),
            )
        )
    return WriterResult(
        format="pdf",
        mode="patch",
        bytes_written=bytes_written,
        fidelity=FidelityReport(
            claimed_tier="exact-preserve" if zero_edit else "high",
            evidence=tuple(evidence),
        ),
    )


def patch_pdf(
    document: DocumentIR,
    source_stream: BinaryIO,
    output: BinaryIO,
    *,
    edits: Sequence[EditOperation] = (),
    limits: PdfNativeLimits | None = None,
) -> WriterResult:
    validate_document(document)
    source = _read_source_bytes(source_stream)
    _validate_source_authority(document, source)
    limits = limits or PdfNativeLimits()
    edits = tuple(edits)

    if not edits:
        output.write(source)
        return _result(len(source), zero_edit=True)

    _validate_edit_set(edits)
    routed = _route_all(document, source, edits, limits)
    info_objgens = {item.info_objgen for item in routed}
    if len(info_objgens) != 1:
        raise UnsupportedEditError(
            "PDF metadata transaction resolved to ambiguous native owners.",
            details={"reason": "pdf.structure.authority_ambiguous"},
        )
    info_objgen = next(iter(info_objgens))

    try:
        writer = PdfWriter(BytesIO(source), incremental=True, strict=True)
        writer.add_metadata({item.key: item.value for item in routed})
        _audit_increment(writer, info_objgen=info_objgen)
        candidate_stream = BytesIO()
        writer.write(candidate_stream)
        candidate = candidate_stream.getvalue()
    except (UnsupportedEditError, RoundTripVerificationError):
        raise
    except Exception as exc:
        raise RoundTripVerificationError(
            "PDF incremental candidate construction failed.",
            details={"reason": "pdf.writer.incremental_write_failed"},
        ) from exc

    _verify_basic_candidate(source, candidate, routed, limits=limits)
    output.write(candidate)
    return _result(len(candidate), zero_edit=False)
