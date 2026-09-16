"""Source-preserving EPUB two-way support."""

from .limits import EpubPackageLimits
from .model import EpubParseError
from .parser import parse_epub_source
from .reader import EpubIRReader, read_epub_ir
from .writer import patch_epub
from .writer_adapter import EpubPatchWriter

__all__ = [
    "EpubIRReader",
    "EpubPackageLimits",
    "EpubParseError",
    "EpubPatchWriter",
    "parse_epub_source",
    "patch_epub",
    "read_epub_ir",
]
