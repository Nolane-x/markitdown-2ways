"""Native source-preserving XML round-trip support."""

from .reader import XmlIRReader, read_xml_ir
from .writer import patch_xml
from .writer_adapter import XmlPatchWriter

__all__ = [
    "XmlIRReader",
    "XmlPatchWriter",
    "patch_xml",
    "read_xml_ir",
]
