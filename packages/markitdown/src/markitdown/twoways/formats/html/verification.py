from __future__ import annotations

from collections.abc import Mapping
from io import BytesIO
from typing import Any

from ..._errors import RoundTripVerificationError
from ...ir.document import DocumentIR
from ...ir.nodes import Node
from ..text.model import TextRepresentation
from .reader import read_html_ir


_SCALAR_KINDS = frozenset(
    {"attribute", "text", "comment", "doctype", "rawtext", "rcdata"}
)


def _failure(message: str, reason: str, **details: object) -> None:
    raise RoundTripVerificationError(
        message,
        details={"reason": reason, **details},
    )


def _nodes_by_path(document: DocumentIR) -> dict[str, Node]:
    result: dict[str, Node] = {}
    for node in document.nodes.values():
        path = node.metadata.get("html.path")
        if not isinstance(path, str) or not path:
            _failure(
                "HTML candidate contains invalid ownership metadata.",
                "html.candidate.path",
                node_id=node.node_id,
            )
        if path in result:
            _failure(
                "HTML candidate contains ambiguous ownership paths.",
                "html.candidate.duplicate_path",
                path=path,
            )
        result[path] = node
    return result


def _path_for_node(document: DocumentIR, node_id: str | None) -> str | None:
    if node_id is None:
        return None
    node = document.nodes.get(node_id)
    if node is None:
        _failure(
            "HTML candidate topology references a missing node.",
            "html.candidate.topology_missing_node",
            node_id=node_id,
        )
    path = node.metadata.get("html.path")
    if not isinstance(path, str):
        _failure(
            "HTML candidate topology references invalid ownership.",
            "html.candidate.topology_path",
            node_id=node_id,
        )
    return path


def _topology(
    document: DocumentIR,
    nodes: Mapping[str, Node],
) -> dict[str, tuple[str, str | None, tuple[str, ...]]]:
    result: dict[str, tuple[str, str | None, tuple[str, ...]]] = {}
    for path, node in nodes.items():
        kind = node.metadata.get("html.kind")
        if not isinstance(kind, str):
            _failure(
                "HTML candidate contains invalid owner-kind evidence.",
                "html.candidate.kind",
                path=path,
            )
        parent_path = _path_for_node(document, node.parent_id)
        child_paths_list: list[str] = []
        for child_id in node.children:
            child_path = _path_for_node(document, child_id)
            if child_path is None:
                _failure(
                    "HTML candidate contains invalid child ownership.",
                    "html.candidate.child_path",
                    path=path,
                )
            child_paths_list.append(child_path)
        result[path] = (kind, parent_path, tuple(child_paths_list))
    return result


def _root(document: DocumentIR, nodes: Mapping[str, Node]) -> Node:
    root = nodes.get("/")
    if root is None or document.root_node_ids != (root.node_id,):
        _failure(
            "HTML candidate document-root ownership changed.",
            "html.candidate.root",
        )
    return root


def _declaration_identity(value: object) -> tuple[tuple[object, ...], ...] | None:
    if not isinstance(value, (tuple, list)):
        return None
    identity: list[tuple[object, ...]] = []
    for item in value:
        if not isinstance(item, Mapping):
            return None
        identity.append(
            (
                item.get("raw"),
                item.get("raw_digest"),
                item.get("encoding"),
            )
        )
    return tuple(identity)


def _compare_root_evidence(source_root: Node, candidate_root: Node) -> None:
    if candidate_root.metadata.get("html.recovery_stable") is not True:
        _failure(
            "HTML candidate became recovery-sensitive.",
            "html.candidate.recovery_unstable",
            recovery_reason=candidate_root.metadata.get("html.recovery_reason"),
        )

    for key in (
        "html.encoding",
        "html.bom",
        "html.byte_roundtrip",
        "html.recovery_signature",
        "html.native_source",
        "html.identity_markdown",
    ):
        expected = source_root.metadata.get(key)
        actual = candidate_root.metadata.get(key)
        if actual != expected:
            _failure(
                "HTML candidate changed protected document evidence.",
                "html.candidate.root_evidence",
                key=key,
                expected=expected,
                actual=actual,
            )

    expected_declarations = _declaration_identity(
        source_root.metadata.get("html.encoding_declarations")
    )
    actual_declarations = _declaration_identity(
        candidate_root.metadata.get("html.encoding_declarations")
    )
    if expected_declarations is None or actual_declarations is None:
        _failure(
            "HTML candidate contains malformed encoding-declaration evidence.",
            "html.candidate.encoding_declaration_shape",
        )
    if actual_declarations != expected_declarations:
        _failure(
            "HTML candidate changed encoding declaration spelling or meaning.",
            "html.candidate.encoding_declarations",
            expected=expected_declarations,
            actual=actual_declarations,
        )


def _compare_owner_identity(path: str, source: Node, candidate: Node) -> None:
    for key in ("html.kind", "html.qname", "html.normalized_name"):
        expected = source.metadata.get(key)
        actual = candidate.metadata.get(key)
        if actual != expected:
            _failure(
                "HTML candidate changed native owner identity.",
                "html.candidate.owner_identity",
                path=path,
                key=key,
                expected=expected,
                actual=actual,
            )

    if source.metadata.get("html.kind") == "attribute":
        expected_quote = source.metadata.get("html.quote")
        actual_quote = candidate.metadata.get("html.quote")
        if actual_quote != expected_quote:
            _failure(
                "HTML candidate changed attribute quote style.",
                "html.candidate.attribute_quote",
                path=path,
                expected=expected_quote,
                actual=actual_quote,
            )


def _verify_requested(
    path: str,
    source: Node,
    candidate: Node,
    requested: str,
) -> None:
    kind = source.metadata.get("html.kind")
    if kind not in {"text", "attribute"}:
        _failure(
            "HTML requested candidate target is not a writable scalar owner.",
            "html.candidate.requested_kind",
            path=path,
            kind=kind,
        )
    if not isinstance(candidate.payload, Mapping):
        _failure(
            "HTML requested candidate target lost semantic payload.",
            "html.candidate.requested_payload",
            path=path,
        )
    actual = candidate.payload.get("value")
    if actual != requested:
        _failure(
            "HTML candidate does not contain the requested semantic value.",
            "html.candidate.requested_value",
            path=path,
            expected=requested,
            actual=actual,
        )


def _verify_unrequested(path: str, source: Node, candidate: Node) -> None:
    kind = source.metadata.get("html.kind")
    if kind not in _SCALAR_KINDS:
        return
    expected_digest = source.metadata.get("html.raw_digest")
    actual_digest = candidate.metadata.get("html.raw_digest")
    if actual_digest != expected_digest:
        _failure(
            "HTML candidate changed raw evidence outside requested targets.",
            "html.candidate.unrequested_raw",
            path=path,
            expected=expected_digest,
            actual=actual_digest,
        )
    if candidate.payload != source.payload:
        _failure(
            "HTML candidate changed semantics outside requested targets.",
            "html.candidate.unrequested_semantics",
            path=path,
            expected=source.payload,
            actual=candidate.payload,
        )


def verify_html_candidate(
    document: DocumentIR,
    candidate: bytes,
    representation: TextRepresentation,
    requested: Mapping[str, str],
) -> None:
    descriptor = document.source
    if descriptor is None:
        _failure(
            "HTML candidate verification requires source authority.",
            "html.candidate.missing_source_descriptor",
        )

    if any(
        not isinstance(path, str) or not isinstance(value, str)
        for path, value in requested.items()
    ):
        _failure(
            "HTML candidate verification received malformed requested values.",
            "html.candidate.requested_shape",
        )

    try:
        candidate_document = read_html_ir(
            BytesIO(candidate),
            filename=descriptor.filename,
            mimetype=descriptor.mimetype,
            encoding=representation.encoding,
        )
    except (UnicodeError, ValueError, TypeError) as exc:
        raise RoundTripVerificationError(
            "HTML candidate failed strict re-read verification.",
            details={"reason": "html.candidate.reread"},
        ) from exc

    source_nodes = _nodes_by_path(document)
    candidate_nodes = _nodes_by_path(candidate_document)
    source_root = _root(document, source_nodes)
    candidate_root = _root(candidate_document, candidate_nodes)
    _compare_root_evidence(source_root, candidate_root)

    if set(candidate_nodes) != set(source_nodes):
        _failure(
            "HTML candidate changed the lexical ownership path set.",
            "html.candidate.path_set",
            expected=tuple(sorted(source_nodes)),
            actual=tuple(sorted(candidate_nodes)),
        )

    source_topology = _topology(document, source_nodes)
    candidate_topology = _topology(candidate_document, candidate_nodes)
    if candidate_topology != source_topology:
        _failure(
            "HTML candidate changed native parent/child topology.",
            "html.candidate.topology",
            expected=source_topology,
            actual=candidate_topology,
        )

    missing_requested = set(requested) - set(source_nodes)
    if missing_requested:
        _failure(
            "HTML requested candidate target is missing from source ownership.",
            "html.candidate.requested_missing",
            paths=tuple(sorted(missing_requested)),
        )

    for path, source_node in source_nodes.items():
        candidate_node = candidate_nodes[path]
        _compare_owner_identity(path, source_node, candidate_node)
        if path in requested:
            _verify_requested(path, source_node, candidate_node, requested[path])
        else:
            _verify_unrequested(path, source_node, candidate_node)
