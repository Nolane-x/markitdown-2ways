from __future__ import annotations

from dataclasses import fields, is_dataclass
from hashlib import sha256
import json
from typing import Any, Mapping

from .._errors import PatchPreconditionError
from .document import DocumentIR
from .edits import EditOperation
from .nodes import ChartPayload, ImagePayload, Node, TablePayload, TextPayload


def _jsonable(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return {
            field.name: _jsonable(getattr(value, field.name))
            for field in fields(value)
            if getattr(value, field.name) is not None
        }
    if isinstance(value, Mapping):
        return {str(key): _jsonable(value[key]) for key in sorted(value, key=str)}
    if isinstance(value, (tuple, list)):
        return [_jsonable(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return repr(value)


def stable_digest(value: Any) -> str:
    payload = json.dumps(
        _jsonable(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return sha256(payload.encode("utf-8")).hexdigest()


def node_semantic_text(node: Node) -> str:
    payload = node.payload
    if isinstance(payload, TextPayload):
        if payload.paragraphs:
            return "\n".join(
                "".join(run.text for run in paragraph.runs)
                for paragraph in payload.paragraphs
            )
        return payload.text
    if isinstance(payload, ImagePayload):
        return payload.alt_text or ""
    if isinstance(payload, TablePayload):
        rows: list[str] = []
        for row_index in range(payload.rows):
            cells = [
                cell.text or ""
                for cell in sorted(
                    (cell for cell in payload.cells if cell.row == row_index),
                    key=lambda cell: cell.column,
                )
            ]
            rows.append("\t".join(cells))
        return "\n".join(rows)
    if isinstance(payload, ChartPayload):
        return payload.title or ""
    return ""


def node_semantic_digest(node: Node) -> str:
    payload = node.payload
    structured: dict[str, Any] = {
        "kind": node.kind,
        "semantic_role": node.semantic_role,
        "semantic_text": node_semantic_text(node),
    }
    if isinstance(payload, TextPayload):
        structured["text"] = payload.text
        structured["paragraphs"] = [
            [run.text for run in paragraph.runs] for paragraph in payload.paragraphs
        ]
    elif isinstance(payload, ImagePayload):
        structured["alt_text"] = payload.alt_text
        structured["resource_id"] = payload.resource_id
    return stable_digest(structured)


def native_locator_digest(node: Node) -> str | None:
    return None if node.native_locator is None else stable_digest(node.native_locator)

def validate_edit_preconditions(
    document: DocumentIR,
    node: Node,
    edit: EditOperation,
    *,
    format_label: str,
) -> None:
    def fail(reason: str, actual: object) -> None:
        raise PatchPreconditionError(
            f"{format_label} edit precondition failed.",
            details={
                "reason": reason,
                "operation_id": edit.operation_id,
                "target_node_id": edit.target_node_id,
                "actual": actual,
            },
        )

    if edit.target_node_id != node.node_id or node.node_id not in document.nodes:
        fail("target_mismatch", node.node_id)
    precondition = edit.precondition
    if precondition is None:
        return
    checks = (
        (
            "semantic_digest",
            precondition.expected_semantic_digest,
            node_semantic_digest,
        ),
        (
            "native_locator_digest",
            precondition.expected_native_locator_digest,
            native_locator_digest,
        ),
        ("old_value", precondition.expected_old_value, node_semantic_text),
    )
    for reason, expected, getter in checks:
        if expected is not None:
            actual = getter(node)
            if actual != expected:
                fail(reason, actual)

