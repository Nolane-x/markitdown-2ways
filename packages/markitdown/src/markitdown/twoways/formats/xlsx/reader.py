from __future__ import annotations

from hashlib import sha256
from io import BytesIO
from typing import Any, BinaryIO
from zipfile import ZipFile

from ...capabilities import (
    CapabilityDecision,
    CapabilityState,
    encode_capabilities,
)
from ...ir.document import Canvas, DocumentIR, SourceDescriptor
from ...ir.nodes import Node, TableCell, TablePayload
from ...ir.provenance import NativeLocator, Provenance
from ...ir.serialization import validate_document
from ...ooxml import parse_xml_part
from ...ooxml.package import read_binary_stream
from ...readers.base import DocumentIRReader
from .cells import indices_to_a1, read_shared_string_table, read_worksheet_grid
from .package import discover_xlsx_parts


def _read_members(source_bytes: bytes) -> dict[str, bytes]:
    with ZipFile(BytesIO(source_bytes), "r") as archive:
        return {info.filename: archive.read(info) for info in archive.infolist()}


def read_xlsx_ir(
    file_stream: BinaryIO,
    stream_info: Any | None = None,
) -> DocumentIR:
    source_bytes = read_binary_stream(file_stream, stream_label="XLSX input")
    parts = discover_xlsx_parts(source_bytes)
    members = _read_members(source_bytes)
    source_digest = sha256(source_bytes).hexdigest()
    shared_strings: tuple[str, ...] = ()
    rich_shared_string_indexes: frozenset[int] = frozenset()
    if parts.shared_strings_part is not None:
        shared_strings, rich_shared_string_indexes = read_shared_string_table(
            parse_xml_part(members[parts.shared_strings_part.lstrip("/")])
        )

    canvases: list[Canvas] = []
    nodes: dict[str, Node] = {}
    for index, worksheet in enumerate(parts.worksheets):
        root = parse_xml_part(members[worksheet.part_uri.lstrip("/")])
        grid = read_worksheet_grid(
            root,
            shared_strings=shared_strings,
            rich_shared_string_indexes=rich_shared_string_indexes,
        )
        native_cells = {(cell.row, cell.column): cell for cell in grid.cells}
        table_cells: list[TableCell] = []
        writable_count = 0
        for row in range(grid.rows):
            for column in range(grid.columns):
                native = native_cells.get((row, column))
                address = indices_to_a1(row, column)
                if native is None:
                    table_cells.append(
                        TableCell(
                            row=row,
                            column=column,
                            text="",
                            metadata={
                                "xlsx.address": address,
                                "xlsx.typed_value": None,
                                "xlsx.present": False,
                                "xlsx.writable": False,
                                "xlsx.reason_code": "xlsx.cell.missing_native_cell",
                            },
                        )
                    )
                    continue
                writable = native.capability.state is CapabilityState.WRITABLE
                writable_count += int(writable)
                table_cells.append(
                    TableCell(
                        row=row,
                        column=column,
                        text=native.display_text,
                        metadata={
                            "xlsx.address": native.address,
                            "xlsx.typed_value": native.value,
                            "xlsx.data_type": native.data_type,
                            "xlsx.formula": native.formula,
                            "xlsx.style_id": native.style_id,
                            "xlsx.merged": native.merged,
                            "xlsx.present": True,
                            "xlsx.writable": writable,
                            "xlsx.reason_code": native.capability.reason_code,
                        },
                    )
                )

        canvas_id = f"xlsx-worksheet-{index}"
        node_id = f"xlsx-sheet-{sha256(f'{source_digest}:{index}:{worksheet.part_uri}'.encode()).hexdigest()[:24]}"
        if writable_count:
            table_capability = CapabilityDecision(
                operation="update_sheet_cells",
                state=CapabilityState.WRITABLE,
                constraints={"typed_cells": True, "writable_cells": writable_count},
            )
        else:
            table_capability = CapabilityDecision(
                operation="update_sheet_cells",
                state=CapabilityState.READ_ONLY,
                reason_code="xlsx.sheet.no_writable_cells",
            )
        node = Node(
            node_id=node_id,
            kind="table",
            semantic_role="worksheet-grid",
            order=0,
            canvas_id=canvas_id,
            provenance=(
                Provenance(
                    source_format="xlsx",
                    canvas_index=index,
                    part_uri=worksheet.part_uri,
                    extraction_method="spreadsheetml",
                ),
            ),
            native_locator=NativeLocator(
                backend="xlsx",
                part_uri=worksheet.part_uri,
                relationship_id=worksheet.relationship_id,
                name=worksheet.name,
                path="/worksheet/sheetData",
            ),
            payload=TablePayload(
                rows=grid.rows,
                columns=grid.columns,
                cells=tuple(table_cells),
            ),
            metadata={
                "xlsx.sheet_name": worksheet.name,
                "xlsx.sheet_id": worksheet.sheet_id,
                "xlsx.sheet_index": index,
                "twoways.capabilities.v1": encode_capabilities((table_capability,)),
            },
        )
        nodes[node_id] = node
        canvases.append(
            Canvas(
                canvas_id=canvas_id,
                index=index,
                kind="worksheet",
                name=worksheet.name,
                root_node_ids=(node_id,),
                native_locator=NativeLocator(
                    backend="xlsx",
                    part_uri=worksheet.part_uri,
                    relationship_id=worksheet.relationship_id,
                    name=worksheet.name,
                ),
            )
        )

    filename = (
        getattr(stream_info, "filename", None) if stream_info is not None else None
    )
    mimetype = (
        getattr(stream_info, "mimetype", None) if stream_info is not None else None
    )
    document = DocumentIR(
        document_id=f"xlsx-document-{source_digest[:24]}",
        source=SourceDescriptor(
            format="xlsx",
            filename=filename,
            mimetype=mimetype,
            sha256=source_digest,
            size_bytes=len(source_bytes),
            preserved_source_ref=f"xlsx:sha256:{source_digest}",
        ),
        canvases=tuple(canvases),
        nodes=nodes,
    )
    validate_document(document)
    return document


class XlsxIRReader(DocumentIRReader):
    def accepts(self, file_stream: BinaryIO, stream_info: Any, **kwargs: Any) -> bool:
        extension = (getattr(stream_info, "extension", None) or "").lower()
        mimetype = (getattr(stream_info, "mimetype", None) or "").lower()
        return extension == ".xlsx" or mimetype == (
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

    def read(
        self,
        file_stream: BinaryIO,
        stream_info: Any,
        **kwargs: Any,
    ) -> DocumentIR:
        if kwargs:
            raise TypeError(f"unexpected XLSX reader options: {sorted(kwargs)}")
        return read_xlsx_ir(file_stream, stream_info)
