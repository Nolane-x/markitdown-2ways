from __future__ import annotations

from dataclasses import dataclass, field

from ...capabilities import CapabilityDecision
from ...ooxml import OOXMLPackageLimits


SPREADSHEETML_TRANSITIONAL_NS = (
    "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
)
SPREADSHEETML_STRICT_NS = "http://purl.oclc.org/ooxml/spreadsheetml/main"
SPREADSHEETML_NAMESPACES = frozenset(
    {SPREADSHEETML_TRANSITIONAL_NS, SPREADSHEETML_STRICT_NS}
)

OFFICE_REL_TRANSITIONAL_NS = (
    "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
)
OFFICE_REL_STRICT_NS = "http://purl.oclc.org/ooxml/officeDocument/relationships"

PACKAGE_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
CONTENT_TYPES_NS = "http://schemas.openxmlformats.org/package/2006/content-types"

WORKBOOK_CONTENT_TYPE = (
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"
)
WORKSHEET_CONTENT_TYPE = (
    "application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"
)
SHARED_STRINGS_CONTENT_TYPE = (
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sharedStrings+xml"
)
STYLES_CONTENT_TYPE = (
    "application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"
)


@dataclass(frozen=True)
class XlsxPatchOptions:
    verify_output: bool = True
    limits: OOXMLPackageLimits = field(default_factory=OOXMLPackageLimits)


@dataclass(frozen=True)
class XlsxWorksheetPart:
    name: str
    sheet_id: int
    relationship_id: str
    part_uri: str


@dataclass(frozen=True)
class XlsxPackageParts:
    workbook_part: str
    spreadsheet_namespace: str
    worksheets: tuple[XlsxWorksheetPart, ...]
    shared_strings_part: str | None = None
    styles_part: str | None = None


@dataclass(frozen=True)
class XlsxCell:
    address: str
    row: int
    column: int
    value: object
    display_text: str
    data_type: str | None
    formula: str | None
    style_id: int | None
    merged: bool
    capability: CapabilityDecision


@dataclass(frozen=True)
class XlsxWorksheetGrid:
    rows: int
    columns: int
    cells: tuple[XlsxCell, ...]
    merged_addresses: frozenset[str] = frozenset()
