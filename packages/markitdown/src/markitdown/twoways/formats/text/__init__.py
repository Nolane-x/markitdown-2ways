"""Native source-preserving text round-trip support."""

from .codec import decode_text_source, encode_text_source, normalize_newlines
from .model import TextRepresentation
from .reader import TextIRReader, read_text_ir
from .writer import TextPatchWriter, patch_text

__all__ = [
    "TextIRReader",
    "TextPatchWriter",
    "TextRepresentation",
    "decode_text_source",
    "encode_text_source",
    "normalize_newlines",
    "patch_text",
    "read_text_ir",
]
