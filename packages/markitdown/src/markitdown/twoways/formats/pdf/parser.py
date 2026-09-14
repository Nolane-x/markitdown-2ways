from __future__ import annotations

from hashlib import sha256
from io import BytesIO
import re

from pypdf import PdfReader
from pypdf.errors import PdfReadError
from pypdf.generic import IndirectObject, TextStringObject

from .limits import PdfNativeLimits
from .model import (
    ParsedPdfSource,
    PdfInfoFieldEvidence,
    PdfParseError,
    PdfSourceSnapshot,
)

_SUPPORTED_FIELDS = {
    "Title": "/Title",
    "Author": "/Author",
    "Subject": "/Subject",
    "Keywords": "/Keywords",
}


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


def _objgen(value: object) -> tuple[int, int] | None:
    if isinstance(value, IndirectObject):
        return (value.idnum, value.generation)
    return None


def _detect_signature_policy(reader: PdfReader) -> tuple[bool, bool]:
    try:
        root = reader.root_object
    except Exception:
        return (False, False)

    has_certification = "/Perms" in root
    has_signature = False
    acroform_ref = _raw_get(root, "/AcroForm")
    try:
        acroform = acroform_ref.get_object() if isinstance(acroform_ref, IndirectObject) else acroform_ref
        fields = acroform.get("/Fields", ()) if hasattr(acroform, "get") else ()
        stack = list(fields or ())
        while stack:
            field_ref = stack.pop()
            field = field_ref.get_object() if isinstance(field_ref, IndirectObject) else field_ref
            if not hasattr(field, "get"):
                continue
            if field.get("/FT") == "/Sig" or "/V" in field and field.get("/FT") == "/Sig":
                has_signature = True
                break
            kids = field.get("/Kids", ())
            stack.extend(kids or ())
    except Exception:
        has_signature = True
    return (has_signature, has_certification)


def parse_pdf_source(
    source: bytes,
    *,
    limits: PdfNativeLimits | None = None,
) -> ParsedPdfSource:
    limits = limits or PdfNativeLimits()
    if not isinstance(source, bytes):
        raise TypeError("PDF source must be bytes")
    if len(source) > limits.max_source_bytes:
        raise PdfParseError(
            "PDF source exceeds the configured byte limit.",
            reason="pdf.source.too_large",
            details={"source_size": len(source), "limit": limits.max_source_bytes},
        )
    if not source.startswith(b"%PDF-"):
        raise PdfParseError(
            "Source does not contain a valid PDF header.",
            reason="pdf.source.malformed",
        )

    try:
        reader = PdfReader(BytesIO(source), strict=True)
        encrypted = bool(reader.is_encrypted)
        if encrypted:
            page_count = 0
        else:
            page_count = len(reader.pages)
    except (PdfReadError, ValueError, TypeError, KeyError, EOFError) as exc:
        raise PdfParseError(
            "Unable to establish strict PDF source authority.",
            reason="pdf.source.malformed",
        ) from exc

    if page_count > limits.max_pages:
        raise PdfParseError(
            "PDF page count exceeds the configured limit.",
            reason="pdf.source.too_many_pages",
            details={"page_count": page_count, "limit": limits.max_pages},
        )

    trailer = reader.trailer
    info_ref = _raw_get(trailer, "/Info")
    info_objgen = _objgen(info_ref)
    diagnostics: list[str] = []
    fields: list[PdfInfoFieldEvidence] = []
    supported_metadata: dict[str, str] = {}

    if info_ref is None or info_objgen is None:
        diagnostics.append("pdf.metadata.info_missing")
        info = None
    else:
        try:
            info = info_ref.get_object()
        except Exception:
            info = None
            diagnostics.append("pdf.structure.authority_ambiguous")

    total_chars = 0
    unsupported_value_type = False
    if info is not None:
        for field, key in _SUPPORTED_FIELDS.items():
            raw_value = _raw_get(info, key)
            if raw_value is None:
                continue
            if not isinstance(raw_value, TextStringObject):
                unsupported_value_type = True
                diagnostics.append("pdf.metadata.unsupported_value_type")
                continue
            value = str(raw_value)
            if len(value) > limits.max_metadata_value_chars:
                diagnostics.append("pdf.metadata.value_too_large")
                continue
            total_chars += len(value)
            supported_metadata[field] = value
            fields.append(
                PdfInfoFieldEvidence(
                    field=field,
                    key=key,
                    value=value,
                    info_objgen=info_objgen,
                    object_type=type(raw_value).__name__,
                )
            )

    if total_chars > limits.max_total_metadata_chars:
        diagnostics.append("pdf.metadata.total_too_large")

    linearized = bool(re.search(rb"/Linearized\b", source[:4096]))
    if linearized:
        diagnostics.append("pdf.structure.linearized")

    has_xmp = False
    has_signature = False
    has_certification = False
    if not encrypted:
        try:
            root = reader.root_object
            has_xmp = "/Metadata" in root
        except Exception:
            diagnostics.append("pdf.structure.authority_ambiguous")
        has_signature, has_certification = _detect_signature_policy(reader)

    if encrypted:
        diagnostics.append("pdf.security.encrypted")
    if has_xmp:
        diagnostics.append("pdf.metadata.xmp_conflict")
    if has_signature:
        diagnostics.append("pdf.security.signature_present")
    if has_certification:
        diagnostics.append("pdf.security.certification_present")

    blocking = {
        "pdf.metadata.info_missing",
        "pdf.metadata.xmp_conflict",
        "pdf.metadata.unsupported_value_type",
        "pdf.metadata.value_too_large",
        "pdf.metadata.total_too_large",
        "pdf.security.encrypted",
        "pdf.security.signature_present",
        "pdf.security.certification_present",
        "pdf.structure.linearized",
        "pdf.structure.authority_ambiguous",
    }
    writable = bool(fields) and not unsupported_value_type and not any(
        reason in blocking for reason in diagnostics
    )

    header_line = source.splitlines()[0].decode("ascii", errors="replace")
    snapshot = PdfSourceSnapshot(
        source_sha256=sha256(source).hexdigest(),
        source_size=len(source),
        pdf_header=header_line,
        page_count=page_count,
        info_objgen=info_objgen,
        supported_metadata=supported_metadata,
        has_xmp=has_xmp,
        encrypted=encrypted,
        has_signature=has_signature,
        has_certification=has_certification,
        linearized=linearized,
    )
    return ParsedPdfSource(
        snapshot=snapshot,
        fields=tuple(fields),
        writable=writable,
        diagnostics=tuple(dict.fromkeys(diagnostics)),
    )
