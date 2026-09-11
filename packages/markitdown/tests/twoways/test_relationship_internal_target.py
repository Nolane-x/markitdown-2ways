from __future__ import annotations

from io import BytesIO
from zipfile import ZipFile

import pytest

from markitdown.twoways._errors import OOXMLPackageError
from markitdown.twoways.formats.docx.relationships import relationships_for_part
from markitdown.twoways.ooxml import snapshot_package


def _package(target_mode: str, target: str) -> bytes:
    rels = (
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/'
        'relationships">'
        f'<Relationship Id="rId1" Type="hyperlink" Target="{target}" '
        f'TargetMode="{target_mode}"/>'
        "</Relationships>"
    ).encode("utf-8")
    output = BytesIO()
    with ZipFile(output, "w") as archive:
        archive.writestr("word/_rels/document.xml.rels", rels)
    return output.getvalue()


def test_snapshot_rejects_absolute_uri_for_internal_relationship():
    with pytest.raises(OOXMLPackageError) as exc:
        snapshot_package(_package("Internal", "mailto:test@example.com"))
    assert exc.value.details["reason"] == "malformed_relationship"
    assert exc.value.details["attribute"] == "Target"


def test_docx_parser_rejects_absolute_uri_for_internal_relationship():
    with pytest.raises(ValueError, match="relative"):
        relationships_for_part(
            _package("Internal", "mailto:test@example.com"),
            "/word/document.xml",
        )


def test_external_absolute_uri_remains_allowed():
    source = _package("External", "mailto:test@example.com")
    snapshot = snapshot_package(source)
    assert len(snapshot.entries) == 1
    relationships = relationships_for_part(source, "/word/document.xml")
    assert relationships["rId1"].external is True
    assert relationships["rId1"].resolved_target is None
