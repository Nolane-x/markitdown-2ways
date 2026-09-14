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
        _source_mismatch("source_size", expected=descriptor.size_bytes, actual=len(source))


def _precondition(reason: str, *, node_id: str, expected: object, actual: object) -> None:
    raise PatchPreconditionError(
        "PDF native metadata evidence no longer matches the source authority.",
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
                "reason": parsed.diagnostics[0] if parsed.diagnostics else "pdf.structure.read_only"
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
        actual_locator = (locator.backend, locator.part_uri, locator.object_id, locator.path)
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

    total_chars = sum(len(item.value) for item in parsed.fields if item.key != key) + len(value)
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
