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
    "logical_slice_ranges",
    "parse_cfb",
    "parse_xls",
]
