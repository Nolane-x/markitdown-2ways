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
from ...ir.nodes import Node, TextPayload
from ...ir.provenance import NativeLocator, Provenance
from ...ir.serialization import validate_document
from ...readers.base import DocumentIRReader
from .model import IpynbCellEvidence, ParsedIpynbSource
from .parser import IpynbParseError, parse_ipynb_source


_IPYNB_EXTENSIONS = frozenset({".ipynb"})
_IPYNB_MIMETYPES = frozenset({"application/x-ipynb+json"})
_JSON_MIMETYPES = frozenset({"application/json"})
_SUPPORTED_CELL_TYPES = frozenset({"markdown", "code", "raw"})


def _read_source_bytes(source: BinaryIO) -> bytes:
    data = source.read()
    if isinstance(data, str):
        raise TypeError("IPYNB source stream must return bytes")
    if not isinstance(data, (bytes, bytearray, memoryview)):
        raise TypeError("IPYNB source stream returned a non-bytes value")
    return bytes(data)


def _node_id(source_digest: str, label: str) -> str:
    label_digest = sha256(label.encode("utf-8")).hexdigest()[:20]
    return f"ipynb-{source_digest[:16]}-{label_digest}"


def _read_only_capability(reason: str) -> CapabilityDecision:
    return CapabilityDecision(
        operation="replace_ipynb_cell_source",
        state=CapabilityState.READ_ONLY,
        reason_code=reason,
    )


def _source_capability(
    cell: IpynbCellEvidence,
    *,
    byte_roundtrip: bool,
) -> CapabilityDecision:
    if cell.cell_type not in _SUPPORTED_CELL_TYPES:
        return _read_only_capability("ipynb.cell.unsupported_type")
    if cell.source_representation == "string-array" and not cell.source_segment_pointers:
        return _read_only_capability(
            "ipynb.cell.source.empty_array_requires_structure"
        )
    if not byte_roundtrip:
        return _read_only_capability("ipynb.encoding.not_roundtrippable")
    return CapabilityDecision(
        operation="replace_ipynb_cell_source",
        state=CapabilityState.WRITABLE,
        constraints={
            "identity_markdown": False,
            "source_preservation": "json-scalar-source-segments",
            "structural_edits": False,
            "target_only": True,
            "outputs_preserved": True,
        },
    )


def _source_role(cell_type: str) -> str:
    if cell_type == "markdown":
        return "ipynb-markdown-source"
    if cell_type == "code":
        return "code"
    if cell_type == "raw":
        return "ipynb-raw-source"
    return "ipynb-cell-source"


def _cell_role(cell_type: str) -> str:
    if cell_type in _SUPPORTED_CELL_TYPES:
        return f"ipynb-{cell_type}-cell"
    return "ipynb-cell"


def _root_metadata(parsed: ParsedIpynbSource) -> dict[str, Any]:
    return {
        "ipynb.nbformat": parsed.nbformat,
        "ipynb.nbformat_minor": parsed.nbformat_minor,
        "ipynb.writable_version": parsed.writable_version,
        "ipynb.read_only_reason": parsed.read_only_reason,
        "ipynb.top_level_non_cells_digest": parsed.top_level_non_cells_digest,
        "ipynb.root_start": parsed.root_start,
        "ipynb.root_end": parsed.root_end,
        "ipynb.root_raw_digest": parsed.root_raw_digest,
        "ipynb.encoding": parsed.representation.encoding,
        "ipynb.bom": parsed.representation.bom,
        "ipynb.byte_roundtrip": parsed.representation.byte_roundtrip,
        "ipynb.native_source": True,
    }


def _cell_metadata(cell: IpynbCellEvidence) -> dict[str, Any]:
    return {
        "ipynb.cell_index": cell.index,
        "ipynb.cell_type": cell.cell_type,
        "ipynb.cell_id": cell.cell_id,
        "ipynb.non_source_digest": cell.non_source_digest,
        "ipynb.cell_start": cell.cell_start,
        "ipynb.cell_end": cell.cell_end,
        "ipynb.cell_raw_digest": cell.cell_raw_digest,
        "ipynb.native_source": True,
    }


def _source_metadata(
    cell: IpynbCellEvidence,
    parsed: ParsedIpynbSource,
    capability: CapabilityDecision,
) -> dict[str, Any]:
    return {
        "ipynb.cell_index": cell.index,
        "ipynb.cell_type": cell.cell_type,
        "ipynb.cell_id": cell.cell_id,
        "ipynb.non_source_digest": cell.non_source_digest,
        "ipynb.source_pointer": cell.source_pointer,
        "ipynb.source_representation": cell.source_representation,
        "ipynb.source_segment_pointers": cell.source_segment_pointers,
        "ipynb.source_segment_raw_digests": cell.source_segment_raw_digests,
        "ipynb.source_segment_values": cell.source_segment_values,
        "ipynb.source_start": cell.source_start,
        "ipynb.source_end": cell.source_end,
        "ipynb.source_raw_digest": cell.source_raw_digest,
        "ipynb.encoding": parsed.representation.encoding,
        "ipynb.bom": parsed.representation.bom,
        "ipynb.byte_roundtrip": parsed.representation.byte_roundtrip,
        "ipynb.native_source": True,
        "ipynb.identity_markdown": False,
        "text.native_source": True,
        CAPABILITY_METADATA_KEY: encode_capabilities((capability,)),
    }


def read_ipynb_ir(
    source: BinaryIO,
    *,
    filename: str | None = None,
    mimetype: str | None = None,
    encoding: str | None = None,
) -> DocumentIR:
    source_bytes = _read_source_bytes(source)
    source_digest = sha256(source_bytes).hexdigest()
    parsed = parse_ipynb_source(source_bytes, encoding=encoding)
    canvas_id = f"ipynb-canvas-{source_digest[:24]}"
    root_locator = NativeLocator(
        backend="ipynb",
        part_uri="/",
        object_id="notebook",
        path="",
    )

    if not parsed.writable_version:
        root_id = _node_id(source_digest, "notebook-root")
        root_metadata = _root_metadata(parsed)
        root_metadata[CAPABILITY_METADATA_KEY] = encode_capabilities(
            (_read_only_capability(parsed.read_only_reason or "ipynb.read_only"),)
        )
        root = Node(
            node_id=root_id,
            kind="unknown_native",
            semantic_role="ipynb-notebook",
            canvas_id=canvas_id,
            provenance=(
                Provenance(
                    source_format="ipynb",
                    canvas_index=0,
                    part_uri="/",
                    char_span=(parsed.root_start, parsed.root_end),
                    extraction_method="ipynb-strict-json",
                ),
            ),
            native_locator=root_locator,
            metadata=root_metadata,
        )
        document = DocumentIR(
            document_id=f"ipynb-document-{source_digest[:24]}",
            source=SourceDescriptor(
                format="ipynb",
                filename=filename,
                mimetype=mimetype,
                sha256=source_digest,
                size_bytes=len(source_bytes),
                preserved_source_ref=f"ipynb:sha256:{source_digest}",
            ),
            canvases=(
                Canvas(
                    canvas_id=canvas_id,
                    index=0,
                    kind="notebook",
                    name=filename,
                    root_node_ids=(root_id,),
                    native_locator=root_locator,
                ),
            ),
            nodes={root_id: root},
            root_node_ids=(root_id,),
        )
        validate_document(document)
        return document

    root_id = _node_id(source_digest, "notebook-root")
    cell_ids = {
        cell.index: _node_id(source_digest, f"cell:{cell.index}")
        for cell in parsed.cells
    }
    source_ids = {
        cell.index: _node_id(source_digest, f"source:{cell.source_pointer}")
        for cell in parsed.cells
    }

    root_metadata = _root_metadata(parsed)
    root_metadata["ipynb.cell_count"] = len(parsed.cells)
    root_metadata[CAPABILITY_METADATA_KEY] = encode_capabilities(
        (_read_only_capability("ipynb.notebook.structure_read_only"),)
    )

    nodes: dict[str, Node] = {}
    nodes[root_id] = Node(
        node_id=root_id,
        kind="group",
        semantic_role="ipynb-notebook",
        children=tuple(cell_ids[cell.index] for cell in parsed.cells),
        canvas_id=canvas_id,
        provenance=(
            Provenance(
                source_format="ipynb",
                canvas_index=0,
                part_uri="/",
                char_span=(parsed.root_start, parsed.root_end),
                extraction_method="ipynb-strict-json",
            ),
        ),
        native_locator=root_locator,
        metadata=root_metadata,
    )

    for cell in parsed.cells:
        cell_id = cell_ids[cell.index]
        source_id = source_ids[cell.index]
        cell_metadata = _cell_metadata(cell)
        cell_metadata[CAPABILITY_METADATA_KEY] = encode_capabilities(
            (_read_only_capability("ipynb.cell.structure_read_only"),)
        )
        nodes[cell_id] = Node(
            node_id=cell_id,
            kind="group",
            semantic_role=_cell_role(cell.cell_type),
            parent_id=root_id,
            children=(source_id,),
            order=cell.index,
            canvas_id=canvas_id,
            provenance=(
                Provenance(
                    source_format="ipynb",
                    canvas_index=0,
                    part_uri="/",
                    char_span=(cell.cell_start, cell.cell_end),
                    extraction_method="ipynb-strict-json",
                ),
            ),
            native_locator=NativeLocator(
                backend="ipynb",
                part_uri="/",
                object_id="cell",
                path=f"/cells/{cell.index}",
            ),
            metadata=cell_metadata,
        )

        capability = _source_capability(
            cell,
            byte_roundtrip=parsed.representation.byte_roundtrip,
        )
        nodes[source_id] = Node(
            node_id=source_id,
            kind="text",
            semantic_role=_source_role(cell.cell_type),
            parent_id=cell_id,
            order=0,
            canvas_id=canvas_id,
            provenance=(
                Provenance(
                    source_format="ipynb",
                    canvas_index=0,
                    part_uri="/",
                    char_span=(cell.source_start, cell.source_end),
                    extraction_method="ipynb-strict-json",
                ),
            ),
            native_locator=NativeLocator(
                backend="ipynb",
                part_uri="/",
                object_id="cell-source",
                path=cell.source_pointer,
            ),
            payload=TextPayload(text=cell.logical_source),
            metadata=_source_metadata(cell, parsed, capability),
        )

    document = DocumentIR(
        document_id=f"ipynb-document-{source_digest[:24]}",
        source=SourceDescriptor(
            format="ipynb",
            filename=filename,
            mimetype=mimetype,
            sha256=source_digest,
            size_bytes=len(source_bytes),
            preserved_source_ref=f"ipynb:sha256:{source_digest}",
        ),
        canvases=(
            Canvas(
                canvas_id=canvas_id,
                index=0,
                kind="notebook",
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


def _clean_mimetype(value: str | None) -> str:
    return (value or "").split(";", 1)[0].strip().lower()


def _probe_notebook(file_stream: BinaryIO) -> bool:
    try:
        position = file_stream.tell()
    except (AttributeError, OSError):
        return False
    try:
        data = file_stream.read()
        if not isinstance(data, (bytes, bytearray, memoryview)):
            return False
        try:
            parsed = parse_ipynb_source(bytes(data))
        except (IpynbParseError, TypeError, ValueError):
            return False
        return (
            isinstance(parsed.nbformat, int)
            and not isinstance(parsed.nbformat, bool)
            and isinstance(parsed.nbformat_minor, int)
            and not isinstance(parsed.nbformat_minor, bool)
        )
    finally:
        try:
            file_stream.seek(position)
        except (AttributeError, OSError):
            pass


class IpynbIRReader(DocumentIRReader):
    def accepts(self, file_stream: BinaryIO, stream_info: Any, **kwargs: Any) -> bool:
        del kwargs
        extension = (getattr(stream_info, "extension", None) or "").lower()
        mimetype = _clean_mimetype(getattr(stream_info, "mimetype", None))
        if extension in _IPYNB_EXTENSIONS or mimetype in _IPYNB_MIMETYPES:
            return True
        if mimetype in _JSON_MIMETYPES:
            return _probe_notebook(file_stream)
        return False

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
            raise TypeError(f"unexpected IPYNB reader options: {sorted(kwargs)}")
        return read_ipynb_ir(
            file_stream,
            filename=getattr(stream_info, "filename", None),
            mimetype=getattr(stream_info, "mimetype", None),
            encoding=encoding,
        )
