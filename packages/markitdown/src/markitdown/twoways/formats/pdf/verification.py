from __future__ import annotations

from collections.abc import Mapping, Sequence
from io import BytesIO
from typing import Any

from pdfminer.pdfdocument import PDFDocument
from pdfminer.pdfparser import PDFParser
from pdfminer.utils import decode_text
from pypdf import PdfReader
from pypdf.generic import IndirectObject

from ..._errors import RoundTripVerificationError
from .limits import PdfNativeLimits
from .parser import parse_pdf_source
from .routing import PdfRoutedMetadataEdit

_SUPPORTED_FIELDS = ("Title", "Author", "Subject", "Keywords")


def _fail(reason: str, message: str, **details: object) -> None:
    raise RoundTripVerificationError(
        message,
        details={"reason": reason, **details},
    )


def _raw_get(mapping: object, key: str) -> object | None:
    raw_get = getattr(mapping, "raw_get", None)
    if callable(raw_get):
        try:
            return raw_get(key)
        except KeyError:
            return None
    try:
        return mapping[key]  # type: ignore[index]
    except (KeyError, TypeError):
        return None


def _canonical_pdf_value(value: Any) -> object:
    if isinstance(value, IndirectObject):
        return ("ref", value.idnum, value.generation)
    if isinstance(value, Mapping):
        return (
            "dict",
            tuple(
                sorted(
                    (str(key), _canonical_pdf_value(item))
                    for key, item in value.items()
                )
            ),
        )
    if isinstance(value, (list, tuple)):
        return ("array", tuple(_canonical_pdf_value(item) for item in value))
    if isinstance(value, bytes):
        return ("bytes", value.hex())
    if isinstance(value, str):
        return ("text", str(value))
    if isinstance(value, bool):
        return ("bool", value)
    if isinstance(value, int):
        return ("int", value)
    if isinstance(value, float):
        return ("float", value)
    if value is None:
        return ("null", None)
    return (type(value).__name__, repr(value))


def _info_inventory(data: bytes) -> dict[str, object]:
    try:
        reader = PdfReader(BytesIO(data), strict=True)
        info_ref = _raw_get(reader.trailer, "/Info")
        if not isinstance(info_ref, IndirectObject):
            _fail(
                "pdf.candidate.info_missing",
                "PDF candidate does not expose an indirect Document Information owner.",
            )
        info = info_ref.get_object()
        if not isinstance(info, Mapping):
            _fail(
                "pdf.candidate.info_missing",
                "PDF candidate Document Information owner is not a dictionary.",
            )
        return {str(key): _canonical_pdf_value(value) for key, value in info.items()}
    except RoundTripVerificationError:
        raise
    except Exception as exc:
        raise RoundTripVerificationError(
            "PDF Document Information inventory could not be established.",
            details={"reason": "pdf.candidate.reread_failed"},
        ) from exc


def _pdfminer_metadata(data: bytes) -> dict[str, str]:
    try:
        parser = PDFParser(BytesIO(data))
        document = PDFDocument(parser)
    except Exception as exc:
        raise RoundTripVerificationError(
            "pdfminer could not independently parse the PDF candidate.",
            details={"reason": "pdf.candidate.pdfminer_metadata"},
        ) from exc

    result: dict[str, str] = {}
    try:
        for info in document.info:
            for field in _SUPPORTED_FIELDS:
                if field in result or field not in info:
                    continue
                value = info[field]
                if isinstance(value, bytes):
                    result[field] = decode_text(value)
                elif isinstance(value, str):
                    result[field] = value
                else:
                    _fail(
                        "pdf.candidate.pdfminer_metadata",
                        "pdfminer exposed a non-text supported metadata value.",
                        field=field,
                        value_type=type(value).__name__,
                    )
    except RoundTripVerificationError:
        raise
    except Exception as exc:
        raise RoundTripVerificationError(
            "pdfminer metadata inspection failed.",
            details={"reason": "pdf.candidate.pdfminer_metadata"},
        ) from exc
    return result


def verify_pdf_candidate(
    source: bytes,
    candidate: bytes,
    routed: Sequence[PdfRoutedMetadataEdit],
    *,
    changed_objects: Sequence[tuple[int, int]],
    limits: PdfNativeLimits | None = None,
) -> None:
    limits = limits or PdfNativeLimits()
    routed = tuple(routed)
    changed_objects = tuple(changed_objects)

    if not candidate.startswith(source) or len(candidate) <= len(source):
        _fail(
            "pdf.candidate.source_prefix",
            "PDF incremental candidate does not preserve the exact source prefix.",
        )
    suffix_size = len(candidate) - len(source)
    if suffix_size > limits.max_increment_bytes:
        _fail(
            "pdf.writer.increment_too_large",
            "PDF incremental suffix exceeds the configured safety limit.",
            suffix_size=suffix_size,
            limit=limits.max_increment_bytes,
        )

    source_parsed = parse_pdf_source(source, limits=limits)
    candidate_parsed = parse_pdf_source(candidate, limits=limits)
    source_snapshot = source_parsed.snapshot
    candidate_snapshot = candidate_parsed.snapshot

    if source_snapshot.info_objgen is None:
        _fail(
            "pdf.metadata.info_missing",
            "Source PDF lacks an authoritative Document Information owner.",
        )
    authorized_owner = source_snapshot.info_objgen
    if set(changed_objects) != {authorized_owner}:
        _fail(
            "pdf.writer.unexpected_increment_object",
            "PDF incremental update changed an object outside the authorized /Info owner.",
            expected=(authorized_owner,),
            actual=changed_objects,
        )

    if candidate_snapshot.page_count != source_snapshot.page_count:
        _fail(
            "pdf.candidate.page_count",
            "PDF candidate changed the page count.",
            expected=source_snapshot.page_count,
            actual=candidate_snapshot.page_count,
        )
    if candidate_snapshot.root_objgen != source_snapshot.root_objgen:
        _fail(
            "pdf.candidate.root_authority",
            "PDF candidate changed the catalog root authority.",
            expected=source_snapshot.root_objgen,
            actual=candidate_snapshot.root_objgen,
        )
    if candidate_snapshot.info_objgen != authorized_owner:
        _fail(
            "pdf.candidate.info_authority",
            "PDF candidate changed the Document Information owner identity.",
            expected=authorized_owner,
            actual=candidate_snapshot.info_objgen,
        )

    source_policy = (
        source_snapshot.has_xmp,
        source_snapshot.encrypted,
        source_snapshot.has_signature,
        source_snapshot.has_certification,
        source_snapshot.linearized,
    )
    candidate_policy = (
        candidate_snapshot.has_xmp,
        candidate_snapshot.encrypted,
        candidate_snapshot.has_signature,
        candidate_snapshot.has_certification,
        candidate_snapshot.linearized,
    )
    if candidate_policy != source_policy:
        _fail(
            "pdf.candidate.policy_drift",
            "PDF candidate changed a security or metadata authority policy flag.",
            expected=source_policy,
            actual=candidate_policy,
        )

    requested = {item.field: item.value for item in routed}
    source_metadata = dict(source_snapshot.supported_metadata)
    candidate_metadata = dict(candidate_snapshot.supported_metadata)
    for field, value in requested.items():
        actual = candidate_metadata.get(field)
        if actual != value:
            _fail(
                "pdf.candidate.requested_semantic",
                "Requested PDF metadata value did not survive strict re-read.",
                field=field,
                expected=value,
                actual=actual,
            )
    for field, value in source_metadata.items():
        if field in requested:
            continue
        actual = candidate_metadata.get(field)
        if actual != value:
            _fail(
                "pdf.candidate.unrequested_metadata",
                "Unrequested supported PDF metadata changed.",
                field=field,
                expected=value,
                actual=actual,
            )

    source_info = _info_inventory(source)
    candidate_info = _info_inventory(candidate)
    requested_keys = {item.key for item in routed}
    source_untouched = {
        key: value for key, value in source_info.items() if key not in requested_keys
    }
    candidate_untouched = {
        key: value for key, value in candidate_info.items() if key not in requested_keys
    }
    if candidate_untouched != source_untouched:
        _fail(
            "pdf.candidate.unrequested_metadata",
            "Unrequested Document Information entries changed.",
            expected=source_untouched,
            actual=candidate_untouched,
        )

    independent = _pdfminer_metadata(candidate)
    for field in _SUPPORTED_FIELDS:
        expected = candidate_metadata.get(field)
        if expected is None:
            continue
        actual = independent.get(field)
        if actual != expected:
            _fail(
                "pdf.candidate.pdfminer_metadata",
                "pdfminer disagreed with the strict pypdf metadata interpretation.",
                field=field,
                expected=expected,
                actual=actual,
            )
