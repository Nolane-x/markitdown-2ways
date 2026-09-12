"""Native source-preserving CSV round-trip support."""

from .reader import CsvIRReader, read_csv_ir
from .writer import CsvPatchWriter, patch_csv

__all__ = [
    "CsvIRReader",
    "CsvPatchWriter",
    "patch_csv",
    "read_csv_ir",
]
