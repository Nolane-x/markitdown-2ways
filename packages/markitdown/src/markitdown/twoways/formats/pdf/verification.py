from __future__ import annotations

from collections.abc import Mapping, Sequence
from io import BytesIO
from typing import Any

import pdfplumber
from pdfminer.pdfdocument import PDFDocument
from pdfminer.pdfparser import PDFParser
from pdfminer.utils import decode_text
from pypdf import PdfReader
from pypdf.generic import IndirectObject

from ..._errors import RoundTripVerificationError
from .limits import PdfNativeLimits
from .parser import parse_pdf_source
from .routing import PdfRoutedLinkEdit, PdfRoutedMetadataEdit

_SUPPORTED_FIELDS = ("Title", "Author", "Subject", "Keywords")
PdfRoutedEdit = PdfRoutedMetadataEdit | PdfRoutedLinkEdit


def _fail(reason: str, message: str, **details: object) -> None:
    raise RoundTripVerificationError(message, details={"reason": reason, **details})


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
            tuple(sorted((str(k), _canonical_pdf_value(v)) for k, v in value.items())),
        )
    if isinstance(value, (list, tuple)):
        return ("array", tuple(_canonical_pdf_value(v) for v in value))
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
                "PDF candidate lacks indirect Info authority.",
            )
        info = info_ref.get_object()
        if not isinstance(info, Mapping):
            _fail(
                "pdf.candidate.info_missing",
                "PDF candidate Info owner is not a dictionary.",
            )
        return {str(k): _canonical_pdf_value(v) for k, v in info.items()}
    except RoundTripVerificationError:
        raise
    except Exception as exc:
        raise RoundTripVerificationError(
            "PDF Document Information inventory could not be established.",
            details={"reason": "pdf.candidate.reread_failed"},
        ) from exc


def _pdfminer_metadata(data: bytes) -> dict[str, str]:
    try:
        document = PDFDocument(PDFParser(BytesIO(data)))
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


def _pdfplumber_hyperlinks(
    data: bytes,
) -> tuple[
    tuple[tuple[tuple[float, float, float, float] | None, str | None], ...], ...
]:
    try:
        pages = []
        with pdfplumber.open(BytesIO(data)) as pdf:
            for page in pdf.pages:
                page_links = []
                height = float(page.height)
                for hyperlink in page.hyperlinks:
                    if not isinstance(hyperlink, Mapping):
                        continue
                    try:
                        rect = (
                            float(hyperlink["x0"]),
                            height - float(hyperlink["bottom"]),
                            float(hyperlink["x1"]),
                            height - float(hyperlink["top"]),
                        )
                    except (KeyError, TypeError, ValueError):
                        rect = None
                    uri = hyperlink.get("uri")
                    page_links.append((rect, uri if isinstance(uri, str) else None))
                pages.append(tuple(page_links))
        return tuple(pages)
    except Exception as exc:
        raise RoundTripVerificationError(
            "pdfplumber could not independently inspect PDF URI links.",
            details={"reason": "pdf.candidate.pdfplumber_link"},
        ) from exc


def _verify_metadata(
    source, candidate, source_parsed, candidate_parsed, routed
) -> None:
    source_snapshot = source_parsed.snapshot
    candidate_snapshot = candidate_parsed.snapshot
    requested = {item.field: item.value for item in routed}
    source_metadata = dict(source_snapshot.supported_metadata)
    candidate_metadata = dict(candidate_snapshot.supported_metadata)
    for field, value in requested.items():
        if candidate_metadata.get(field) != value:
            _fail(
                "pdf.candidate.requested_semantic",
                "Requested PDF metadata value did not survive strict re-read.",
                field=field,
                expected=value,
                actual=candidate_metadata.get(field),
            )
    for field, value in source_metadata.items():
        if field not in requested and candidate_metadata.get(field) != value:
            _fail(
                "pdf.candidate.unrequested_metadata",
                "Unrequested supported PDF metadata changed.",
                field=field,
                expected=value,
                actual=candidate_metadata.get(field),
            )
    if source_snapshot.info_objgen is not None:
        source_info = _info_inventory(source)
        candidate_info = _info_inventory(candidate)
        requested_keys = {item.key for item in routed}
        source_untouched = {
            k: v for k, v in source_info.items() if k not in requested_keys
        }
        candidate_untouched = {
            k: v for k, v in candidate_info.items() if k not in requested_keys
        }
        if candidate_untouched != source_untouched:
            _fail(
                "pdf.candidate.unrequested_metadata",
                "Unrequested Document Information entries changed.",
                expected=source_untouched,
                actual=candidate_untouched,
            )
    if routed:
        independent = _pdfminer_metadata(candidate)
        for field in _SUPPORTED_FIELDS:
            expected = candidate_metadata.get(field)
            if expected is not None and independent.get(field) != expected:
                _fail(
                    "pdf.candidate.pdfminer_metadata",
                    "pdfminer disagreed with the strict pypdf metadata interpretation.",
                    field=field,
                    expected=expected,
                    actual=independent.get(field),
                )


def _verify_annotation_authority(
    source_snapshot,
    candidate_snapshot,
    *,
    direct_action_targets: frozenset[tuple[int, int]],
) -> None:
    if candidate_snapshot.page_objgens != source_snapshot.page_objgens:
        _fail(
            "pdf.candidate.page_identity",
            "PDF candidate changed page object identity.",
            expected=source_snapshot.page_objgens,
            actual=candidate_snapshot.page_objgens,
        )
    if candidate_snapshot.annotation_topology != source_snapshot.annotation_topology:
        _fail(
            "pdf.candidate.annotation_topology",
            "PDF candidate changed annotation count, order, or native ownership.",
            expected=source_snapshot.annotation_topology,
            actual=candidate_snapshot.annotation_topology,
        )
    source_fp = source_snapshot.annotation_fingerprints
    candidate_fp = candidate_snapshot.annotation_fingerprints
    if len(candidate_fp) != len(source_fp) or any(
        len(c) != len(s) for s, c in zip(source_fp, candidate_fp)
    ):
        _fail(
            "pdf.candidate.annotation_topology",
            "PDF candidate changed annotation fingerprint topology.",
        )
    for page_index, (source_page, candidate_page) in enumerate(
        zip(source_fp, candidate_fp)
    ):
        for annotation_index, (source_digest, candidate_digest) in enumerate(
            zip(source_page, candidate_page)
        ):
            target = (page_index, annotation_index)
            if (
                source_digest != candidate_digest
                and target not in direct_action_targets
            ):
                _fail(
                    "pdf.candidate.annotation_sibling",
                    "PDF candidate changed an annotation outside an authorized direct URI target.",
                    target=target,
                    expected=source_digest,
                    actual=candidate_digest,
                )


def _link_binding(link) -> tuple[object, ...]:
    return (
        link.annotation_objgen,
        link.action_objgen,
        link.owner_kind,
        link.mutation_owner_objgen,
        link.rect,
        link.subtype,
        link.action_type,
        link.writable,
        link.reason_code,
        link.immutable_digest,
    )


def _verify_links(source_parsed, candidate_parsed, routed) -> None:
    source_links = {(x.page_index, x.annotation_index): x for x in source_parsed.links}
    candidate_links = {
        (x.page_index, x.annotation_index): x for x in candidate_parsed.links
    }
    if len(source_links) != len(source_parsed.links) or len(candidate_links) != len(
        candidate_parsed.links
    ):
        _fail(
            "pdf.candidate.link_topology",
            "PDF URI link coordinates are not uniquely authoritative.",
        )
    if candidate_links.keys() != source_links.keys():
        _fail(
            "pdf.candidate.link_topology",
            "PDF URI link topology changed during incremental mutation.",
            expected=tuple(sorted(source_links)),
            actual=tuple(sorted(candidate_links)),
        )
    requested = {(item.page_index, item.annotation_index): item.uri for item in routed}
    for key, source_link in source_links.items():
        candidate_link = candidate_links[key]
        if _link_binding(candidate_link) != _link_binding(source_link):
            _fail(
                "pdf.candidate.link_binding",
                "PDF URI link native ownership or immutable annotation evidence changed.",
                target=key,
                expected=_link_binding(source_link),
                actual=_link_binding(candidate_link),
            )
        expected_uri = requested.get(key, source_link.uri)
        if candidate_link.uri != expected_uri:
            _fail(
                "pdf.candidate.link_uri",
                "PDF URI link value did not match the requested target-only result.",
                target=key,
                expected=expected_uri,
                actual=candidate_link.uri,
            )


def _verify_pdfplumber_links(
    source, candidate, source_parsed, candidate_parsed, routed
) -> None:
    if not routed:
        return
    source_oracle = _pdfplumber_hyperlinks(source)
    candidate_oracle = _pdfplumber_hyperlinks(candidate)
    source_links = {(x.page_index, x.annotation_index): x for x in source_parsed.links}
    candidate_links = {
        (x.page_index, x.annotation_index): x for x in candidate_parsed.links
    }
    for item in routed:
        key = (item.page_index, item.annotation_index)
        source_link = source_links.get(key)
        candidate_link = candidate_links.get(key)
        if source_link is None or candidate_link is None or source_link.rect is None:
            _fail(
                "pdf.candidate.pdfplumber_link",
                "PDF URI link could not be mapped.",
                target=key,
            )
        if item.page_index >= len(source_oracle) or item.page_index >= len(
            candidate_oracle
        ):
            _fail(
                "pdf.candidate.pdfplumber_link",
                "pdfplumber page topology did not match.",
                target=key,
            )

        def matches(page_links):
            out = []
            for rect, uri in page_links:
                if rect is not None and all(
                    abs(a - b) <= 1e-6 for a, b in zip(rect, source_link.rect)
                ):
                    out.append(uri)
            return out

        source_matches = matches(source_oracle[item.page_index])
        candidate_matches = matches(candidate_oracle[item.page_index])
        if len(source_matches) != 1 or len(candidate_matches) != 1:
            _fail(
                "pdf.candidate.pdfplumber_link",
                "pdfplumber hyperlink mapping was missing or ambiguous.",
                target=key,
                source_matches=len(source_matches),
                candidate_matches=len(candidate_matches),
            )
        if source_matches[0] != source_link.uri or candidate_matches[0] != item.uri:
            _fail(
                "pdf.candidate.pdfplumber_link",
                "pdfplumber disagreed with PDF URI-link semantics.",
                target=key,
            )


def verify_pdf_candidate(
    source: bytes,
    candidate: bytes,
    routed: Sequence[PdfRoutedEdit],
    *,
    changed_objects: Sequence[tuple[int, int]],
    limits: PdfNativeLimits | None = None,
) -> None:
    limits = limits or PdfNativeLimits()
    routed = tuple(routed)
    changed_objects = tuple(changed_objects)
    metadata_edits = tuple(x for x in routed if isinstance(x, PdfRoutedMetadataEdit))
    link_edits = tuple(x for x in routed if isinstance(x, PdfRoutedLinkEdit))
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
    expected_owners = {x.mutation_owner_objgen for x in link_edits}
    if metadata_edits:
        if source_snapshot.info_objgen is None:
            _fail(
                "pdf.metadata.info_missing",
                "Source PDF lacks authoritative Info ownership.",
            )
        expected_owners.add(source_snapshot.info_objgen)
    if set(changed_objects) != expected_owners:
        _fail(
            "pdf.writer.unexpected_increment_object",
            "PDF incremental update changed an object outside the authorized owner set.",
            expected=tuple(sorted(expected_owners)),
            actual=changed_objects,
        )
    if candidate_snapshot.page_count != source_snapshot.page_count:
        _fail("pdf.candidate.page_count", "PDF candidate changed page count.")
    if candidate_snapshot.root_objgen != source_snapshot.root_objgen:
        _fail(
            "pdf.candidate.root_authority",
            "PDF candidate changed catalog root authority.",
        )
    if candidate_snapshot.info_objgen != source_snapshot.info_objgen:
        _fail(
            "pdf.candidate.info_authority",
            "PDF candidate changed Info owner identity.",
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
            "PDF candidate changed a security or authority policy flag.",
        )
    _verify_annotation_authority(
        source_snapshot,
        candidate_snapshot,
        direct_action_targets=frozenset(
            (x.page_index, x.annotation_index)
            for x in link_edits
            if x.owner_kind == "annotation"
        ),
    )
    _verify_metadata(source, candidate, source_parsed, candidate_parsed, metadata_edits)
    _verify_links(source_parsed, candidate_parsed, link_edits)
    _verify_pdfplumber_links(
        source, candidate, source_parsed, candidate_parsed, link_edits
    )
