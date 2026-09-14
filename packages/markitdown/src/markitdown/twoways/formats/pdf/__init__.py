"""Native-safe PDF two-way support."""

from .limits import PdfNativeLimits
from .model import PdfParseError
from .parser import parse_pdf_source
from .reader import PdfIRReader, read_pdf_ir
from .writer import patch_pdf
from .writer_adapter import PdfPatchWriter

__all__ = [
    "PdfIRReader",
    "PdfNativeLimits",
    "PdfParseError",
    "PdfPatchWriter",
    "parse_pdf_source",
    "patch_pdf",
    "read_pdf_ir",
]
