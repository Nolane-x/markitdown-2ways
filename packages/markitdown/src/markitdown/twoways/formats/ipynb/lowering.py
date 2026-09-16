from __future__ import annotations

from collections.abc import Mapping
from io import BytesIO

from ...ir.document import DocumentIR
from ...ir.edits import EditOperation
from ..json.reader import read_json_ir
from .model import ParsedIpynbSource


def repartition_cell_source(value: str, segment_count: int) -> tuple[str, ...]:
    if not isinstance(value, str):
        raise TypeError("IPYNB cell source replacement must be a string")
    if segment_count < 1:
        raise ValueError("IPYNB source segment count must be positive")

    chunks = value.splitlines(keepends=True)
    if not chunks:
        return tuple("" for _ in range(segment_count))
    if len(chunks) < segment_count:
        return tuple(chunks + [""] * (segment_count - len(chunks)))
    if len(chunks) == segment_count:
        return tuple(chunks)
    return tuple([*chunks[: segment_count - 1], "".join(chunks[segment_count - 1 :])])


def _shadow_node_by_pointer(document: DocumentIR, pointer: str):
    matches = [
        node
        for node in document.nodes.values()
        if node.metadata.get("json.pointer") == pointer
    ]
    if len(matches) != 1:
        raise ValueError(f"shadow JSON pointer ownership is not unique: {pointer}")
    return matches[0]


def lower_ipynb_cell_sources(
    source: bytes,
    parsed: ParsedIpynbSource,
    requested: Mapping[int, str],
) -> tuple[DocumentIR, tuple[EditOperation, ...]]:
    shadow = read_json_ir(
        BytesIO(source),
        filename="notebook.ipynb",
        mimetype="application/json",
        encoding=parsed.representation.encoding,
    )
    cells = {cell.index: cell for cell in parsed.cells}
    lowered: list[EditOperation] = []

    for cell_index in sorted(requested):
        if cell_index not in cells:
            raise ValueError(f"unknown IPYNB cell index: {cell_index}")
        value = requested[cell_index]
        if not isinstance(value, str):
            raise TypeError("IPYNB requested source value must be a string")
        cell = cells[cell_index]

        if cell.source_representation == "string":
            segments = (value,)
        else:
            segments = repartition_cell_source(
                value,
                len(cell.source_segment_pointers),
            )

        for ordinal, (pointer, old_value, new_value) in enumerate(
            zip(
                cell.source_segment_pointers,
                cell.source_segment_values,
                segments,
                strict=True,
            )
        ):
            if old_value == new_value:
                continue
            node = _shadow_node_by_pointer(shadow, pointer)
            lowered.append(
                EditOperation(
                    operation_id=f"ipynb-json-{cell_index}-{ordinal}",
                    type="replace_json_scalar",
                    target_node_id=node.node_id,
                    payload={"value": new_value},
                )
            )

    return shadow, tuple(lowered)
