"""HTML two-way format support."""

from .reader import HtmlIRReader, read_html_ir
from .writer import patch_html
from .writer_adapter import HtmlPatchWriter

__all__ = [
    "HtmlIRReader",
    "HtmlPatchWriter",
    "patch_html",
    "read_html_ir",
]
