"""Native source-preserving JSON round-trip support."""

from .reader import JsonIRReader, read_json_ir
from .writer import JsonPatchWriter, patch_json

__all__ = [
    "JsonIRReader",
    "JsonPatchWriter",
    "patch_json",
    "read_json_ir",
]
