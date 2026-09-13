from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from hashlib import sha256
from io import BytesIO

from ...capabilities import CapabilityState, capabilities_for_node
from ...ir.document import DocumentIR
from ...ir.edits import EditOperation
from ...ir.nodes import Node
from ..xml.reader import read_xml_ir


@dataclass(frozen=True)
class EpubXmlTextReplacement:
    operation_id: str
    xml_path: str
    member_sha256: str
    value: str

    def __post_init__(self) -> None:
        if not self.operation_id:
            raise ValueError("EPUB lowering operation_id must be non-empty")
        if not self.xml_path:
            raise ValueError("EPUB lowering xml_path must be non-empty")
        if not self.member_sha256:
            raise ValueError("EPUB lowering member_sha256 must be non-empty")
        if not isinstance(self.value, str):
            raise TypeError("EPUB XML text replacement value must be a string")


def _writable_text_owner(document: DocumentIR, xml_path: str) -> Node:
    matches = [
        node
        for node in document.nodes.values()
        if node.metadata.get("xml.path") == xml_path
        and node.metadata.get("xml.kind") == "text"
        and capabilities_for_node(node).for_operation("replace_xml_text").state
        is CapabilityState.WRITABLE
    ]
    if len(matches) != 1:
        raise ValueError(
            f"EPUB lowering requires exactly one writable XML text owner: {xml_path}"
        )
    return matches[0]


def lower_epub_member_edits(
    member_bytes: bytes,
    member_path: str,
    requested: Sequence[EpubXmlTextReplacement],
) -> tuple[DocumentIR, tuple[EditOperation, ...]]:
    if not isinstance(member_bytes, bytes):
        raise TypeError("EPUB member bytes must be bytes")
    if not member_path:
        raise ValueError("EPUB member path must be non-empty")

    replacements = tuple(requested)
    actual_digest = sha256(member_bytes).hexdigest()
    seen_paths: set[str] = set()
    for item in replacements:
        if not isinstance(item, EpubXmlTextReplacement):
            raise TypeError("EPUB lowering requests must be EpubXmlTextReplacement values")
        if item.member_sha256 != actual_digest:
            raise ValueError(
                "EPUB member digest does not match lowering source authority"
            )
        if item.xml_path in seen_paths:
            raise ValueError(f"duplicate EPUB XML owner: {item.xml_path}")
        seen_paths.add(item.xml_path)

    shadow = read_xml_ir(
        BytesIO(member_bytes),
        filename=member_path,
        mimetype=(
            "application/xhtml+xml"
            if member_path.lower().endswith(".xhtml")
            else "application/xml"
        ),
    )

    lowered: list[EditOperation] = []
    for item in replacements:
        node = _writable_text_owner(shadow, item.xml_path)
        lowered.append(
            EditOperation(
                operation_id=item.operation_id,
                type="replace_xml_text",
                target_node_id=node.node_id,
                payload={"value": item.value},
            )
        )

    return shadow, tuple(lowered)
