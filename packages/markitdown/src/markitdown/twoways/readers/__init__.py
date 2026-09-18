from .base import DocumentIRReader
from .remote import RemoteDerivedLimits, read_wikipedia_snapshot_ir

__all__ = [
    "DocumentIRReader",
    "RemoteDerivedLimits",
    "read_wikipedia_snapshot_ir",
]
