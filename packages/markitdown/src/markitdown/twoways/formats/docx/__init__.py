from __future__ import annotations

from typing import Any

from .model import DocxPatchOptions, DocxReadOptions

__all__ = [
    "DocxIRReader",
    "DocxPatchOptions",
    "DocxPatchWriter",
    "DocxReadOptions",
    "patch_docx",
    "read_docx_ir",
]


def read_docx_ir(*args: Any, **kwargs: Any):
    from .reader import read_docx_ir as implementation

    return implementation(*args, **kwargs)


def patch_docx(*args: Any, **kwargs: Any):
    from .writer import patch_docx as implementation

    return implementation(*args, **kwargs)


def __getattr__(name: str):
    if name == "DocxIRReader":
        from .reader import DocxIRReader

        return DocxIRReader
    if name == "DocxPatchWriter":
        from .writer import DocxPatchWriter

        return DocxPatchWriter
    raise AttributeError(name)
