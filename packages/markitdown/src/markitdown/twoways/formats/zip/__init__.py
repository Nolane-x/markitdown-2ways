"""Source-preserving recursive ZIP two-way support."""

from .limits import ZipRecursiveLimits
from .model import ZipParseError
from .parser import parse_zip_source
from .reader import ZipIRReader, read_zip_ir
from .writer import patch_zip
from .writer_adapter import ZipPatchWriter

__all__ = [
    "ZipIRReader",
    "ZipParseError",
    "ZipPatchWriter",
    "ZipRecursiveLimits",
    "parse_zip_source",
    "patch_zip",
    "read_zip_ir",
]
