"""Native source-preserving JSON round-trip support."""

from .reader import JsonIRReader, read_json_ir
from .writer import patch_json
from .writer_adapter import JsonPatchWriter

__all__ = [
    "JsonIRReader",
    "JsonPatchWriter",
    "patch_json",
    "read_json_ir",
]
