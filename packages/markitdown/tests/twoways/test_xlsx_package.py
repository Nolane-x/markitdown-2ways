from __future__ import annotations

import pytest

from markitdown.twoways._errors import OOXMLPackageError
from markitdown.twoways.formats.xlsx.package import discover_xlsx_parts

from ._xlsx_fixtures import CONTENT_TYPES, ROOT_RELS, WORKBOOK, WORKBOOK_RELS, make_xlsx


def test_discovers_authoritative_workbook_and_ordered_sheets() -> None:
    parts = discover_xlsx_parts(make_xlsx())

    assert parts.workbook_part == "/xl/workbook.xml"
    assert parts.spreadsheet_namespace == "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    assert [(sheet.name, sheet.relationship_id, sheet.part_uri) for sheet in parts.worksheets] == [
        ("Data", "rId1", "/xl/worksheets/sheet1.xml"),
        ("Other", "rId2", "/xl/worksheets/sheet2.xml"),
    ]
    assert parts.shared_strings_part == "/xl/sharedStrings.xml"


def test_rejects_multiple_office_document_authorities() -> None:
    root_rels = ROOT_RELS.replace(
        "</Relationships>",
        '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>',
    )
    with pytest.raises(OOXMLPackageError) as exc_info:
        discover_xlsx_parts(make_xlsx(replacements={"_rels/.rels": root_rels}))
    assert exc_info.value.details["reason"] == "ambiguous_workbook_part"


def test_rejects_external_worksheet_relationship() -> None:
    rels = WORKBOOK_RELS.replace(
        'Target="worksheets/sheet1.xml"',
        'Target="https://example.invalid/sheet1.xml" TargetMode="External"',
    )
    with pytest.raises(OOXMLPackageError) as exc_info:
        discover_xlsx_parts(make_xlsx(replacements={"xl/_rels/workbook.xml.rels": rels}))
    assert exc_info.value.details["reason"] == "external_worksheet_target"


def test_rejects_relationship_target_that_escapes_package_root() -> None:
    rels = WORKBOOK_RELS.replace('Target="worksheets/sheet1.xml"', 'Target="../../../escape.xml"')
    with pytest.raises((OOXMLPackageError, ValueError)):
        discover_xlsx_parts(make_xlsx(replacements={"xl/_rels/workbook.xml.rels": rels}))


def test_rejects_wrong_worksheet_content_type() -> None:
    content_types = CONTENT_TYPES.replace(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml",
        "application/xml",
        1,
    )
    with pytest.raises(OOXMLPackageError) as exc_info:
        discover_xlsx_parts(make_xlsx(replacements={"[Content_Types].xml": content_types}))
    assert exc_info.value.details["reason"] == "wrong_worksheet_content_type"


def test_rejects_mixed_supported_spreadsheetml_namespaces_in_workbook() -> None:
    workbook = WORKBOOK.replace(
        '<sheet name="Data"',
        '<sheet xmlns="http://purl.oclc.org/ooxml/spreadsheetml/main" name="Data"',
    )
    with pytest.raises(OOXMLPackageError) as exc_info:
        discover_xlsx_parts(make_xlsx(replacements={"xl/workbook.xml": workbook}))
    assert exc_info.value.details["reason"] == "mixed_spreadsheet_namespace"
