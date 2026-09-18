from __future__ import annotations

from typing import Any

from .biff import logical_slice_ranges, parse_xls
from .cfb import parse_cfb
from .limits import XlsLimits
from .model import (
    BiffRecord,
    CfbDirectoryEntry,
    CfbHeader,
    CfbPhysicalRange,
    CfbStream,
    ParsedCfb,
    ParsedXls,
    XlsFormatError,
    XlsNumberOwner,
    XlsSheet,
)

__all__ = [
    "BiffRecord",
    "CfbDirectoryEntry",
    "CfbHeader",
    "CfbPhysicalRange",
    "CfbStream",
    "ParsedCfb",
    "ParsedXls",
    "XlsFormatError",
    "XlsLimits",
    "XlsNumberOwner",
    "XlsSheet",
    "XlsIRReader",
    "XlsPatchWriter",
    "logical_slice_ranges",
    "parse_cfb",
    "parse_xls",
    "patch_xls",
    "read_xls_ir",
]


def patch_xls(*args: Any, **kwargs: Any):
    from .writer import patch_xls as implementation

    return implementation(*args, **kwargs)


def read_xls_ir(*args: Any, **kwargs: Any):
    from .reader import read_xls_ir as implementation

    return implementation(*args, **kwargs)


def __getattr__(name: str):
    if name == "XlsIRReader":
        from .reader import XlsIRReader

        return XlsIRReader
    if name == "XlsPatchWriter":
        from .writer import XlsPatchWriter

        return XlsPatchWriter
    raise AttributeError(name)

