from __future__ import annotations

from io import BytesIO
from zipfile import ZipFile

from markitdown.twoways.formats.docx.relationships import relationships_for_part
from markitdown.twoways.ooxml import snapshot_package


_RELATIONSHIPS_WITH_COMMENT = (
    b'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/'
    b'relationships">'
    b'<!-- relationship comment -->'
    b'<Relationship Id="rId1" Type="image" Target="media/image1.png"/>'
    b'</Relationships>'
)


def _package_with_relationship_comment() -> bytes:
    output = BytesIO()
    with ZipFile(output, "w") as archive:
        archive.writestr(
            "word/_rels/document.xml.rels",
            _RELATIONSHIPS_WITH_COMMENT,
        )
    return output.getvalue()


def test_snapshot_accepts_xml_comments_in_relationship_parts():
    snapshot = snapshot_package(_package_with_relationship_comment())
    assert len(snapshot.entries) == 1


def test_docx_relationship_parser_ignores_xml_comments():
    relationships = relationships_for_part(
        _package_with_relationship_comment(),
        "/word/document.xml",
    )
    assert tuple(relationships) == ("rId1",)
