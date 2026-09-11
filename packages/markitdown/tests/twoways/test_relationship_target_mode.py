from __future__ import annotations

from io import BytesIO
from zipfile import ZipFile

import pytest

from markitdown.twoways._errors import OOXMLPackageError
from markitdown.twoways.formats.docx.relationships import relationships_for_part
from markitdown.twoways.ooxml import snapshot_package


_INVALID_TARGET_MODE_RELS = (
    b'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/'
    b'relationships">'
    b'<Relationship Id="rId1" Type="image" Target="media/image1.png" '
    b'TargetMode="Bogus"/>'
    b"</Relationships>"
)


def _package_with_invalid_target_mode() -> bytes:
    output = BytesIO()
    with ZipFile(output, "w") as archive:
        archive.writestr(
            "word/_rels/document.xml.rels",
            _INVALID_TARGET_MODE_RELS,
        )
    return output.getvalue()


def test_snapshot_rejects_invalid_relationship_target_mode():
    with pytest.raises(OOXMLPackageError) as exc:
        snapshot_package(_package_with_invalid_target_mode())
    assert exc.value.details["reason"] == "malformed_relationship"
    assert exc.value.details["attribute"] == "TargetMode"


def test_docx_relationship_parser_rejects_invalid_target_mode():
    with pytest.raises(OOXMLPackageError) as exc:
        relationships_for_part(
            _package_with_invalid_target_mode(),
            "/word/document.xml",
        )
    assert exc.value.details["reason"] == "malformed_relationship"
    assert exc.value.details["attribute"] == "TargetMode"
