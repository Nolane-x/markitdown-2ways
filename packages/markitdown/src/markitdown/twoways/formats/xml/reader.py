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
from ..text.codec import decode_text_source
from .lexical import parse_xml_source, scan_xml_text
from .model import ParsedXmlSource, XmlLexicalError, XmlLexicalNode


_XML_EXTENSIONS = frozenset({".xml"})
_XML_MIMETYPES = frozenset({"application/xml", "text/xml"})
_WRITABLE_CONSTRAINTS = {
    "identity_markdown": False,
    "source_preservation": "lexical-source-span",
    "structural_edits": False,
    "target_only": True,
}


def _read_source_bytes(source: BinaryIO) -> bytes:
    data = source.read()
    if isinstance(data, str):
        raise TypeError("XML source stream must return bytes")
    if not isinstance(data, (bytes, bytearray, memoryview)):
        raise TypeError("XML source stream returned a non-bytes value")
    return bytes(data)


def _node_id(source_digest: str, lexeme: XmlLexicalNode) -> str:
    identity = f"{lexeme.kind}\0{lexeme.path}".encode("utf-8")
    native_digest = sha256(identity).hexdigest()[:20]
    return f"xml-native-{source_digest[:16]}-{native_digest}"


def _writable_or_encoding_read_only(
    operation: str,
    *,
    byte_roundtrip: bool,
) -> CapabilityDecision:
    if not byte_roundtrip:
        return CapabilityDecision(
            operation=operation,
            state=CapabilityState.READ_ONLY,
            reason_code="xml.encoding.not_roundtrippable",
        )
    return CapabilityDecision(
        operation=operation,
        state=CapabilityState.WRITABLE,
        constraints=_WRITABLE_CONSTRAINTS,
    )


def _capabilities(
    lexeme: XmlLexicalNode,
    *,
    byte_roundtrip: bool,
) -> tuple[CapabilityDecision, ...]:
    if lexeme.kind == "text":
        return (
            _writable_or_encoding_read_only(
                "replace_xml_text",
                byte_roundtrip=byte_roundtrip,
            ),
        )
    if lexeme.kind == "attribute":
        return (
            _writable_or_encoding_read_only(
                "replace_xml_attribute",
                byte_roundtrip=byte_roundtrip,
            ),
        )
    if lexeme.kind == "element":
        return (
            CapabilityDecision(
                operation="replace_xml_text",
                state=CapabilityState.READ_ONLY,
                reason_code="xml.element.structural_edit_unsupported",
            ),
        )
    if lexeme.kind == "namespace":
        return (
            CapabilityDecision(
                operation="replace_xml_attribute",
                state=CapabilityState.READ_ONLY,
                reason_code="xml.namespace.structural_edit_unsupported",
            ),
        )
    if lexeme.kind == "cdata":
        return (
            CapabilityDecision(
                operation="replace_xml_text",
                state=CapabilityState.READ_ONLY,
                reason_code="xml.cdata.lexical_edit_unsupported",
            ),
        )
    return ()


def _payload(lexeme: XmlLexicalNode) -> dict[str, Any]:
    if lexeme.kind == "element":
        return {
            "xml_type": "element",
            "qname": lexeme.qname,
            "expanded_name": lexeme.expanded_name,
        }
    if lexeme.kind == "attribute":
        return {
            "xml_type": "attribute",
            "qname": lexeme.qname,
            "expanded_name": lexeme.expanded_name,
            "value": lexeme.value,
        }
    if lexeme.kind == "namespace":
        return {
            "xml_type": "namespace",
            "prefix": lexeme.namespace_prefix,
            "uri": lexeme.namespace_uri,
        }
    if lexeme.kind == "text":
        return {"xml_type": "text", "value": lexeme.value}
    if lexeme.kind == "cdata":
        return {"xml_type": "cdata", "value": lexeme.value}
    if lexeme.kind == "comment":
        return {"xml_type": "comment", "value": lexeme.value}
    if lexeme.kind == "processing_instruction":
        return {
            "xml_type": "processing_instruction",
            "target": lexeme.qname,
            "data": lexeme.value,
        }
    raise AssertionError(f"unreachable XML kind: {lexeme.kind}")


def _parse_for_reader(
    source_bytes: bytes,
    *,
    encoding: str | None,
) -> ParsedXmlSource:
    try:
        return parse_xml_source(source_bytes, encoding=encoding)
    except XmlLexicalError as exc:
        if "exact decode/encode authority proof" not in str(exc):
            raise

        try:
            text, representation = decode_text_source(
                source_bytes,
                encoding=encoding,
            )
        except (UnicodeError, LookupError, ValueError):
            raise exc

        if representation.byte_roundtrip:
            raise exc

        lexical = scan_xml_text(text)
        return ParsedXmlSource(
            text=text,
            representation=representation,
            lexical=lexical,
        )


def read_xml_ir(
    source: BinaryIO,
    *,
    filename: str | None = None,
    mimetype: str | None = None,
    encoding: str | None = None,
) -> DocumentIR:
    source_bytes = _read_source_bytes(source)
    source_digest = sha256(source_bytes).hexdigest()
    parsed = _parse_for_reader(source_bytes, encoding=encoding)
    representation = parsed.representation
    lexical = parsed.lexical
    declaration = parsed.declaration

    canvas_id = f"xml-canvas-{source_digest[:24]}"
    node_ids = {
        lexeme.path: _node_id(source_digest, lexeme) for lexeme in lexical.nodes
    }

    direct_children: dict[str, list[XmlLexicalNode]] = {}
    for lexeme in lexical.nodes:
        if lexeme.parent_path is not None:
            direct_children.setdefault(lexeme.parent_path, []).append(lexeme)
    for children in direct_children.values():
        children.sort(key=lambda item: (item.start, item.end, item.path))

    nodes: dict[str, Node] = {}
    for order, lexeme in enumerate(lexical.nodes):
        capabilities = _capabilities(
            lexeme,
            byte_roundtrip=representation.byte_roundtrip,
        )
        metadata: dict[str, Any] = {
            "xml.path": lexeme.path,
            "xml.kind": lexeme.kind,
            "xml.char_start": lexeme.start,
            "xml.char_end": lexeme.end,
            "xml.raw": lexeme.raw,
            "xml.raw_digest": lexeme.raw_digest,
            "xml.qname": lexeme.qname,
            "xml.expanded_name": lexeme.expanded_name,
            "xml.value_start": lexeme.value_start,
            "xml.value_end": lexeme.value_end,
            "xml.quote": lexeme.quote,
            "xml.namespace_prefix": lexeme.namespace_prefix,
            "xml.namespace_uri": lexeme.namespace_uri,
            "xml.encoding": representation.encoding,
            "xml.bom": representation.bom,
            "xml.byte_roundtrip": representation.byte_roundtrip,
            "xml.version": declaration.version if declaration is not None else "1.0",
            "xml.declared_encoding": (
                declaration.encoding if declaration is not None else None
            ),
            "xml.standalone": (
                declaration.standalone if declaration is not None else None
            ),
            "xml.declaration_raw": (
                declaration.raw if declaration is not None else None
            ),
            "xml.declaration_raw_digest": (
                declaration.raw_digest if declaration is not None else None
            ),
            "xml.native_source": True,
            "xml.identity_markdown": False,
            CAPABILITY_METADATA_KEY: encode_capabilities(capabilities),
        }
        node_id = node_ids[lexeme.path]
        nodes[node_id] = Node(
            node_id=node_id,
            kind="unknown_native",
            semantic_role=f"xml-{lexeme.kind.replace('_', '-')}",
            order=order,
            parent_id=(
                node_ids[lexeme.parent_path]
                if lexeme.parent_path is not None
                else None
            ),
            children=tuple(
                node_ids[child.path]
                for child in direct_children.get(lexeme.path, ())
            ),
            canvas_id=canvas_id,
            provenance=(
                Provenance(
                    source_format="xml",
                    canvas_index=0,
                    part_uri="/",
                    char_span=(lexeme.start, lexeme.end),
                    extraction_method="xml-lexical",
                ),
            ),
            native_locator=NativeLocator(
                backend="xml",
                part_uri="/",
                object_id=lexeme.kind,
                path=lexeme.path,
            ),
            payload=_payload(lexeme),
            metadata=metadata,
        )

    root_id = node_ids[lexical.root_path]
    root_locator = nodes[root_id].native_locator
    document = DocumentIR(
        document_id=f"xml-document-{source_digest[:24]}",
        source=SourceDescriptor(
            format="xml",
            filename=filename,
            mimetype=mimetype,
            sha256=source_digest,
            size_bytes=len(source_bytes),
            preserved_source_ref=f"xml:sha256:{source_digest}",
        ),
        canvases=(
            Canvas(
                canvas_id=canvas_id,
                index=0,
                kind="xml",
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


class XmlIRReader(DocumentIRReader):
    def accepts(self, file_stream: BinaryIO, stream_info: Any, **kwargs: Any) -> bool:
        del file_stream, kwargs
        extension = (getattr(stream_info, "extension", None) or "").lower()
        mimetype = (
            (getattr(stream_info, "mimetype", None) or "")
            .split(";", 1)[0]
            .strip()
            .lower()
        )
        return extension in _XML_EXTENSIONS or mimetype in _XML_MIMETYPES

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
            raise TypeError(f"unexpected XML reader options: {sorted(kwargs)}")
        return read_xml_ir(
            file_stream,
            filename=getattr(stream_info, "filename", None),
            mimetype=getattr(stream_info, "mimetype", None),
            encoding=encoding,
        )
