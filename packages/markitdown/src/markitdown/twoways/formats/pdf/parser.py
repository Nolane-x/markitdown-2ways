from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
from io import BytesIO
import re

from pypdf import PdfReader
from pypdf.errors import PdfReadError
from pypdf.generic import (
    ArrayObject,
    DictionaryObject,
    IndirectObject,
    TextStringObject,
)

from .limits import PdfNativeLimits
from .model import (
    ParsedPdfSource,
    PdfInfoFieldEvidence,
    PdfLinkEvidence,
    PdfParseError,
    PdfSourceSnapshot,
)

_SUPPORTED_FIELDS = {
    "Title": "/Title",
    "Author": "/Author",
    "Subject": "/Subject",
    "Keywords": "/Keywords",
}

_LINK_SOURCE_BLOCKERS = frozenset(
    {
        "pdf.metadata.xmp_conflict",
        "pdf.security.encrypted",
        "pdf.security.signature_present",
        "pdf.security.certification_present",
        "pdf.structure.linearized",
        "pdf.structure.authority_ambiguous",
    }
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
        if isinstance(acroform_ref, IndirectObject):
            acroform = acroform_ref.get_object()
        else:
            acroform = acroform_ref
        if hasattr(acroform, "get"):
            fields = acroform.get("/Fields", ())
        else:
            fields = ()
        stack = list(fields or ())
        while stack:
            field_ref = stack.pop()
            if isinstance(field_ref, IndirectObject):
                field = field_ref.get_object()
            else:
                field = field_ref
            if not hasattr(field, "get"):
                continue
            if field.get("/FT") == "/Sig":
                has_signature = True
                break
            kids = field.get("/Kids", ())
            stack.extend(kids or ())
    except Exception:
        has_signature = True
    return (has_signature, has_certification)


def _rect_tuple(value: object) -> tuple[float, float, float, float] | None:
    if isinstance(value, IndirectObject):
        try:
            value = value.get_object()
        except Exception:
            return None
    if not isinstance(value, (ArrayObject, list, tuple)) or len(value) != 4:
        return None
    try:
        return tuple(float(item) for item in value)  # type: ignore[return-value]
    except (TypeError, ValueError):
        return None


def _link_locator_digest(
    *,
    page_index: int,
    annotation_index: int,
    annotation_objgen: tuple[int, int],
    action_objgen: tuple[int, int] | None,
    owner_kind: str,
    mutation_owner_objgen: tuple[int, int],
    uri: str,
) -> str:
    evidence = repr(
        (
            "pdf-link-uri",
            page_index,
            annotation_index,
            annotation_objgen,
            action_objgen,
            owner_kind,
            mutation_owner_objgen,
            "/Link",
            "/URI",
            uri,
        )
    ).encode("utf-8")
    return sha256(evidence).hexdigest()


def _collect_links(
    reader: PdfReader,
    *,
    limits: PdfNativeLimits,
    source_policy_blocked: bool,
) -> tuple[PdfLinkEvidence, ...]:
    links: list[PdfLinkEvidence] = []
    total_annotations = 0
    total_uri_chars = 0

    for page_index, page in enumerate(reader.pages):
        annots_ref = _raw_get(page, "/Annots")
        if annots_ref is None:
            continue
        try:
            annots = (
                annots_ref.get_object()
                if isinstance(annots_ref, IndirectObject)
                else annots_ref
            )
        except Exception as exc:
            raise PdfParseError(
                "Unable to establish PDF annotation-array authority.",
                reason="pdf.annotations.malformed",
                details={"page_index": page_index},
            ) from exc
        if not isinstance(annots, (ArrayObject, list, tuple)):
            raise PdfParseError(
                "PDF page annotations are not represented by an array.",
                reason="pdf.annotations.malformed",
                details={"page_index": page_index},
            )
        if len(annots) > limits.max_annotations_per_page:
            raise PdfParseError(
                "PDF page annotation count exceeds the configured limit.",
                reason="pdf.annotations.too_many",
                details={
                    "page_index": page_index,
                    "annotation_count": len(annots),
                    "limit": limits.max_annotations_per_page,
                },
            )
        total_annotations += len(annots)
        if total_annotations > limits.max_total_annotations:
            raise PdfParseError(
                "PDF annotation count exceeds the configured limit.",
                reason="pdf.annotations.too_many",
                details={
                    "annotation_count": total_annotations,
                    "limit": limits.max_total_annotations,
                },
            )

        for annotation_index, annotation_ref in enumerate(annots):
            annotation_objgen = _objgen(annotation_ref)
            if annotation_objgen is None:
                # H10 never invents stable authority for direct annotation entries.
                continue
            try:
                annotation = annotation_ref.get_object()
            except Exception as exc:
                raise PdfParseError(
                    "Unable to resolve an indirect PDF annotation.",
                    reason="pdf.annotations.malformed",
                    details={
                        "page_index": page_index,
                        "annotation_index": annotation_index,
                    },
                ) from exc
            if not isinstance(annotation, DictionaryObject):
                raise PdfParseError(
                    "PDF annotation entry does not resolve to a dictionary.",
                    reason="pdf.annotations.malformed",
                    details={
                        "page_index": page_index,
                        "annotation_index": annotation_index,
                    },
                )
            if str(annotation.get("/Subtype", "")) != "/Link":
                continue

            action_ref = _raw_get(annotation, "/A")
            if action_ref is None:
                continue
            action_objgen = _objgen(action_ref)
            if action_objgen is not None:
                owner_kind = "action"
                mutation_owner_objgen = action_objgen
                try:
                    action = action_ref.get_object()
                except Exception as exc:
                    raise PdfParseError(
                        "Unable to resolve an indirect PDF link action.",
                        reason="pdf.link.action_malformed",
                        details={
                            "page_index": page_index,
                            "annotation_index": annotation_index,
                        },
                    ) from exc
            else:
                owner_kind = "annotation"
                mutation_owner_objgen = annotation_objgen
                action = action_ref
            if not isinstance(action, DictionaryObject):
                continue
            action_type = str(action.get("/S", ""))
            if action_type != "/URI":
                continue

            uri_raw = _raw_get(action, "/URI")
            if uri_raw is None:
                continue
            uri_is_text = isinstance(uri_raw, TextStringObject)
            uri = str(uri_raw) if uri_is_text else ""
            if uri_is_text and len(uri) > limits.max_uri_chars:
                raise PdfParseError(
                    "PDF URI exceeds the configured character limit.",
                    reason="pdf.link.uri_too_large",
                    details={
                        "page_index": page_index,
                        "annotation_index": annotation_index,
                        "uri_chars": len(uri),
                        "limit": limits.max_uri_chars,
                    },
                )
            total_uri_chars += len(uri)
            if total_uri_chars > limits.max_total_uri_chars:
                raise PdfParseError(
                    "PDF URI text exceeds the configured total character limit.",
                    reason="pdf.link.total_uri_too_large",
                    details={
                        "uri_chars": total_uri_chars,
                        "limit": limits.max_total_uri_chars,
                    },
                )

            reason_code: str | None = None
            if source_policy_blocked:
                reason_code = "pdf.link.source_policy"
            elif not uri_is_text:
                reason_code = "pdf.link.unsupported_uri"
            elif "/Dest" in annotation:
                reason_code = "pdf.link.competing_destination"
            elif "/AA" in annotation or "/AA" in action:
                reason_code = "pdf.link.additional_actions"

            links.append(
                PdfLinkEvidence(
                    page_index=page_index,
                    annotation_index=annotation_index,
                    annotation_objgen=annotation_objgen,
                    action_objgen=action_objgen,
                    owner_kind=owner_kind,
                    mutation_owner_objgen=mutation_owner_objgen,
                    uri=uri,
                    rect=_rect_tuple(_raw_get(annotation, "/Rect")),
                    subtype="/Link",
                    action_type="/URI",
                    locator_digest=_link_locator_digest(
                        page_index=page_index,
                        annotation_index=annotation_index,
                        annotation_objgen=annotation_objgen,
                        action_objgen=action_objgen,
                        owner_kind=owner_kind,
                        mutation_owner_objgen=mutation_owner_objgen,
                        uri=uri,
                    ),
                    writable=reason_code is None,
                    reason_code=reason_code,
                )
            )

    owner_counts: dict[tuple[int, int], int] = {}
    for link in links:
        owner_counts[link.mutation_owner_objgen] = (
            owner_counts.get(link.mutation_owner_objgen, 0) + 1
        )
    if any(count > 1 for count in owner_counts.values()):
        links = [
            replace(
                link,
                writable=False,
                reason_code="pdf.link.shared_owner",
            )
            if owner_counts[link.mutation_owner_objgen] > 1
            else link
            for link in links
        ]

    return tuple(links)


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
    root_ref = _raw_get(trailer, "/Root")
    root_objgen = _objgen(root_ref)
    info_ref = _raw_get(trailer, "/Info")
    info_objgen = _objgen(info_ref)
    diagnostics: list[str] = []
    fields: list[PdfInfoFieldEvidence] = []
    supported_metadata: dict[str, str] = {}

    if root_objgen is None:
        diagnostics.append("pdf.structure.authority_ambiguous")

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
    writable = (
        bool(fields)
        and not unsupported_value_type
        and not any(reason in blocking for reason in diagnostics)
    )

    links: tuple[PdfLinkEvidence, ...] = ()
    if not encrypted:
        links = _collect_links(
            reader,
            limits=limits,
            source_policy_blocked=any(
                reason in _LINK_SOURCE_BLOCKERS for reason in diagnostics
            ),
        )

    header_line = source.splitlines()[0].decode("ascii", errors="replace")
    snapshot = PdfSourceSnapshot(
        source_sha256=sha256(source).hexdigest(),
        source_size=len(source),
        pdf_header=header_line,
        page_count=page_count,
        root_objgen=root_objgen,
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
        links=links,
    )
