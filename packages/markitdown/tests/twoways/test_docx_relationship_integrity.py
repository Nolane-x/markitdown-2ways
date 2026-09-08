from __future__ import annotations

from io import BytesIO
from zipfile import ZipFile

import pytest

from markitdown.twoways._errors import OOXMLPackageError
from markitdown.twoways.formats.docx.relationships import relationships_for_part


def _package_with_relationships(relationships_xml: bytes) -> bytes:
    output = BytesIO()
    with ZipFile(output, "w") as archive:
        archive.writestr("word/_rels/document.xml.rels", relationships_xml)
    return output.getvalue()


def test_duplicate_docx_relationship_ids_fail_closed():
    source = _package_with_relationships(
        b'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/'
        b'relationships">'
        b'<Relationship Id="rId7" Type="image" Target="media/image1.png"/>'
        b'<Relationship Id="rId7" Type="image" Target="media/image2.png"/>'
        b'</Relationships>'
    )

    with pytest.raises(OOXMLPackageError) as exc:
        relationships_for_part(source, "/word/document.xml")

    assert exc.value.details["reason"] == "duplicate_relationship_id"
    assert exc.value.details["relationship_id"] == "rId7"
