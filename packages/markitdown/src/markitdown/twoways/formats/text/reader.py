from __future__ import annotations

from hashlib import sha256
from pathlib import PurePath
from typing import Any, BinaryIO

from ...capabilities import (
    CAPABILITY_METADATA_KEY,
    CapabilityDecision,
    CapabilityState,
    encode_capabilities,
)
from ...ir.document import Canvas, DocumentIR, SourceDescriptor
from ...ir.nodes import Node, TextPayload
from ...ir.provenance import NativeLocator, Provenance
from ...ir.serialization import validate_document
from ...readers.base import DocumentIRReader
from .codec import decode_text_source


_TEXT_EXTENSIONS = frozenset({".txt", ".text"})
_MARKDOWN_EXTENSIONS = frozenset({".md", ".markdown"})
_TEXT_MIMETYPES = frozenset({"text/plain"})
_MARKDOWN_MIMETYPES = frozenset({"text/markdown", "application/markdown"})


def _read_source_bytes(source: BinaryIO) -> bytes:
    data = source.read()
    if isinstance(data, str):
        raise TypeError("text source stream must return bytes")
    if not isinstance(data, (bytes, bytearray, memoryview)):
        raise TypeError("text source stream returned a non-bytes value")
    return bytes(data)


def _classify_format(filename: str | None, mimetype: str | None) -> str:
    extension = PurePath(filename).suffix.lower() if filename else ""
    normalized_mimetype = (mimetype or "").split(";", 1)[0].strip().lower()
    if extension in _MARKDOWN_EXTENSIONS or normalized_mimetype in _MARKDOWN_MIMETYPES:
        return "markdown"
    return "text"


def _replace_text_capability(
    *,
    byte_roundtrip: bool,
    newline: str,
) -> CapabilityDecision:
    if not byte_roundtrip:
        return CapabilityDecision(
            operation="replace_text",
            state=CapabilityState.READ_ONLY,
            reason_code="text.encoding.not_roundtrippable",
        )
    if newline == "mixed":
        return CapabilityDecision(
            operation="replace_text",
            state=CapabilityState.READ_ONLY,
            reason_code="text.newline.mixed",
        )
    return CapabilityDecision(
        operation="replace_text",
        state=CapabilityState.WRITABLE,
        constraints={
            "identity_markdown": True,
            "source_preservation": "encoding-bom-newline",
            "whole_document": True,
        },
    )


def read_text_ir(
    source: BinaryIO,
    *,
    filename: str | None = None,
    mimetype: str | None = None,
    encoding: str | None = None,
) -> DocumentIR:
    source_bytes = _read_source_bytes(source)
    source_digest = sha256(source_bytes).hexdigest()
    text, representation = decode_text_source(source_bytes, encoding=encoding)
    source_format = _classify_format(filename, mimetype)

    document_id = f"{source_format}-document-{source_digest[:24]}"
    canvas_id = f"{source_format}-canvas-{source_digest[:24]}"
    node_id = f"{source_format}-text-{source_digest[:24]}"
    locator = NativeLocator(
        backend="text",
        part_uri="/",
        object_id="document-body",
    )
    capability = _replace_text_capability(
        byte_roundtrip=representation.byte_roundtrip,
        newline=representation.newline,
    )
    node = Node(
        node_id=node_id,
        kind="text",
        semantic_role="document-body",
        order=0,
        canvas_id=canvas_id,
        provenance=(
            Provenance(
                source_format=source_format,
                canvas_index=0,
                part_uri="/",
                char_span=(0, len(text)),
                extraction_method="text-codec",
            ),
        ),
        native_locator=locator,
        payload=TextPayload(text=text),
        metadata={
            "text.encoding": representation.encoding,
            "text.bom": representation.bom,
            "text.newline": representation.newline,
            "text.byte_roundtrip": representation.byte_roundtrip,
            "text.format": source_format,
            CAPABILITY_METADATA_KEY: encode_capabilities((capability,)),
        },
    )
    document = DocumentIR(
        document_id=document_id,
        source=SourceDescriptor(
            format=source_format,
            filename=filename,
            mimetype=mimetype,
            sha256=source_digest,
            size_bytes=len(source_bytes),
            preserved_source_ref=f"text:sha256:{source_digest}",
        ),
        canvases=(
            Canvas(
                canvas_id=canvas_id,
                index=0,
                kind="text",
                name=filename,
                root_node_ids=(node_id,),
                native_locator=locator,
            ),
        ),
        nodes={node_id: node},
        root_node_ids=(node_id,),
    )
    validate_document(document)
    return document


class TextIRReader(DocumentIRReader):
    def accepts(self, file_stream: BinaryIO, stream_info: Any, **kwargs: Any) -> bool:
        extension = (getattr(stream_info, "extension", None) or "").lower()
        mimetype = (
            (getattr(stream_info, "mimetype", None) or "")
            .split(";", 1)[0]
            .strip()
            .lower()
        )
        return (
            extension in _TEXT_EXTENSIONS
            or extension in _MARKDOWN_EXTENSIONS
            or mimetype in _TEXT_MIMETYPES
            or mimetype in _MARKDOWN_MIMETYPES
        )

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
            raise TypeError(f"unexpected text reader options: {sorted(kwargs)}")
        return read_text_ir(
            file_stream,
            filename=getattr(stream_info, "filename", None),
            mimetype=getattr(stream_info, "mimetype", None),
            encoding=encoding,
        )
