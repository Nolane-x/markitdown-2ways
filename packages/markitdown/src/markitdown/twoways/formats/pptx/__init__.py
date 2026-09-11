from __future__ import annotations

from typing import Any

from .model import PptxPatchOptions, PptxReadOptions

__all__ = [
    "PptxIRReader",
    "PptxPatchOptions",
    "PptxPatchWriter",
    "PptxReadOptions",
    "patch_pptx",
    "read_pptx_ir",
]


def read_pptx_ir(*args: Any, **kwargs: Any):
    from .reader import read_pptx_ir as implementation

    return implementation(*args, **kwargs)


def patch_pptx(*args: Any, **kwargs: Any):
    from .writer import patch_pptx as implementation

    return implementation(*args, **kwargs)


def __getattr__(name: str):
    if name == "PptxIRReader":
        from .reader import PptxIRReader

        return PptxIRReader
    if name == "PptxPatchWriter":
        from .writer import PptxPatchWriter

        return PptxPatchWriter
    raise AttributeError(name)
