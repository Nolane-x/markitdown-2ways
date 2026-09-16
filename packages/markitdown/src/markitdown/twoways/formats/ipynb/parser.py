from __future__ import annotations

from collections.abc import Mapping
import json
from typing import Any

from ...ir.semantics import stable_digest
from ..json.lexical import JsonLexicalError, scan_json_text
from ..json.model import JsonLexicalNode
from ..text.codec import decode_text_source
from .model import IpynbCellEvidence, ParsedIpynbSource


class IpynbParseError(ValueError):
    """Raised when notebook semantics cannot be bound safely to strict JSON source."""


def _require_integer(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise IpynbParseError(f"IPYNB {field} must be an integer")
    if value < 0:
        raise IpynbParseError(f"IPYNB {field} must be non-negative")
    return value


def _require_object(value: object, field: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise IpynbParseError(f"IPYNB {field} must be a JSON object")
    return value


def _lexeme(
    lexical_by_pointer: Mapping[str, JsonLexicalNode],
    pointer: str,
    *,
    kind: str | None = None,
) -> JsonLexicalNode:
    node = lexical_by_pointer.get(pointer)
    if node is None:
        raise IpynbParseError(f"IPYNB lexical evidence is missing for {pointer or '/'}")
    if kind is not None and node.kind != kind:
        raise IpynbParseError(
            f"IPYNB lexical evidence kind mismatch at {pointer or '/'}"
        )
    return node


def parse_ipynb_source(
    source: bytes,
    *,
    encoding: str | None = None,
) -> ParsedIpynbSource:
    if not isinstance(source, bytes):
        raise TypeError("IPYNB source must be bytes")

    try:
        text, representation = decode_text_source(source, encoding=encoding)
        lexical = scan_json_text(text)
    except (UnicodeError, ValueError, JsonLexicalError) as exc:
        raise IpynbParseError(f"IPYNB strict JSON source is invalid: {exc}") from exc

    try:
        semantic = json.loads(text)
    except (json.JSONDecodeError, ValueError, TypeError) as exc:
        raise IpynbParseError(f"IPYNB JSON semantics are invalid: {exc}") from exc

    root = _require_object(semantic, "root")
    nbformat = _require_integer(root.get("nbformat"), "nbformat")
    nbformat_minor = _require_integer(root.get("nbformat_minor"), "nbformat_minor")
    cells_value = root.get("cells")
    if not isinstance(cells_value, list):
        raise IpynbParseError("IPYNB cells must be a JSON array")

    lexical_by_pointer = {node.pointer: node for node in lexical.nodes}
    root_lexeme = _lexeme(lexical_by_pointer, "", kind="object")
    top_level_non_cells_digest = stable_digest(
        {key: value for key, value in root.items() if key != "cells"}
    )

    if nbformat != 4:
        return ParsedIpynbSource(
            text=text,
            representation=representation,
            nbformat=nbformat,
            nbformat_minor=nbformat_minor,
            writable_version=False,
            read_only_reason="ipynb.nbformat.unsupported_version",
            top_level_non_cells_digest=top_level_non_cells_digest,
            root_start=root_lexeme.start,
            root_end=root_lexeme.end,
            root_raw_digest=root_lexeme.raw_digest,
            cells=(),
        )

    cells: list[IpynbCellEvidence] = []
    for index, raw_cell in enumerate(cells_value):
        cell = _require_object(raw_cell, f"cells[{index}]")
        cell_type = cell.get("cell_type")
        if not isinstance(cell_type, str) or not cell_type:
            raise IpynbParseError(f"IPYNB cells[{index}].cell_type must be a string")

        cell_id = cell.get("id")
        if cell_id is not None and not isinstance(cell_id, str):
            raise IpynbParseError(f"IPYNB cells[{index}].id must be a string")

        if "source" not in cell:
            raise IpynbParseError(f"IPYNB cells[{index}].source is required")
        source_value = cell["source"]

        cell_pointer = f"/cells/{index}"
        source_pointer = f"{cell_pointer}/source"
        cell_lexeme = _lexeme(lexical_by_pointer, cell_pointer, kind="object")
        source_lexeme = _lexeme(lexical_by_pointer, source_pointer)

        if isinstance(source_value, str):
            if source_lexeme.kind != "string":
                raise IpynbParseError(
                    f"IPYNB lexical source mismatch at {source_pointer}"
                )
            source_representation = "string"
            source_segment_pointers = (source_pointer,)
            source_segment_raw_digests = (source_lexeme.raw_digest,)
            source_segment_values = (source_value,)
        elif isinstance(source_value, list):
            if source_lexeme.kind != "array":
                raise IpynbParseError(
                    f"IPYNB lexical source mismatch at {source_pointer}"
                )
            if any(not isinstance(item, str) for item in source_value):
                raise IpynbParseError(
                    f"IPYNB cells[{index}].source array must contain strings only"
                )
            source_representation = "string-array"
            source_segment_pointers = tuple(source_lexeme.children)
            if len(source_segment_pointers) != len(source_value):
                raise IpynbParseError(
                    f"IPYNB source segment ownership mismatch at {source_pointer}"
                )
            segment_lexemes = tuple(
                _lexeme(lexical_by_pointer, pointer, kind="string")
                for pointer in source_segment_pointers
            )
            source_segment_raw_digests = tuple(
                segment.raw_digest for segment in segment_lexemes
            )
            source_segment_values = tuple(source_value)
        else:
            raise IpynbParseError(
                f"IPYNB cells[{index}].source must be a string or string array"
            )

        cells.append(
            IpynbCellEvidence(
                index=index,
                cell_type=cell_type,
                cell_id=cell_id,
                non_source_digest=stable_digest(
                    {key: value for key, value in cell.items() if key != "source"}
                ),
                cell_start=cell_lexeme.start,
                cell_end=cell_lexeme.end,
                cell_raw_digest=cell_lexeme.raw_digest,
                source_pointer=source_pointer,
                source_representation=source_representation,
                source_segment_pointers=source_segment_pointers,
                source_segment_raw_digests=source_segment_raw_digests,
                source_segment_values=source_segment_values,
                logical_source="".join(source_segment_values),
                source_start=source_lexeme.start,
                source_end=source_lexeme.end,
                source_raw_digest=source_lexeme.raw_digest,
            )
        )

    return ParsedIpynbSource(
        text=text,
        representation=representation,
        nbformat=nbformat,
        nbformat_minor=nbformat_minor,
        writable_version=True,
        read_only_reason=None,
        top_level_non_cells_digest=top_level_non_cells_digest,
        root_start=root_lexeme.start,
        root_end=root_lexeme.end,
        root_raw_digest=root_lexeme.raw_digest,
        cells=tuple(cells),
    )
