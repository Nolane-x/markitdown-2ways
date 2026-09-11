from __future__ import annotations

from typing import Any

from .cells import a1_to_indices, indices_to_a1
from .model import XlsxPatchOptions
from .package import discover_xlsx_parts
from .patch import patch_worksheet_cells

__all__ = [
    "XlsxIRReader",
    "XlsxPatchOptions",
    "XlsxPatchWriter",
    "a1_to_indices",
    "discover_xlsx_parts",
    "indices_to_a1",
    "patch_worksheet_cells",
    "patch_xlsx",
    "read_xlsx_ir",
]


def read_xlsx_ir(*args: Any, **kwargs: Any):
    from .reader import read_xlsx_ir as implementation

    return implementation(*args, **kwargs)


def patch_xlsx(*args: Any, **kwargs: Any):
    from .writer import patch_xlsx as implementation

    return implementation(*args, **kwargs)


def __getattr__(name: str):
    if name == "XlsxIRReader":
        from .reader import XlsxIRReader

        return XlsxIRReader
    if name == "XlsxPatchWriter":
        from .writer import XlsxPatchWriter

        return XlsxPatchWriter
    raise AttributeError(name)
