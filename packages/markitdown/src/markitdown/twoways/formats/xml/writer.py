from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import replace
from hashlib import sha256
from io import BytesIO
from typing import BinaryIO

from ..._errors import (
    IRValidationError,
    PatchPreconditionError,
    SourcePackageMismatchError,
    UnsupportedEditError,
)
from ..._results import (
    FidelityEvidence,
    FidelityReport,
    FidelityStatus,
    WriterResult,
)
from ...capabilities import (
    CAPABILITY_METADATA_KEY,
    CapabilityState,
    capabilities_for_node,
)
from ...ir.document import DocumentIR
from ...ir.edits import EditOperation, EditPrecondition
from ...ir.nodes import Node
from ...ir.semantics import validate_edit_preconditions
from ...ir.serialization import validate_document
from ..text.model import TextRepresentation
from .lexical import parse_xml_source
from .model import XmlLexicalNode
from .reader import read_xml_ir


_XML_EVIDENCE_KEYS = (
    "xml.path",
    "xml.kind",
    "xml.char_start",
    "xml.char_end",
    "xml.raw",
    "xml.raw_digest",
    "xml.qname",
    "xml.expanded_name",
    "xml.value_start",
    "xml.value_end",
    "xml.quote",
    "xml.namespace_prefix",
    "xml.namespace_uri",
    "xml.encoding",
    "xml.bom",
    "xml.byte_roundtrip",
    "xml.version",
    "xml.declared_encoding",
    "xml.standalone",
    "xml.declaration_raw",
    "xml.declaration_raw_digest",
    "xml.native_source",
    "xml.identity_markdown",
    CAPABILITY_METADATA_KEY,
)


def _read_source_bytes(source_stream: BinaryIO) -> bytes:
    source = source_stream.read()
    if not isinstance(source, bytes):
        raise TypeError("XML source stream must produce bytes")
    return source


def _source_mismatch(reason: str, *, expected: object, actual: object) -> None:
    raise SourcePackageMismatchError(
        f"XML source does not match the DocumentIR source authority ({reason}).",
        details={"reason": reason, "expected": expected, "actual": actual},
    )


def _validate_source_authority(document: DocumentIR, source: bytes) -> None:
    descriptor = document.source
    if descriptor is None:
        _source_mismatch("missing_source_descriptor", expected="xml", actual=None)
    assert descriptor is not None
    if descriptor.format != "xml":
        _source_mismatch("source_format", expected="xml", actual=descriptor.format)
    digest = sha256(source).hexdigest()
    if digest != descriptor.sha256:
        _source_mismatch("source_sha256", expected=descriptor.sha256, actual=digest)
    if len(source) != descriptor.size_bytes:
        _source_mismatch(
            "source_size",
            expected=descriptor.size_bytes,
            actual=len(source),
        )


def _nodes_by_path(document: DocumentIR) -> dict[str, Node]:
    result: dict[str, Node] = {}
    for node in document.nodes.values():
        path = node.metadata.get("xml.path")
        if not isinstance(path, str) or not path:
            raise PatchPreconditionError(
                "XML node is missing its native ownership path.",
                details={"reason": "xml.missing_path", "node_id": node.node_id},
            )
        if path in result:
            raise PatchPreconditionError(
                "XML ownership path is ambiguous in the DocumentIR.",
                details={"reason": "xml.duplicate_path", "path": path},
            )
        result[path] = node
    return result


def _root_node(document: DocumentIR) -> Node:
    if len(document.root_node_ids) != 1:
        raise PatchPreconditionError(
            "XML DocumentIR must contain exactly one document-element root.",
            details={"reason": "xml.root_count"},
        )
    root_id = document.root_node_ids[0]
    root = document.nodes.get(root_id)
    if root is None:
        raise PatchPreconditionError(
            "XML document-element root is missing.",
            details={"reason": "xml.root_missing"},
        )
    return root


def _representation(document: DocumentIR, *, require_writable: bool) -> TextRepresentation:
    root = _root_node(document)
    encoding = root.metadata.get("xml.encoding")
    bom = root.metadata.get("xml.bom")
    byte_roundtrip = root.metadata.get("xml.byte_roundtrip")
    if not isinstance(encoding, str) or not isinstance(bom, str):
        raise PatchPreconditionError(
            "XML source representation metadata is incomplete.",
            details={"reason": "xml.representation_metadata"},
        )
    if not isinstance(byte_roundtrip, bool):
        raise PatchPreconditionError(
            "XML source byte-roundtrip evidence is malformed.",
            details={"reason": "xml.representation_roundtrip_metadata"},
        )
    if require_writable and not byte_roundtrip:
        raise UnsupportedEditError(
            "XML source encoding is not byte-roundtrippable.",
            details={"reason": "xml.encoding.not_roundtrippable"},
        )
    return TextRepresentation(
        encoding=encoding,
        bom=bom,
        newline="mixed",
        byte_roundtrip=byte_roundtrip,
    )


def _fail_native_evidence(
    node: Node,
    path: str,
    reason: str,
    *,
    expected: object,
    actual: object,
) -> None:
    raise PatchPreconditionError(
        "XML native evidence no longer matches the source.",
        details={
            "reason": reason,
            "node_id": node.node_id,
            "path": path,
            "expected": expected,
            "actual": actual,
        },
    )


def _validate_node_evidence(node: Node, expected: Node, path: str) -> None:
    for key in _XML_EVIDENCE_KEYS:
        expected_value = expected.metadata.get(key)
        actual_value = node.metadata.get(key)
        if actual_value != expected_value:
            _fail_native_evidence(
                node,
                path,
                key,
                expected=expected_value,
                actual=actual_value,
            )

    checks = (
        ("native_locator", expected.native_locator, node.native_locator),
        ("provenance", expected.provenance, node.provenance),
        ("parent", expected.parent_id, node.parent_id),
        ("children", expected.children, node.children),
        ("semantic_kind", (expected.kind, expected.semantic_role), (node.kind, node.semantic_role)),
        ("payload", expected.payload, node.payload),
    )
    for reason, expected_value, actual_value in checks:
        if actual_value != expected_value:
            _fail_native_evidence(
                node,
                path,
                reason,
                expected=expected_value,
                actual=actual_value,
            )


def _validate_source_model(
    document: DocumentIR,
    source: bytes,
    representation: TextRepresentation,
) -> tuple[dict[str, Node], dict[str, XmlLexicalNode]]:
    descriptor = document.source
    assert descriptor is not None
    try:
        expected_document = read_xml_ir(
            BytesIO(source),
            filename=descriptor.filename,
            mimetype=descriptor.mimetype,
            encoding=representation.encoding,
        )
    except (UnicodeError, ValueError, TypeError) as exc:
        raise PatchPreconditionError(
            "XML source cannot be re-read using the recorded representation.",
            details={"reason": "xml.source_reread"},
        ) from exc

    actual_nodes = _nodes_by_path(document)
    expected_nodes = _nodes_by_path(expected_document)
    if set(actual_nodes) != set(expected_nodes):
        raise PatchPreconditionError(
            "XML ownership topology no longer matches the source.",
            details={
                "reason": "xml.path_set",
                "expected": tuple(sorted(expected_nodes)),
                "actual": tuple(sorted(actual_nodes)),
            },
        )

    if document.root_node_ids != expected_document.root_node_ids:
        raise PatchPreconditionError(
            "XML root ownership no longer matches the source.",
            details={"reason": "xml.root_identity"},
        )
    if document.canvases != expected_document.canvases:
        raise PatchPreconditionError(
            "XML canvas ownership no longer matches the source.",
            details={"reason": "xml.canvas_identity"},
        )

    for path, expected_node in expected_nodes.items():
        _validate_node_evidence(actual_nodes[path], expected_node, path)

    lexical_by_path: dict[str, XmlLexicalNode] = {}
    if representation.byte_roundtrip:
        try:
            parsed = parse_xml_source(source, encoding=representation.encoding)
        except (UnicodeError, ValueError, TypeError) as exc:
            raise PatchPreconditionError(
                "XML source fails strict lexical authority reparse.",
                details={"reason": "xml.source_lexical_reparse"},
            ) from exc
        lexical_by_path = {item.path: item for item in parsed.lexical.nodes}
        if set(lexical_by_path) != set(expected_nodes):
            raise PatchPreconditionError(
                "XML lexical ownership changed during source reparse.",
                details={"reason": "xml.lexical_path_set"},
            )

    return actual_nodes, lexical_by_path


def _is_xml_char(character: str) -> bool:
    value = ord(character)
    return (
        value in {0x9, 0xA, 0xD}
        or 0x20 <= value <= 0xD7FF
        or 0xE000 <= value <= 0xFFFD
        or 0x10000 <= value <= 0x10FFFF
    )


def _validate_requested_value(value: object) -> str:
    if not isinstance(value, str):
        raise UnsupportedEditError(
            "XML replacement value must be a string.",
            details={"reason": "xml.value.type", "value_type": type(value).__name__},
        )
    if any(not _is_xml_char(character) for character in value):
        raise UnsupportedEditError(
            "XML replacement contains a character forbidden by XML 1.0.",
            details={"reason": "xml.value.invalid_character"},
        )
    return value


def _validate_preconditions(
    document: DocumentIR,
    node: Node,
    edit: EditOperation,
    lexical: XmlLexicalNode,
) -> None:
    precondition = edit.precondition
    if precondition is not None and precondition.expected_old_value is not None:
        if precondition.expected_old_value != lexical.value:
            raise PatchPreconditionError(
                "XML edit precondition failed.",
                details={
                    "reason": "old_value",
                    "operation_id": edit.operation_id,
                    "target_node_id": edit.target_node_id,
                    "actual": lexical.value,
                },
            )
        generic_precondition = EditPrecondition(
            expected_semantic_digest=precondition.expected_semantic_digest,
            expected_native_locator_digest=precondition.expected_native_locator_digest,
            expected_old_value=None,
        )
        edit = replace(edit, precondition=generic_precondition)
    validate_edit_preconditions(document, node, edit, format_label="xml")


def _preflight_edit(
    document: DocumentIR,
    edit: EditOperation,
    path_nodes: Mapping[str, Node],
    lexical_by_path: Mapping[str, XmlLexicalNode],
) -> tuple[XmlLexicalNode, str]:
    if edit.target_node_id is None or edit.target_node_id not in document.nodes:
        raise PatchPreconditionError(
            "XML edit target does not exist in the DocumentIR.",
            details={
                "reason": "target_mismatch",
                "operation_id": edit.operation_id,
                "target_node_id": edit.target_node_id,
            },
        )
    node = document.nodes[edit.target_node_id]
    path = node.metadata.get("xml.path")
    if not isinstance(path, str) or path_nodes.get(path) is not node:
        raise PatchPreconditionError(
            "XML edit target ownership is invalid.",
            details={"reason": "xml.target_path", "operation_id": edit.operation_id},
        )
    lexical = lexical_by_path.get(path)
    if lexical is None:
        raise PatchPreconditionError(
            "XML edit target is missing from strict lexical ownership.",
            details={"reason": "xml.target_lexical", "path": path},
        )

    expected_type = {
        "text": "replace_xml_text",
        "attribute": "replace_xml_attribute",
    }.get(lexical.kind)
    if expected_type is None or edit.type != expected_type:
        raise UnsupportedEditError(
            "XML edit operation does not match a writable native owner.",
            details={
                "reason": "xml.edit_type_or_kind",
                "operation_id": edit.operation_id,
                "kind": lexical.kind,
                "edit_type": edit.type,
            },
        )

    capability = capabilities_for_node(node).for_operation(expected_type)
    if capability.state is not CapabilityState.WRITABLE:
        raise UnsupportedEditError(
            "XML target is read-only for the requested edit.",
            details={
                "reason": capability.reason_code or "xml.target.read_only",
                "path": path,
            },
        )
    if set(edit.payload) != {"value"}:
        raise UnsupportedEditError(
            "XML edits require exactly one 'value' payload field.",
            details={"reason": "xml.value.payload_shape", "path": path},
        )

    requested = _validate_requested_value(edit.payload["value"])
    _validate_preconditions(document, node, edit, lexical)
    if requested == lexical.value:
        raise UnsupportedEditError(
            "XML edit is a semantic no-op.",
            details={"reason": "xml.value.semantic_noop", "path": path},
        )
    return lexical, requested


def _result(bytes_written: int, *, zero_edit: bool) -> WriterResult:
    evidence = [
        FidelityEvidence(
            check_code="xml.source_authority",
            status=FidelityStatus.PASSED,
            description="Source SHA-256 and byte size matched the DocumentIR authority.",
        ),
        FidelityEvidence(
            check_code="xml.native_evidence",
            status=FidelityStatus.PASSED,
            description="XML lexical ownership and native evidence matched the source.",
        ),
    ]
    if zero_edit:
        evidence.append(
            FidelityEvidence(
                check_code="xml.zero_edit_identity",
                status=FidelityStatus.PASSED,
                description="Zero-edit output reused the exact source bytes.",
            )
        )
    return WriterResult(
        format="xml",
        mode="patch",
        bytes_written=bytes_written,
        fidelity=FidelityReport(
            claimed_tier="exact-preserve" if zero_edit else "high",
            evidence=tuple(evidence),
        ),
    )


def patch_xml(
    document: DocumentIR,
    source_stream: BinaryIO,
    output: BinaryIO,
    *,
    edits: Sequence[EditOperation] = (),
) -> WriterResult:
    try:
        validate_document(document)
    except IRValidationError as exc:
        raise PatchPreconditionError(
            "XML DocumentIR failed structural validation.",
            details={"reason": "xml.document_ir_invalid"},
        ) from exc

    source = _read_source_bytes(source_stream)
    _validate_source_authority(document, source)
    edits = tuple(edits)
    representation = _representation(document, require_writable=bool(edits))
    path_nodes, lexical_by_path = _validate_source_model(
        document,
        source,
        representation,
    )

    if not edits:
        output.write(source)
        return _result(len(source), zero_edit=True)

    seen_paths: set[str] = set()
    for edit in edits:
        lexical, _requested = _preflight_edit(
            document,
            edit,
            path_nodes,
            lexical_by_path,
        )
        if lexical.path in seen_paths:
            raise UnsupportedEditError(
                "XML edit set contains a duplicate target.",
                details={"reason": "xml.value.duplicate_target", "path": lexical.path},
            )
        seen_paths.add(lexical.path)

    raise UnsupportedEditError(
        "XML value rendering is not implemented until H4 Task 4.",
        details={"reason": "xml.rendering.not_implemented"},
    )
