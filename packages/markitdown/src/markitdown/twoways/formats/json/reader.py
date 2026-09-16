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
from .lexical import scan_json_text
from .model import JsonLexicalNode


_JSON_EXTENSIONS = frozenset({".json"})
_JSON_MIMETYPES = frozenset({"application/json", "text/json"})
_CONTAINER_KINDS = frozenset({"object", "array"})


def _read_source_bytes(source: BinaryIO) -> bytes:
    data = source.read()
    if isinstance(data, str):
        raise TypeError("JSON source stream must return bytes")
    if not isinstance(data, (bytes, bytearray, memoryview)):
        raise TypeError("JSON source stream returned a non-bytes value")
    return bytes(data)


def _node_id(source_digest: str, pointer: str) -> str:
    pointer_digest = sha256(pointer.encode("utf-8")).hexdigest()[:20]
    return f"json-value-{source_digest[:16]}-{pointer_digest}"


def _capability(lexeme: JsonLexicalNode, *, byte_roundtrip: bool) -> CapabilityDecision:
    if lexeme.kind in _CONTAINER_KINDS:
        return CapabilityDecision(
            operation="replace_json_scalar",
            state=CapabilityState.READ_ONLY,
            reason_code="json.container.structural_edit_unsupported",
        )
    if not byte_roundtrip:
        return CapabilityDecision(
            operation="replace_json_scalar",
            state=CapabilityState.READ_ONLY,
            reason_code="json.encoding.not_roundtrippable",
        )
    return CapabilityDecision(
        operation="replace_json_scalar",
        state=CapabilityState.WRITABLE,
        constraints={
            "identity_markdown": False,
            "source_preservation": "lexical-value-span",
            "structural_edits": False,
            "target_only": True,
        },
    )


def _payload(lexeme: JsonLexicalNode) -> dict[str, Any]:
    if lexeme.kind in _CONTAINER_KINDS:
        return {"json_type": lexeme.kind, "size": len(lexeme.children)}
    if lexeme.kind == "string":
        return {"json_type": "string", "value": lexeme.value}
    if lexeme.kind == "number":
        return {"json_type": "number", "raw": lexeme.raw}
    if lexeme.kind == "boolean":
        return {"json_type": "boolean", "value": lexeme.value}
    if lexeme.kind == "null":
        return {"json_type": "null", "value": None}
    raise AssertionError(f"unreachable JSON kind: {lexeme.kind}")


def read_json_ir(
    source: BinaryIO,
    *,
    filename: str | None = None,
    mimetype: str | None = None,
    encoding: str | None = None,
) -> DocumentIR:
    source_bytes = _read_source_bytes(source)
    source_digest = sha256(source_bytes).hexdigest()
    text, representation = decode_text_source(source_bytes, encoding=encoding)
    lexical = scan_json_text(text)
    canvas_id = f"json-canvas-{source_digest[:24]}"
    node_ids = {
        lexeme.pointer: _node_id(source_digest, lexeme.pointer)
        for lexeme in lexical.nodes
    }

    nodes: dict[str, Node] = {}
    for order, lexeme in enumerate(lexical.nodes):
        locator = NativeLocator(
            backend="json",
            part_uri="/",
            object_id="value",
            path=lexeme.pointer,
        )
        capability = _capability(
            lexeme,
            byte_roundtrip=representation.byte_roundtrip,
        )
        node_id = node_ids[lexeme.pointer]
        nodes[node_id] = Node(
            node_id=node_id,
            kind="unknown_native",
            semantic_role=f"json-{lexeme.kind}",
            order=order,
            parent_id=(
                node_ids[lexeme.parent_pointer]
                if lexeme.parent_pointer is not None
                else None
            ),
            children=tuple(node_ids[pointer] for pointer in lexeme.children),
            canvas_id=canvas_id,
            provenance=(
                Provenance(
                    source_format="json",
                    canvas_index=0,
                    part_uri="/",
                    char_span=(lexeme.start, lexeme.end),
                    extraction_method="json-lexical",
                ),
            ),
            native_locator=locator,
            payload=_payload(lexeme),
            metadata={
                "json.pointer": lexeme.pointer,
                "json.kind": lexeme.kind,
                "json.char_start": lexeme.start,
                "json.char_end": lexeme.end,
                "json.raw": lexeme.raw,
                "json.raw_digest": lexeme.raw_digest,
                "json.encoding": representation.encoding,
                "json.bom": representation.bom,
                "json.byte_roundtrip": representation.byte_roundtrip,
                "json.native_source": True,
                "json.identity_markdown": False,
                CAPABILITY_METADATA_KEY: encode_capabilities((capability,)),
            },
        )

    root_id = node_ids[lexical.root_pointer]
    root_locator = nodes[root_id].native_locator
    document = DocumentIR(
        document_id=f"json-document-{source_digest[:24]}",
        source=SourceDescriptor(
            format="json",
            filename=filename,
            mimetype=mimetype,
            sha256=source_digest,
            size_bytes=len(source_bytes),
            preserved_source_ref=f"json:sha256:{source_digest}",
        ),
        canvases=(
            Canvas(
                canvas_id=canvas_id,
                index=0,
                kind="json",
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


class JsonIRReader(DocumentIRReader):
    def accepts(self, file_stream: BinaryIO, stream_info: Any, **kwargs: Any) -> bool:
        del file_stream, kwargs
        extension = (getattr(stream_info, "extension", None) or "").lower()
        mimetype = (
            (getattr(stream_info, "mimetype", None) or "")
            .split(";", 1)[0]
            .strip()
            .lower()
        )
        return extension in _JSON_EXTENSIONS or mimetype in _JSON_MIMETYPES

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
            raise TypeError(f"unexpected JSON reader options: {sorted(kwargs)}")
        return read_json_ir(
            file_stream,
            filename=getattr(stream_info, "filename", None),
            mimetype=getattr(stream_info, "mimetype", None),
            encoding=encoding,
        )
