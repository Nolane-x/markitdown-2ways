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
from ...ir.nodes import Node, TableCell, TablePayload
from ...ir.provenance import NativeLocator, Provenance
from ...ir.serialization import validate_document
from ...readers.base import DocumentIRReader
from ..text.codec import decode_text_source
from .lexical import resolve_csv_text


_CSV_EXTENSIONS = frozenset({".csv"})
_CSV_MIMETYPES = frozenset({"text/csv", "application/csv"})
_TERMINATOR_NAMES = {"\r\n": "crlf", "\n": "lf", "\r": "cr", "": "eof"}


def _read_source_bytes(source: BinaryIO) -> bytes:
    data = source.read()
    if isinstance(data, str):
        raise TypeError("CSV source stream must return bytes")
    if not isinstance(data, (bytes, bytearray, memoryview)):
        raise TypeError("CSV source stream returned a non-bytes value")
    return bytes(data)


def _capability(
    *,
    byte_roundtrip: bool,
    dialect_proven: bool,
    dialect_reason: str | None,
    field_count: int,
) -> CapabilityDecision:
    if not byte_roundtrip:
        return CapabilityDecision(
            operation="update_csv_cells",
            state=CapabilityState.READ_ONLY,
            reason_code="csv.encoding.not_roundtrippable",
        )
    if not dialect_proven:
        return CapabilityDecision(
            operation="update_csv_cells",
            state=CapabilityState.READ_ONLY,
            reason_code=dialect_reason or "csv.dialect.ambiguous",
        )
    if field_count == 0:
        return CapabilityDecision(
            operation="update_csv_cells",
            state=CapabilityState.READ_ONLY,
            reason_code="csv.table.no_writable_cells",
        )
    return CapabilityDecision(
        operation="update_csv_cells",
        state=CapabilityState.WRITABLE,
        constraints={
            "identity_markdown": False,
            "source_preservation": "lexical-field-spans",
            "structural_edits": False,
            "target_only": True,
        },
    )


def _row_terminators(rows) -> tuple[str, ...]:
    names: list[str] = []
    for row in rows:
        name = _TERMINATOR_NAMES[row.terminator]
        if name == "eof":
            continue
        if name not in names:
            names.append(name)
    return tuple(names)


def read_csv_ir(
    source: BinaryIO,
    *,
    filename: str | None = None,
    mimetype: str | None = None,
    encoding: str | None = None,
    delimiter: str | None = None,
) -> DocumentIR:
    source_bytes = _read_source_bytes(source)
    source_digest = sha256(source_bytes).hexdigest()
    text, representation = decode_text_source(source_bytes, encoding=encoding)
    lexical = resolve_csv_text(text, delimiter=delimiter)
    fields = tuple(field for row in lexical.rows for field in row.fields)
    capability = _capability(
        byte_roundtrip=representation.byte_roundtrip,
        dialect_proven=lexical.dialect_proven,
        dialect_reason=lexical.reason_code,
        field_count=len(fields),
    )
    writable = capability.state is CapabilityState.WRITABLE

    table_cells = tuple(
        TableCell(
            row=field.row,
            column=field.column,
            text=field.value,
            metadata={
                "csv.row": field.row,
                "csv.column": field.column,
                "csv.char_start": field.start,
                "csv.char_end": field.end,
                "csv.quoted": field.quoted,
                "csv.multiline": field.multiline,
                "csv.raw_digest": field.raw_digest,
                "csv.present": True,
                "csv.writable": writable,
                "csv.reason_code": None if writable else capability.reason_code,
            },
        )
        for field in fields
    )
    columns = max((len(row.fields) for row in lexical.rows), default=0)
    canvas_id = f"csv-canvas-{source_digest[:24]}"
    node_id = f"csv-table-{source_digest[:24]}"
    locator = NativeLocator(
        backend="csv",
        part_uri="/",
        object_id="table",
    )
    node = Node(
        node_id=node_id,
        kind="table",
        semantic_role="csv-grid",
        order=0,
        canvas_id=canvas_id,
        provenance=(
            Provenance(
                source_format="csv",
                canvas_index=0,
                part_uri="/",
                char_span=(0, len(text)),
                extraction_method="csv-lexical",
            ),
        ),
        native_locator=locator,
        payload=TablePayload(
            rows=len(lexical.rows),
            columns=columns,
            cells=table_cells,
        ),
        metadata={
            "csv.delimiter": lexical.delimiter,
            "csv.dialect_proven": lexical.dialect_proven,
            "csv.quotechar": '"',
            "csv.doublequote": True,
            "csv.escapechar": None,
            "csv.skipinitialspace": False,
            "csv.encoding": representation.encoding,
            "csv.bom": representation.bom,
            "csv.byte_roundtrip": representation.byte_roundtrip,
            "csv.identity_markdown": False,
            "csv.row_terminators": _row_terminators(lexical.rows),
            CAPABILITY_METADATA_KEY: encode_capabilities((capability,)),
        },
    )
    document = DocumentIR(
        document_id=f"csv-document-{source_digest[:24]}",
        source=SourceDescriptor(
            format="csv",
            filename=filename,
            mimetype=mimetype,
            sha256=source_digest,
            size_bytes=len(source_bytes),
            preserved_source_ref=f"csv:sha256:{source_digest}",
        ),
        canvases=(
            Canvas(
                canvas_id=canvas_id,
                index=0,
                kind="table",
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


class CsvIRReader(DocumentIRReader):
    def accepts(self, file_stream: BinaryIO, stream_info: Any, **kwargs: Any) -> bool:
        del file_stream, kwargs
        extension = (getattr(stream_info, "extension", None) or "").lower()
        mimetype = (
            (getattr(stream_info, "mimetype", None) or "")
            .split(";", 1)[0]
            .strip()
            .lower()
        )
        return extension in _CSV_EXTENSIONS or mimetype in _CSV_MIMETYPES

    def read(
        self,
        file_stream: BinaryIO,
        stream_info: Any,
        **kwargs: Any,
    ) -> DocumentIR:
        encoding = kwargs.pop("encoding", None)
        delimiter = kwargs.pop("delimiter", None)
        if encoding is None:
            encoding = getattr(stream_info, "charset", None)
        if kwargs:
            raise TypeError(f"unexpected CSV reader options: {sorted(kwargs)}")
        return read_csv_ir(
            file_stream,
            filename=getattr(stream_info, "filename", None),
            mimetype=getattr(stream_info, "mimetype", None),
            encoding=encoding,
            delimiter=delimiter,
        )
