from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256

from ..._errors import (
    PatchPreconditionError,
    SourcePackageMismatchError,
    UnsupportedEditError,
)
from ...capabilities import CapabilityState, capabilities_for_node
from ...ir.document import DocumentIR
from ...ir.edits import EditOperation
from ...ir.nodes import TextPayload
from ...ir.semantics import validate_edit_preconditions
from ...ir.serialization import validate_document
from .limits import PdfNativeLimits
from .parser import parse_pdf_source

_FIELD_TO_KEY = {
    "Title": "/Title",
    "Author": "/Author",
    "Subject": "/Subject",
    "Keywords": "/Keywords",
}


@dataclass(frozen=True)
class PdfRoutedMetadataEdit:
    operation_id: str
    target_node_id: str
    field: str
    key: str
    old_value: str
    value: str
    info_objgen: tuple[int, int]


@dataclass(frozen=True)
class PdfRoutedLinkEdit:
    operation_id: str
    target_node_id: str
    page_index: int
    annotation_index: int
    annotation_objgen: tuple[int, int]
    action_objgen: tuple[int, int] | None
    owner_kind: str
    mutation_owner_objgen: tuple[int, int]
    locator_digest: str
    old_uri: str
    uri: str


def _source_mismatch(reason: str, *, expected: object, actual: object) -> None:
    raise SourcePackageMismatchError(
        "PDF source does not match the DocumentIR source authority.",
        details={"reason": reason, "expected": expected, "actual": actual},
    )


def _validate_source_authority(document: DocumentIR, source: bytes) -> None:
    descriptor = document.source
    if descriptor is None:
        _source_mismatch("missing_source_descriptor", expected="pdf", actual=None)
    assert descriptor is not None
    if descriptor.format != "pdf":
        _source_mismatch("source_format", expected="pdf", actual=descriptor.format)
    digest = sha256(source).hexdigest()
    if digest != descriptor.sha256:
        _source_mismatch("source_sha256", expected=descriptor.sha256, actual=digest)
    if len(source) != descriptor.size_bytes:
        _source_mismatch(
            "source_size", expected=descriptor.size_bytes, actual=len(source)
        )


def _precondition(
    reason: str, *, node_id: str, expected: object, actual: object
) -> None:
    raise PatchPreconditionError(
        "PDF native metadata evidence no longer matches the source authority.",
        details={
            "reason": reason,
            "node_id": node_id,
            "expected": expected,
            "actual": actual,
        },
    )


def _link_precondition(
    reason: str, *, node_id: str, expected: object, actual: object
) -> None:
    raise PatchPreconditionError(
        "PDF URI link evidence no longer matches the source authority.",
        details={
            "reason": reason,
            "node_id": node_id,
            "expected": expected,
            "actual": actual,
        },
    )


def resolve_pdf_metadata_edit(
    document: DocumentIR,
    source: bytes,
    edit: EditOperation,
    *,
    limits: PdfNativeLimits | None = None,
) -> PdfRoutedMetadataEdit:
    validate_document(document)
    _validate_source_authority(document, source)
    limits = limits or PdfNativeLimits()
    parsed = parse_pdf_source(source, limits=limits)

    if edit.type != "update_pdf_metadata":
        raise UnsupportedEditError(
            "H9 PDF supports update_pdf_metadata edits only.",
            details={"reason": "pdf.edit_type", "operation_id": edit.operation_id},
        )
    if edit.target_node_id is None or edit.target_node_id not in document.nodes:
        raise PatchPreconditionError(
            "PDF metadata edit target does not exist in the DocumentIR.",
            details={
                "reason": "target_mismatch",
                "operation_id": edit.operation_id,
                "target_node_id": edit.target_node_id,
            },
        )

    node = document.nodes[edit.target_node_id]
    validate_edit_preconditions(document, node, edit, format_label="pdf")
    capability = capabilities_for_node(node).for_operation("update_pdf_metadata")
    if capability.state is not CapabilityState.WRITABLE:
        raise UnsupportedEditError(
            "PDF metadata target is read-only.",
            details={
                "reason": capability.reason_code or "pdf.structure.read_only",
                "target_node_id": node.node_id,
            },
        )
    if not parsed.writable:
        raise UnsupportedEditError(
            "Fresh PDF authority is not writable under H9 policy.",
            details={
                "reason": parsed.diagnostics[0]
                if parsed.diagnostics
                else "pdf.structure.read_only"
            },
        )
    if set(edit.payload) != {"field", "value"}:
        raise UnsupportedEditError(
            "PDF metadata edits require exactly field and value payload entries.",
            details={"reason": "pdf.metadata.payload_shape"},
        )

    field = edit.payload["field"]
    value = edit.payload["value"]
    if not isinstance(field, str) or field not in _FIELD_TO_KEY:
        raise UnsupportedEditError(
            "PDF metadata field is outside the H9 writable set.",
            details={"reason": "pdf.metadata.unsupported_field", "field": field},
        )
    if not isinstance(value, str):
        raise UnsupportedEditError(
            "PDF metadata replacement value must be text.",
            details={"reason": "pdf.metadata.value_type", "field": field},
        )
    if len(value) > limits.max_metadata_value_chars:
        raise UnsupportedEditError(
            "PDF metadata replacement exceeds the per-value limit.",
            details={"reason": "pdf.metadata.value_too_large", "field": field},
        )

    key = _FIELD_TO_KEY[field]
    info_objgen = parsed.snapshot.info_objgen
    if info_objgen is None:
        raise UnsupportedEditError(
            "PDF Document Information authority is missing.",
            details={"reason": "pdf.metadata.info_missing"},
        )

    recorded_binding = (
        node.semantic_role,
        node.metadata.get("pdf.info_field"),
        node.metadata.get("pdf.info_key"),
        node.metadata.get("pdf.info_objgen"),
    )
    expected_binding = ("pdf-metadata", field, key, info_objgen)
    if recorded_binding != expected_binding:
        _precondition(
            "pdf.field_binding",
            node_id=node.node_id,
            expected=expected_binding,
            actual=recorded_binding,
        )

    locator = node.native_locator
    expected_locator = ("pdf", "/Info", f"{info_objgen[0]}:{info_objgen[1]}", key)
    actual_locator = None
    if locator is not None:
        actual_locator = (
            locator.backend,
            locator.part_uri,
            locator.object_id,
            locator.path,
        )
    if actual_locator != expected_locator:
        _precondition(
            "pdf.native_locator",
            node_id=node.node_id,
            expected=expected_locator,
            actual=actual_locator,
        )

    fresh_field = next((item for item in parsed.fields if item.key == key), None)
    if fresh_field is None:
        raise UnsupportedEditError(
            "Requested PDF metadata key is not an existing text owner.",
            details={"reason": "pdf.metadata.key_missing", "field": field},
        )
    if fresh_field.info_objgen != info_objgen:
        _precondition(
            "pdf.info_objgen",
            node_id=node.node_id,
            expected=info_objgen,
            actual=fresh_field.info_objgen,
        )
    if not isinstance(node.payload, TextPayload):
        _precondition(
            "pdf.target_payload",
            node_id=node.node_id,
            expected="TextPayload",
            actual=type(node.payload).__name__,
        )
    assert isinstance(node.payload, TextPayload)
    if node.payload.text != fresh_field.value:
        _precondition(
            "pdf.old_value",
            node_id=node.node_id,
            expected=fresh_field.value,
            actual=node.payload.text,
        )
    if node.metadata.get("pdf.object_type") != fresh_field.object_type:
        _precondition(
            "pdf.object_type",
            node_id=node.node_id,
            expected=fresh_field.object_type,
            actual=node.metadata.get("pdf.object_type"),
        )
    if value == fresh_field.value:
        raise UnsupportedEditError(
            "PDF metadata edit is a semantic no-op.",
            details={"reason": "pdf.metadata.semantic_noop", "field": field},
        )

    total_chars = sum(
        len(item.value) for item in parsed.fields if item.key != key
    ) + len(value)
    if total_chars > limits.max_total_metadata_chars:
        raise UnsupportedEditError(
            "PDF metadata transaction exceeds the total text limit.",
            details={"reason": "pdf.metadata.total_too_large"},
        )

    return PdfRoutedMetadataEdit(
        operation_id=edit.operation_id,
        target_node_id=node.node_id,
        field=field,
        key=key,
        old_value=fresh_field.value,
        value=value,
        info_objgen=info_objgen,
    )


def resolve_pdf_link_uri_edit(
    document: DocumentIR,
    source: bytes,
    edit: EditOperation,
    *,
    limits: PdfNativeLimits | None = None,
) -> PdfRoutedLinkEdit:
    validate_document(document)
    _validate_source_authority(document, source)
    limits = limits or PdfNativeLimits()
    parsed = parse_pdf_source(source, limits=limits)

    if edit.type != "update_pdf_link_uri":
        raise UnsupportedEditError(
            "H10 PDF link routing accepts update_pdf_link_uri edits only.",
            details={"reason": "pdf.edit_type", "operation_id": edit.operation_id},
        )
    if edit.target_node_id is None or edit.target_node_id not in document.nodes:
        raise PatchPreconditionError(
            "PDF URI link edit target does not exist in the DocumentIR.",
            details={
                "reason": "target_mismatch",
                "operation_id": edit.operation_id,
                "target_node_id": edit.target_node_id,
            },
        )

    node = document.nodes[edit.target_node_id]
    validate_edit_preconditions(document, node, edit, format_label="pdf")
    capability = capabilities_for_node(node).for_operation("update_pdf_link_uri")
    if capability.state is not CapabilityState.WRITABLE:
        raise UnsupportedEditError(
            "PDF URI link target is read-only.",
            details={
                "reason": capability.reason_code or "pdf.link.read_only",
                "target_node_id": node.node_id,
            },
        )
    required_payload = {"page_index", "annotation_index", "old_uri", "uri"}
    if set(edit.payload) != required_payload:
        raise UnsupportedEditError(
            "PDF URI link edits require page, annotation, old URI, and URI payload entries.",
            details={"reason": "pdf.link.payload_shape"},
        )

    page_index = edit.payload["page_index"]
    annotation_index = edit.payload["annotation_index"]
    old_uri = edit.payload["old_uri"]
    uri = edit.payload["uri"]
    if (
        not isinstance(page_index, int)
        or isinstance(page_index, bool)
        or page_index < 0
        or not isinstance(annotation_index, int)
        or isinstance(annotation_index, bool)
        or annotation_index < 0
    ):
        raise UnsupportedEditError(
            "PDF URI link coordinates must be non-negative integers.",
            details={"reason": "pdf.link.payload_coordinates"},
        )
    if not isinstance(old_uri, str) or not isinstance(uri, str):
        raise UnsupportedEditError(
            "PDF URI link values must be text.",
            details={"reason": "pdf.link.uri_type"},
        )
    if not uri:
        raise UnsupportedEditError(
            "PDF URI link replacement must not be empty.",
            details={"reason": "pdf.link.uri_empty"},
        )
    if len(uri) > limits.max_uri_chars:
        raise UnsupportedEditError(
            "PDF URI link replacement exceeds the configured character limit.",
            details={"reason": "pdf.link.uri_too_large"},
        )

    node_coordinates = (
        node.metadata.get("pdf.page_index"),
        node.metadata.get("pdf.annotation_index"),
    )
    payload_coordinates = (page_index, annotation_index)
    if payload_coordinates != node_coordinates:
        _link_precondition(
            "pdf.link.payload_coordinates",
            node_id=node.node_id,
            expected=node_coordinates,
            actual=payload_coordinates,
        )

    fresh_link = next(
        (
            item
            for item in parsed.links
            if item.page_index == page_index
            and item.annotation_index == annotation_index
        ),
        None,
    )
    if fresh_link is None:
        raise UnsupportedEditError(
            "Requested PDF URI link target is not present in the fresh source.",
            details={"reason": "pdf.link.target_missing"},
        )
    if not fresh_link.writable:
        raise UnsupportedEditError(
            "Fresh PDF URI link authority is read-only under H10 policy.",
            details={"reason": fresh_link.reason_code or "pdf.link.read_only"},
        )

    recorded_binding = (
        node.semantic_role,
        node.metadata.get("pdf.page_index"),
        node.metadata.get("pdf.annotation_index"),
        node.metadata.get("pdf.annotation_objgen"),
        node.metadata.get("pdf.action_objgen"),
        node.metadata.get("pdf.action_owner_kind"),
        node.metadata.get("pdf.mutation_owner_objgen"),
        node.metadata.get("pdf.link_locator_digest"),
        node.metadata.get("pdf.link_subtype"),
        node.metadata.get("pdf.link_action_type"),
    )
    expected_binding = (
        "pdf-link-uri",
        fresh_link.page_index,
        fresh_link.annotation_index,
        fresh_link.annotation_objgen,
        fresh_link.action_objgen,
        fresh_link.owner_kind,
        fresh_link.mutation_owner_objgen,
        fresh_link.locator_digest,
        fresh_link.subtype,
        fresh_link.action_type,
    )
    if recorded_binding != expected_binding:
        _link_precondition(
            "pdf.link.native_binding",
            node_id=node.node_id,
            expected=expected_binding,
            actual=recorded_binding,
        )

    locator = node.native_locator
    expected_locator = (
        "pdf",
        f"/Pages/{page_index}/Annots",
        f"{fresh_link.annotation_objgen[0]}:{fresh_link.annotation_objgen[1]}",
        "/A/URI",
    )
    actual_locator = None
    if locator is not None:
        actual_locator = (
            locator.backend,
            locator.part_uri,
            locator.object_id,
            locator.path,
        )
    if actual_locator != expected_locator:
        _link_precondition(
            "pdf.link.native_locator",
            node_id=node.node_id,
            expected=expected_locator,
            actual=actual_locator,
        )

    if not isinstance(node.payload, TextPayload):
        _link_precondition(
            "pdf.link.target_payload",
            node_id=node.node_id,
            expected="TextPayload",
            actual=type(node.payload).__name__,
        )
    assert isinstance(node.payload, TextPayload)
    if old_uri != node.payload.text or old_uri != fresh_link.uri:
        _link_precondition(
            "pdf.link.old_uri",
            node_id=node.node_id,
            expected=fresh_link.uri,
            actual=old_uri,
        )
    if node.payload.text != fresh_link.uri:
        _link_precondition(
            "pdf.link.old_uri",
            node_id=node.node_id,
            expected=fresh_link.uri,
            actual=node.payload.text,
        )
    if uri == fresh_link.uri:
        raise UnsupportedEditError(
            "PDF URI link edit is a semantic no-op.",
            details={"reason": "pdf.link.semantic_noop"},
        )

    total_uri_chars = sum(
        len(item.uri)
        for item in parsed.links
        if not (
            item.page_index == page_index
            and item.annotation_index == annotation_index
        )
    ) + len(uri)
    if total_uri_chars > limits.max_total_uri_chars:
        raise UnsupportedEditError(
            "PDF URI link transaction exceeds the total URI character limit.",
            details={"reason": "pdf.link.total_uri_too_large"},
        )

    return PdfRoutedLinkEdit(
        operation_id=edit.operation_id,
        target_node_id=node.node_id,
        page_index=page_index,
        annotation_index=annotation_index,
        annotation_objgen=fresh_link.annotation_objgen,
        action_objgen=fresh_link.action_objgen,
        owner_kind=fresh_link.owner_kind,
        mutation_owner_objgen=fresh_link.mutation_owner_objgen,
        locator_digest=fresh_link.locator_digest,
        old_uri=fresh_link.uri,
        uri=uri,
    )
