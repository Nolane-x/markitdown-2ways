from __future__ import annotations

from collections.abc import Sequence
from hashlib import sha256
from io import BytesIO
from typing import BinaryIO

from pypdf import PdfWriter
from pypdf.generic import DictionaryObject, IndirectObject, NameObject, TextStringObject

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
from .routing import (
    PdfRoutedLinkEdit,
    PdfRoutedMetadataEdit,
    PdfRoutedTextFieldEdit,
    resolve_pdf_link_uri_edit,
    resolve_pdf_metadata_edit,
    resolve_pdf_text_field_value_edit,
)
from .verification import verify_pdf_candidate

PdfRoutedEdit = PdfRoutedMetadataEdit | PdfRoutedLinkEdit | PdfRoutedTextFieldEdit


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
            # Preserve the H9 reason code as part of the public error contract.
            raise UnsupportedEditError(
                "PDF transaction contains a duplicate operation id.",
                details={
                    "reason": "pdf.metadata.duplicate_operation_id",
                    "operation_id": edit.operation_id,
                },
            )
        operation_ids.add(edit.operation_id)


def _cross_kind_owner_collision(
    owner_kinds: dict[tuple[int, int], str],
    owner: tuple[int, int],
    kind: str,
) -> bool:
    existing = owner_kinds.get(owner)
    return existing is not None and existing != kind


def _route_all(
    document: DocumentIR,
    source: bytes,
    edits: tuple[EditOperation, ...],
    limits: PdfNativeLimits,
) -> tuple[PdfRoutedEdit, ...]:
    routed: list[PdfRoutedEdit] = []
    metadata_fields: set[str] = set()
    link_targets: set[tuple[int, int]] = set()
    link_owners: set[tuple[int, int]] = set()
    form_targets: set[tuple[int, int]] = set()
    form_owners: set[tuple[int, int]] = set()
    owner_kinds: dict[tuple[int, int], str] = {}

    for edit in edits:
        if edit.type == "update_pdf_metadata":
            metadata = resolve_pdf_metadata_edit(document, source, edit, limits=limits)
            if metadata.field in metadata_fields:
                raise UnsupportedEditError(
                    "PDF metadata transaction contains a duplicate logical target.",
                    details={
                        "reason": "pdf.metadata.duplicate_target",
                        "field": metadata.field,
                    },
                )
            if _cross_kind_owner_collision(
                owner_kinds, metadata.info_objgen, "metadata"
            ):
                raise UnsupportedEditError(
                    "PDF transaction resolved different edit kinds to one native owner.",
                    details={
                        "reason": "pdf.writer.owner_collision",
                        "owner_objgen": metadata.info_objgen,
                    },
                )
            metadata_fields.add(metadata.field)
            owner_kinds[metadata.info_objgen] = "metadata"
            routed.append(metadata)
            continue

        if edit.type == "update_pdf_link_uri":
            link = resolve_pdf_link_uri_edit(document, source, edit, limits=limits)
            target = (link.page_index, link.annotation_index)
            if target in link_targets:
                raise UnsupportedEditError(
                    "PDF URI link transaction contains a duplicate logical target.",
                    details={
                        "reason": "pdf.link.duplicate_target",
                        "page_index": link.page_index,
                        "annotation_index": link.annotation_index,
                    },
                )
            if link.mutation_owner_objgen in link_owners:
                raise UnsupportedEditError(
                    "PDF URI link transaction resolved multiple edits to one native owner.",
                    details={
                        "reason": "pdf.link.owner_collision",
                        "owner_objgen": link.mutation_owner_objgen,
                    },
                )
            if _cross_kind_owner_collision(
                owner_kinds, link.mutation_owner_objgen, "link"
            ):
                raise UnsupportedEditError(
                    "PDF transaction resolved different edit kinds to one native owner.",
                    details={
                        "reason": "pdf.writer.owner_collision",
                        "owner_objgen": link.mutation_owner_objgen,
                    },
                )
            link_targets.add(target)
            link_owners.add(link.mutation_owner_objgen)
            owner_kinds[link.mutation_owner_objgen] = "link"
            routed.append(link)
            continue

        if edit.type == "update_pdf_text_field_value":
            form = resolve_pdf_text_field_value_edit(
                document, source, edit, limits=limits
            )
            target = form.field_objgen
            if target in form_targets:
                raise UnsupportedEditError(
                    "PDF form transaction contains a duplicate logical target.",
                    details={
                        "reason": "pdf.form.duplicate_target",
                        "field_name": form.field_name,
                    },
                )
            if form.field_objgen in form_owners:
                raise UnsupportedEditError(
                    "PDF form transaction resolved multiple edits to one native owner.",
                    details={
                        "reason": "pdf.form.owner_collision",
                        "owner_objgen": form.field_objgen,
                    },
                )
            if _cross_kind_owner_collision(owner_kinds, form.field_objgen, "form"):
                raise UnsupportedEditError(
                    "PDF transaction resolved different edit kinds to one native owner.",
                    details={
                        "reason": "pdf.writer.owner_collision",
                        "owner_objgen": form.field_objgen,
                    },
                )
            form_targets.add(target)
            form_owners.add(form.field_objgen)
            owner_kinds[form.field_objgen] = "form"
            routed.append(form)
            continue

        raise UnsupportedEditError(
            "PDF transaction contains an unsupported edit type.",
            details={"reason": "pdf.edit_type", "operation_id": edit.operation_id},
        )

    parsed = parse_pdf_source(source, limits=limits)
    requested_metadata = {
        item.field: item.value
        for item in routed
        if isinstance(item, PdfRoutedMetadataEdit)
    }
    final_metadata_total = sum(
        len(requested_metadata.get(field.field, field.value)) for field in parsed.fields
    )
    if final_metadata_total > limits.max_total_metadata_chars:
        raise UnsupportedEditError(
            "PDF metadata transaction exceeds the total text limit.",
            details={"reason": "pdf.metadata.total_too_large"},
        )

    requested_links = {
        (item.page_index, item.annotation_index): item.uri
        for item in routed
        if isinstance(item, PdfRoutedLinkEdit)
    }
    final_uri_total = sum(
        len(requested_links.get((link.page_index, link.annotation_index), link.uri))
        for link in parsed.links
    )
    if final_uri_total > limits.max_total_uri_chars:
        raise UnsupportedEditError(
            "PDF URI link transaction exceeds the total URI character limit.",
            details={"reason": "pdf.link.total_uri_too_large"},
        )

    requested_form_values = {
        item.field_objgen: item.value
        for item in routed
        if isinstance(item, PdfRoutedTextFieldEdit)
    }
    final_form_value_total = sum(
        len(requested_form_values.get(field.field_objgen, field.value))
        for field in parsed.form_fields
    )
    if final_form_value_total > limits.max_total_form_value_chars:
        raise UnsupportedEditError(
            "PDF form transaction exceeds the total form-value character limit.",
            details={"reason": "pdf.form.total_value_too_large"},
        )

    return tuple(routed)


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
                    description="Only explicitly authorized native PDF owners changed.",
                ),
                FidelityEvidence(
                    check_code="pdf.final_verification",
                    status=FidelityStatus.PASSED,
                    description="Strict PDF re-read verified requested native PDF semantics.",
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


def _owner_object(writer: PdfWriter, objgen: tuple[int, int]) -> DictionaryObject:
    reference = IndirectObject(objgen[0], objgen[1], writer)
    owner = reference.get_object()
    if not isinstance(owner, DictionaryObject):
        raise RoundTripVerificationError(
            "PDF native mutation owner did not resolve to a dictionary.",
            details={
                "reason": "pdf.writer.native_owner_drift",
                "owner_objgen": objgen,
                "owner_type": type(owner).__name__,
            },
        )
    return owner


def _apply_link_edit(writer: PdfWriter, item: PdfRoutedLinkEdit) -> None:
    owner = _owner_object(writer, item.mutation_owner_objgen)
    if item.owner_kind == "annotation":
        try:
            action = owner.raw_get("/A")
        except KeyError as exc:
            raise RoundTripVerificationError(
                "PDF link annotation lost its direct action dictionary.",
                details={"reason": "pdf.writer.native_owner_drift"},
            ) from exc
        if not isinstance(action, DictionaryObject):
            raise RoundTripVerificationError(
                "PDF link annotation action ownership drifted before mutation.",
                details={
                    "reason": "pdf.writer.native_owner_drift",
                    "action_type": type(action).__name__,
                },
            )
        action[NameObject("/URI")] = TextStringObject(item.uri)
        return

    if item.owner_kind == "action":
        owner[NameObject("/URI")] = TextStringObject(item.uri)
        return

    raise RoundTripVerificationError(
        "PDF URI link mutation owner kind is unsupported.",
        details={
            "reason": "pdf.writer.native_owner_drift",
            "owner_kind": item.owner_kind,
        },
    )


def _apply_form_edit(writer: PdfWriter, item: PdfRoutedTextFieldEdit) -> None:
    owner = _owner_object(writer, item.field_objgen)
    if str(owner.get("/FT")) != "/Tx" or str(owner.get("/Subtype")) != "/Widget":
        raise RoundTripVerificationError(
            "PDF form mutation owner field/widget type drifted before mutation.",
            details={"reason": "pdf.writer.native_owner_drift"},
        )
    if str(owner.get("/T")) != item.field_name:
        raise RoundTripVerificationError(
            "PDF form mutation owner field name drifted before mutation.",
            details={"reason": "pdf.writer.native_owner_drift"},
        )
    if "/AP" in owner or "/Parent" in owner or "/Kids" in owner:
        raise RoundTripVerificationError(
            "PDF form mutation owner left the H11 terminal no-appearance profile.",
            details={"reason": "pdf.writer.native_owner_drift"},
        )
    try:
        current_value = owner.raw_get("/V")
    except KeyError as exc:
        raise RoundTripVerificationError(
            "PDF form mutation owner lost its existing value.",
            details={"reason": "pdf.writer.native_owner_drift"},
        ) from exc
    if not isinstance(current_value, str) or str(current_value) != item.old_value:
        raise RoundTripVerificationError(
            "PDF form mutation owner value drifted before mutation.",
            details={"reason": "pdf.writer.native_owner_drift"},
        )
    owner[NameObject("/V")] = TextStringObject(item.value)


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
    metadata_edits = tuple(
        item for item in routed if isinstance(item, PdfRoutedMetadataEdit)
    )
    link_edits = tuple(item for item in routed if isinstance(item, PdfRoutedLinkEdit))
    form_edits = tuple(
        item for item in routed if isinstance(item, PdfRoutedTextFieldEdit)
    )

    try:
        writer = PdfWriter(BytesIO(source), incremental=True, strict=True)
        if metadata_edits:
            writer.add_metadata({item.key: item.value for item in metadata_edits})
        for item in link_edits:
            _apply_link_edit(writer, item)
        for item in form_edits:
            _apply_form_edit(writer, item)
        changed_objects = tuple(
            (reference.idnum, reference.generation)
            for reference in writer.list_objects_in_increment()
        )
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

    verify_pdf_candidate(
        source,
        candidate,
        routed,
        changed_objects=changed_objects,
        limits=limits,
    )
    output.write(candidate)
    return _result(len(candidate), zero_edit=False)
