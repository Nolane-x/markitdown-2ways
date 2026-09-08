from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Iterable

from .._errors import IRValidationError, UnsupportedSchemaVersionError
from .document import DocumentIR, SCHEMA_NAME
from .nodes import ChartPayload, ImagePayload, TablePayload, UnknownNativePayload


_SCHEMA_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")
_SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")


@dataclass(frozen=True)
class ValidationViolation:
    code: str
    message: str
    path: str | None = None
    details: dict[str, Any] | None = None

    def as_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.path is not None:
            result["path"] = self.path
        if self.details:
            result["details"] = dict(self.details)
        return result


def _add(
    violations: list[ValidationViolation],
    code: str,
    message: str,
    *,
    path: str | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    violations.append(ValidationViolation(code, message, path, details))


def _check_digest(
    violations: list[ValidationViolation], value: str | None, path: str
) -> None:
    if value is not None and _SHA256_RE.fullmatch(value) is None:
        _add(
            violations,
            "digest.invalid",
            "SHA-256 digest must contain exactly 64 hexadecimal characters",
            path=path,
        )


def _duplicates(values: Iterable[Any]) -> set[Any]:
    seen: set[Any] = set()
    duplicates: set[Any] = set()
    for value in values:
        if value in seen:
            duplicates.add(value)
        seen.add(value)
    return duplicates


def validate_document(document: DocumentIR) -> None:
    """Validate a DocumentIR at a public boundary without mutating it."""

    match = _SCHEMA_RE.fullmatch(document.schema_version)
    if match is not None and int(match.group(1)) != 0:
        raise UnsupportedSchemaVersionError(
            f"Unsupported MarkItDown 2Ways schema version: {document.schema_version}",
            details={"schema_version": document.schema_version, "supported_major": 0},
        )

    violations: list[ValidationViolation] = []
    if document.schema_name != SCHEMA_NAME:
        _add(
            violations,
            "schema.name",
            f"schema_name must be {SCHEMA_NAME}",
            path="schema_name",
        )
    if match is None:
        _add(
            violations,
            "schema.version_invalid",
            "schema_version must use MAJOR.MINOR.PATCH numeric syntax",
            path="schema_version",
        )

    canvas_ids = [canvas.canvas_id for canvas in document.canvases]
    for duplicate in sorted(_duplicates(canvas_ids)):
        _add(
            violations,
            "canvas.duplicate_id",
            f"duplicate canvas id: {duplicate}",
            path="canvases",
        )
    canvas_indices = [canvas.index for canvas in document.canvases]
    for duplicate in sorted(_duplicates(canvas_indices)):
        _add(
            violations,
            "canvas.duplicate_index",
            f"duplicate canvas index: {duplicate}",
            path="canvases",
        )
    if canvas_indices != sorted(canvas_indices):
        _add(
            violations,
            "canvas.order",
            "canvases must be ordered by index",
            path="canvases",
        )
    canvas_id_set = set(canvas_ids)
    canvas_index_set = set(canvas_indices)

    node_ids = set(document.nodes)
    for key in sorted(document.nodes):
        node = document.nodes[key]
        if node.node_id != key:
            _add(
                violations,
                "node.key_mismatch",
                f"node map key {key!r} does not match node_id {node.node_id!r}",
                path=f"nodes.{key}",
            )
        if node.canvas_id is not None and node.canvas_id not in canvas_id_set:
            _add(
                violations,
                "node.missing_canvas",
                f"node {key!r} references missing canvas {node.canvas_id!r}",
                path=f"nodes.{key}.canvas_id",
            )
        for index, provenance in enumerate(node.provenance):
            if provenance.canvas_index is not None and provenance.canvas_index not in canvas_index_set:
                _add(
                    violations,
                    "provenance.missing_canvas",
                    f"provenance references missing canvas index {provenance.canvas_index}",
                    path=f"nodes.{key}.provenance.{index}.canvas_index",
                )

    for root in document.root_node_ids:
        if root not in node_ids:
            _add(
                violations,
                "document.missing_root",
                f"document root node {root!r} does not exist",
                path="root_node_ids",
            )
    for canvas in document.canvases:
        for root in canvas.root_node_ids:
            if root not in node_ids:
                _add(
                    violations,
                    "canvas.missing_root",
                    f"canvas {canvas.canvas_id!r} root node {root!r} does not exist",
                    path=f"canvases.{canvas.canvas_id}.root_node_ids",
                )
            elif document.nodes[root].canvas_id not in (None, canvas.canvas_id):
                _add(
                    violations,
                    "canvas.root_canvas_mismatch",
                    f"node {root!r} does not belong to canvas {canvas.canvas_id!r}",
                    path=f"canvases.{canvas.canvas_id}.root_node_ids",
                )

    parents_by_child: dict[str, list[str]] = {}
    for parent_id in sorted(document.nodes):
        parent = document.nodes[parent_id]
        for child_id in parent.children:
            if child_id not in node_ids:
                _add(
                    violations,
                    "node.missing_child",
                    f"node {parent_id!r} references missing child {child_id!r}",
                    path=f"nodes.{parent_id}.children",
                )
                continue
            parents_by_child.setdefault(child_id, []).append(parent_id)
            child = document.nodes[child_id]
            if child.parent_id != parent_id:
                _add(
                    violations,
                    "node.parent_child_mismatch",
                    f"child {child_id!r} parent_id does not match parent {parent_id!r}",
                    path=f"nodes.{child_id}.parent_id",
                )

    for child_id in sorted(parents_by_child):
        parents = parents_by_child[child_id]
        if len(parents) > 1:
            _add(
                violations,
                "node.multiple_parents",
                f"node {child_id!r} is referenced by multiple parents",
                path=f"nodes.{child_id}",
                details={"parents": sorted(parents)},
            )
    for node_id in sorted(document.nodes):
        node = document.nodes[node_id]
        if node.parent_id is not None:
            if node.parent_id not in node_ids:
                _add(
                    violations,
                    "node.missing_parent",
                    f"node {node_id!r} references missing parent {node.parent_id!r}",
                    path=f"nodes.{node_id}.parent_id",
                )
            elif node_id not in document.nodes[node.parent_id].children:
                _add(
                    violations,
                    "node.parent_child_mismatch",
                    f"parent {node.parent_id!r} does not reference child {node_id!r}",
                    path=f"nodes.{node_id}.parent_id",
                )

    state: dict[str, int] = {}
    reported_cycles: set[tuple[str, ...]] = set()

    def visit(node_id: str, stack: tuple[str, ...]) -> None:
        current = state.get(node_id, 0)
        if current == 2:
            return
        if current == 1:
            if node_id in stack:
                start = stack.index(node_id)
                cycle = stack[start:] + (node_id,)
            else:
                cycle = stack + (node_id,)
            if cycle not in reported_cycles:
                reported_cycles.add(cycle)
                _add(
                    violations,
                    "node.cycle",
                    "node hierarchy contains a cycle",
                    path=f"nodes.{node_id}",
                    details={"cycle": list(cycle)},
                )
            return
        state[node_id] = 1
        for child_id in document.nodes[node_id].children:
            if child_id in node_ids:
                visit(child_id, stack + (node_id,))
        state[node_id] = 2

    for node_id in sorted(document.nodes):
        if state.get(node_id, 0) == 0:
            visit(node_id, ())

    resource_ids = set(document.resources)
    for key in sorted(document.resources):
        resource = document.resources[key]
        if resource.resource_id != key:
            _add(
                violations,
                "resource.key_mismatch",
                f"resource map key {key!r} does not match resource_id {resource.resource_id!r}",
                path=f"resources.{key}",
            )
        _check_digest(violations, resource.sha256, f"resources.{key}.sha256")

    payload_ids = set(document.native_payloads)
    for key in sorted(document.native_payloads):
        payload = document.native_payloads[key]
        if payload.payload_id != key:
            _add(
                violations,
                "native_payload.key_mismatch",
                f"native payload map key {key!r} does not match payload_id {payload.payload_id!r}",
                path=f"native_payloads.{key}",
            )
        _check_digest(violations, payload.sha256, f"native_payloads.{key}.sha256")

    if document.source is not None:
        _check_digest(violations, document.source.sha256, "source.sha256")

    for node_id in sorted(document.nodes):
        payload = document.nodes[node_id].payload
        if isinstance(payload, ImagePayload) and payload.resource_id not in resource_ids:
            _add(
                violations,
                "resource.missing",
                f"image node {node_id!r} references missing resource {payload.resource_id!r}",
                path=f"nodes.{node_id}.payload.resource_id",
            )
        if isinstance(payload, (ChartPayload, UnknownNativePayload)):
            native_ref = payload.native_payload_ref
            if native_ref is not None and native_ref not in payload_ids:
                _add(
                    violations,
                    "native_payload.missing",
                    f"node {node_id!r} references missing native payload {native_ref!r}",
                    path=f"nodes.{node_id}.payload.native_payload_ref",
                )
        if isinstance(payload, TablePayload):
            for cell_index, cell in enumerate(payload.cells):
                for referenced_id in cell.node_ids:
                    if referenced_id not in node_ids:
                        _add(
                            violations,
                            "table.missing_node",
                            f"table node {node_id!r} references missing cell node {referenced_id!r}",
                            path=f"nodes.{node_id}.payload.cells.{cell_index}.node_ids",
                        )

    known_internal_ids = node_ids | canvas_id_set | resource_ids | payload_ids | {document.document_id}
    relationship_ids = [rel.relationship_id for rel in document.relationships]
    for duplicate in sorted(_duplicates(relationship_ids)):
        _add(
            violations,
            "relationship.duplicate_id",
            f"duplicate relationship id: {duplicate}",
            path="relationships",
        )
    for index, rel in enumerate(document.relationships):
        if rel.source_id not in known_internal_ids:
            _add(
                violations,
                "relationship.missing_source",
                f"relationship source {rel.source_id!r} does not exist",
                path=f"relationships.{index}.source_id",
            )
        if rel.target_id is not None and rel.target_id not in known_internal_ids:
            _add(
                violations,
                "relationship.missing_target",
                f"relationship target {rel.target_id!r} does not exist",
                path=f"relationships.{index}.target_id",
            )

    edit_ids = [edit.operation_id for edit in document.edits]
    for duplicate in sorted(_duplicates(edit_ids)):
        _add(
            violations,
            "edit.duplicate_id",
            f"duplicate edit operation id: {duplicate}",
            path="edits",
        )
    for index, edit in enumerate(document.edits):
        if edit.type != "add_node" and edit.target_node_id is not None and edit.target_node_id not in node_ids:
            _add(
                violations,
                "edit.missing_target",
                f"edit operation {edit.operation_id!r} references missing node {edit.target_node_id!r}",
                path=f"edits.{index}.target_node_id",
            )
        if edit.precondition is not None:
            _check_digest(
                violations,
                edit.precondition.expected_semantic_digest,
                f"edits.{index}.precondition.expected_semantic_digest",
            )
            _check_digest(
                violations,
                edit.precondition.expected_native_locator_digest,
                f"edits.{index}.precondition.expected_native_locator_digest",
            )

    if violations:
        raise IRValidationError(
            "IR validation failed",
            details={"violations": [violation.as_dict() for violation in violations]},
        )
