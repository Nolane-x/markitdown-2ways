from __future__ import annotations

from dataclasses import dataclass

from ..text.model import TextRepresentation


@dataclass(frozen=True)
class IpynbCellEvidence:
    index: int
    cell_type: str
    cell_id: str | None
    non_source_digest: str
    cell_start: int
    cell_end: int
    cell_raw_digest: str
    source_pointer: str
    source_representation: str
    source_segment_pointers: tuple[str, ...]
    source_segment_raw_digests: tuple[str, ...]
    source_segment_values: tuple[str, ...]
    logical_source: str
    source_start: int
    source_end: int
    source_raw_digest: str

    def __post_init__(self) -> None:
        if self.index < 0:
            raise ValueError("IPYNB cell index must be non-negative")
        if not isinstance(self.cell_type, str) or not self.cell_type:
            raise ValueError("IPYNB cell type must be a non-empty string")
        if self.cell_id is not None and not isinstance(self.cell_id, str):
            raise TypeError("IPYNB cell id must be a string or None")
        if not self.non_source_digest:
            raise ValueError("IPYNB cell non-source digest must be non-empty")
        if self.cell_start < 0 or self.cell_end < self.cell_start:
            raise ValueError("IPYNB cell source span is invalid")
        if not self.cell_raw_digest:
            raise ValueError("IPYNB cell raw digest must be non-empty")
        if not self.source_pointer:
            raise ValueError("IPYNB source pointer must be non-empty")
        if self.source_representation not in {"string", "string-array"}:
            raise ValueError("IPYNB source representation is unsupported")
        if self.source_start < 0 or self.source_end < self.source_start:
            raise ValueError("IPYNB source value span is invalid")
        if not self.source_raw_digest:
            raise ValueError("IPYNB source raw digest must be non-empty")

        pointers = tuple(self.source_segment_pointers)
        digests = tuple(self.source_segment_raw_digests)
        values = tuple(self.source_segment_values)
        object.__setattr__(self, "source_segment_pointers", pointers)
        object.__setattr__(self, "source_segment_raw_digests", digests)
        object.__setattr__(self, "source_segment_values", values)

        if not (len(pointers) == len(digests) == len(values)):
            raise ValueError("IPYNB source segment evidence lengths must match")
        if self.source_representation == "string" and len(values) != 1:
            raise ValueError("IPYNB string source requires exactly one segment")
        if "".join(values) != self.logical_source:
            raise ValueError("IPYNB logical source must equal joined source segments")


@dataclass(frozen=True)
class ParsedIpynbSource:
    text: str
    representation: TextRepresentation
    nbformat: int
    nbformat_minor: int
    writable_version: bool
    read_only_reason: str | None
    top_level_non_cells_digest: str
    root_start: int
    root_end: int
    root_raw_digest: str
    cells: tuple[IpynbCellEvidence, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.text, str):
            raise TypeError("IPYNB decoded source must be text")
        for name in ("nbformat", "nbformat_minor"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError(f"IPYNB {name} must be an integer")
        if self.nbformat < 0 or self.nbformat_minor < 0:
            raise ValueError("IPYNB format versions must be non-negative")
        if self.writable_version and self.read_only_reason is not None:
            raise ValueError("writable IPYNB version cannot have a read-only reason")
        if not self.writable_version and not self.read_only_reason:
            raise ValueError("read-only IPYNB version requires a reason")
        if not self.top_level_non_cells_digest:
            raise ValueError("IPYNB top-level non-cells digest must be non-empty")
        if self.root_start < 0 or self.root_end < self.root_start:
            raise ValueError("IPYNB root span is invalid")
        if not self.root_raw_digest:
            raise ValueError("IPYNB root raw digest must be non-empty")
        object.__setattr__(self, "cells", tuple(self.cells))
        if not self.writable_version and self.cells:
            raise ValueError("unsupported IPYNB versions cannot publish cell evidence")
