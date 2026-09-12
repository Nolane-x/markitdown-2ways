from __future__ import annotations

from hashlib import sha256
from typing import Any, BinaryIO

from ...capabilities import (
    CAPABILITY_METADATA_KEY,
    CapabilityDecision,
    CapabilityState,
    encode_capabilities,
)
from ...ir.document import Canvas, DocumentIR, SourceDescriptor
from ...ir.nodes import Node
from ...ir.provenance import NativeLocator, Provenance
from ...ir.serialization import validate_document
from ...readers.base import DocumentIRReader
from .lexical import parse_html_source
from .model import HtmlLexicalNode, ParsedHtmlSource


_HTML_EXTENSIONS = frozenset({".html", ".htm"})
_HTML_MIMETYPES = frozenset({"text/html"})
_WRITABLE_CONSTRAINTS = {
    "identity_markdown": False,
    "source_preservation": "lexical-source-span",
    "structural_edits": False,
    "target_only": True,
    "recovery_stable": True,
}


def _read_source_bytes(source: BinaryIO) -> bytes:
    data = source.read()
    if isinstance(data, str):
        raise TypeError("HTML source stream must return bytes")
    if not isinstance(data, (bytes, bytearray, memoryview)):
        raise TypeError("HTML source stream returned a non-bytes value")
    return bytes(data)


def _node_id(source_digest: str, kind: str, path: str) -> str:
    identity = f"{kind}\0{path}".encode("utf-8")
    native_digest = sha256(identity).hexdigest()[:20]
    return f"html-native-{source_digest[:16]}-{native_digest}"


def _read_only(operation: str, reason: str) -> CapabilityDecision:
    return CapabilityDecision(
        operation=operation,
        state=CapabilityState.READ_ONLY,
        reason_code=reason,
    )


def _writable_or_encoding_read_only(
    operation: str,
    *,
    byte_roundtrip: bool,
) -> CapabilityDecision:
    if not byte_roundtrip:
        return _read_only(operation, "html.encoding.not_roundtrippable")
    return CapabilityDecision(
        operation=operation,
        state=CapabilityState.WRITABLE,
        constraints=_WRITABLE_CONSTRAINTS,
    )


def _is_encoding_attribute(
    lexeme: HtmlLexicalNode,
    lexical_by_path: dict[str, HtmlLexicalNode],
) -> bool:
    if lexeme.kind != "attribute" or lexeme.parent_path is None:
        return False
    parent = lexical_by_path.get(lexeme.parent_path)
    return bool(
        parent is not None
        and parent.kind == "element"
        and parent.normalized_name == "meta"
        and lexeme.normalized_name in {"charset", "http-equiv", "content"}
    )


def _capabilities(
    lexeme: HtmlLexicalNode,
    *,
    byte_roundtrip: bool,
    lexical_by_path: dict[str, HtmlLexicalNode],
) -> tuple[CapabilityDecision, ...]:
    if lexeme.kind == "text":
        return (
            _writable_or_encoding_read_only(
                "replace_html_text",
                byte_roundtrip=byte_roundtrip,
            ),
        )
    if lexeme.kind == "attribute":
        if lexeme.recovery_reason == "html.attribute.duplicate_name":
            return (
                _read_only("replace_html_attribute", "html.attribute.duplicate_name"),
            )
        if _is_encoding_attribute(lexeme, lexical_by_path):
            return (
                _read_only(
                    "replace_html_attribute",
                    "html.encoding.declaration_read_only",
                ),
            )
        if lexeme.value_start is None or lexeme.value_end is None:
            return (
                _read_only(
                    "replace_html_attribute",
                    "html.attribute.boolean_read_only",
                ),
            )
        if lexeme.quote is None:
            return (
                _read_only(
                    "replace_html_attribute",
                    "html.attribute.requires_quote_transition",
                ),
            )
        return (
            _writable_or_encoding_read_only(
                "replace_html_attribute",
                byte_roundtrip=byte_roundtrip,
            ),
        )
    if lexeme.kind == "element":
        return (
            _read_only(
                "replace_html_text",
                "html.element.structural_edit_unsupported",
            ),
        )
    if lexeme.kind == "rawtext":
        return (_read_only("replace_html_text", "html.raw_text.read_only"),)
    if lexeme.kind == "rcdata":
        return (_read_only("replace_html_text", "html.rcdata.read_only"),)
    return ()


def _payload(lexeme: HtmlLexicalNode) -> dict[str, Any]:
    if lexeme.kind == "element":
        return {
            "html_type": "element",
            "qname": lexeme.qname,
            "normalized_name": lexeme.normalized_name,
        }
    if lexeme.kind == "attribute":
        return {
            "html_type": "attribute",
            "qname": lexeme.qname,
            "normalized_name": lexeme.normalized_name,
            "value": lexeme.value,
        }
    if lexeme.kind in {"text", "rawtext", "rcdata", "comment", "doctype"}:
        return {"html_type": lexeme.kind, "value": lexeme.value}
    raise AssertionError(f"unreachable HTML kind: {lexeme.kind}")


def _encoding_declaration_metadata(parsed: ParsedHtmlSource) -> tuple[dict[str, Any], ...]:
    return tuple(
        {
            "start": item.start,
            "end": item.end,
            "raw": item.raw,
            "raw_digest": item.raw_digest,
            "encoding": item.encoding,
        }
        for item in parsed.encoding_declarations
    )


def _recovery_signature_metadata(parsed: ParsedHtmlSource) -> tuple[dict[str, Any], ...]:
    return tuple(
        {
            "kind": entry.kind,
            "name": entry.name,
            "depth": entry.depth,
            "attribute_names": entry.attribute_names,
        }
        for entry in parsed.recovery_signature.entries
    )


def _root_metadata(parsed: ParsedHtmlSource) -> dict[str, Any]:
    return {
        "html.path": "/",
        "html.kind": "document",
        "html.encoding": parsed.representation.encoding,
        "html.bom": parsed.representation.bom,
        "html.byte_roundtrip": parsed.representation.byte_roundtrip,
        "html.encoding_declarations": _encoding_declaration_metadata(parsed),
        "html.recovery_signature": _recovery_signature_metadata(parsed),
        "html.recovery_stable": parsed.recovery_stable,
        "html.recovery_reason": parsed.recovery_reason,
        "html.native_source": True,
        "html.identity_markdown": False,
    }


def _root_capabilities(parsed: ParsedHtmlSource) -> tuple[CapabilityDecision, ...]:
    reason = (
        "html.document.structural_edit_unsupported"
        if parsed.recovery_stable
        else parsed.recovery_reason or "html.recovery.unproven"
    )
    return (
        _read_only("replace_html_text", reason),
        _read_only("replace_html_attribute", reason),
    )


def read_html_ir(
    source: BinaryIO,
    *,
    filename: str | None = None,
    mimetype: str | None = None,
    encoding: str | None = None,
) -> DocumentIR:
    source_bytes = _read_source_bytes(source)
    source_digest = sha256(source_bytes).hexdigest()
    parsed = parse_html_source(source_bytes, encoding=encoding)
    canvas_id = f"html-canvas-{source_digest[:24]}"
    root_id = _node_id(source_digest, "document", "/")
    root_metadata = _root_metadata(parsed)
    root_metadata[CAPABILITY_METADATA_KEY] = encode_capabilities(
        _root_capabilities(parsed)
    )
    root_locator = NativeLocator(
        backend="html",
        part_uri="/",
        object_id="document",
        path="/",
    )
    root = Node(
        node_id=root_id,
        kind="unknown_native",
        semantic_role="html-document",
        order=0,
        parent_id=None,
        children=(),
        canvas_id=canvas_id,
        provenance=(
            Provenance(
                source_format="html",
                canvas_index=0,
                part_uri="/",
                char_span=(0, len(parsed.text)),
                extraction_method="html-lexical-recovery",
            ),
        ),
        native_locator=root_locator,
        payload={"html_type": "document"},
        metadata=root_metadata,
    )

    nodes: dict[str, Node] = {root_id: root}
    if parsed.recovery_stable:
        lexical_by_path = {item.path: item for item in parsed.lexical.nodes}
        node_ids = {
            item.path: _node_id(source_digest, item.kind, item.path)
            for item in parsed.lexical.nodes
        }
        top_level_ids = tuple(
            node_ids[item.path]
            for item in sorted(parsed.lexical.nodes, key=lambda value: value.order)
            if item.parent_path is None
        )
        nodes[root_id] = Node(
            node_id=root.node_id,
            kind=root.kind,
            semantic_role=root.semantic_role,
            order=root.order,
            parent_id=root.parent_id,
            children=top_level_ids,
            canvas_id=root.canvas_id,
            provenance=root.provenance,
            native_locator=root.native_locator,
            payload=root.payload,
            metadata=root.metadata,
        )

        declarations = _encoding_declaration_metadata(parsed)
        recovery_signature = _recovery_signature_metadata(parsed)
        for lexeme in parsed.lexical.nodes:
            capabilities = _capabilities(
                lexeme,
                byte_roundtrip=parsed.representation.byte_roundtrip,
                lexical_by_path=lexical_by_path,
            )
            metadata: dict[str, Any] = {
                "html.path": lexeme.path,
                "html.kind": lexeme.kind,
                "html.char_start": lexeme.start,
                "html.char_end": lexeme.end,
                "html.raw": lexeme.raw,
                "html.raw_digest": lexeme.raw_digest,
                "html.qname": lexeme.qname,
                "html.normalized_name": lexeme.normalized_name,
                "html.value_start": lexeme.value_start,
                "html.value_end": lexeme.value_end,
                "html.quote": lexeme.quote,
                "html.start_tag_start": lexeme.start_tag_start,
                "html.start_tag_end": lexeme.start_tag_end,
                "html.end_tag_start": lexeme.end_tag_start,
                "html.end_tag_end": lexeme.end_tag_end,
                "html.owner_recovery_reason": lexeme.recovery_reason,
                "html.encoding": parsed.representation.encoding,
                "html.bom": parsed.representation.bom,
                "html.byte_roundtrip": parsed.representation.byte_roundtrip,
                "html.encoding_declarations": declarations,
                "html.recovery_signature": recovery_signature,
                "html.recovery_stable": True,
                "html.recovery_reason": None,
                "html.native_source": True,
                "html.identity_markdown": False,
                CAPABILITY_METADATA_KEY: encode_capabilities(capabilities),
            }
            node_id = node_ids[lexeme.path]
            nodes[node_id] = Node(
                node_id=node_id,
                kind="unknown_native",
                semantic_role=f"html-{lexeme.kind}",
                order=lexeme.order + 1,
                parent_id=(
                    root_id
                    if lexeme.parent_path is None
                    else node_ids[lexeme.parent_path]
                ),
                children=tuple(node_ids[path] for path in lexeme.children),
                canvas_id=canvas_id,
                provenance=(
                    Provenance(
                        source_format="html",
                        canvas_index=0,
                        part_uri="/",
                        char_span=(lexeme.start, lexeme.end),
                        extraction_method="html-lexical-recovery",
                    ),
                ),
                native_locator=NativeLocator(
                    backend="html",
                    part_uri="/",
                    object_id=lexeme.kind,
                    path=lexeme.path,
                ),
                payload=_payload(lexeme),
                metadata=metadata,
            )

    document = DocumentIR(
        document_id=f"html-document-{source_digest[:24]}",
        source=SourceDescriptor(
            format="html",
            filename=filename,
            mimetype=mimetype,
            sha256=source_digest,
            size_bytes=len(source_bytes),
            preserved_source_ref=f"html:sha256:{source_digest}",
        ),
        canvases=(
            Canvas(
                canvas_id=canvas_id,
                index=0,
                kind="html",
                name=filename,
                root_node_ids=(root_id,),
                native_locator=root_locator,
            ),
        ),
        nodes=nodes,
        root_node_ids=(root_id,),
    )
    validate_document(document)
    return document


class HtmlIRReader(DocumentIRReader):
    def accepts(self, file_stream: BinaryIO, stream_info: Any, **kwargs: Any) -> bool:
        del file_stream, kwargs
        extension = (getattr(stream_info, "extension", None) or "").lower()
        mimetype = (
            (getattr(stream_info, "mimetype", None) or "")
            .split(";", 1)[0]
            .strip()
            .lower()
        )
        return extension in _HTML_EXTENSIONS or mimetype in _HTML_MIMETYPES

    def read(
        self,
        file_stream: BinaryIO,
        stream_info: Any,
        **kwargs: Any,
    ) -> DocumentIR:
        encoding = kwargs.pop("encoding", None)
        if encoding is None:
            encoding = getattr(stream_info, "charset", None)
        if kwargs:
            raise TypeError(f"unexpected HTML reader options: {sorted(kwargs)}")
        return read_html_ir(
            file_stream,
            filename=getattr(stream_info, "filename", None),
            mimetype=getattr(stream_info, "mimetype", None),
            encoding=encoding,
        )
