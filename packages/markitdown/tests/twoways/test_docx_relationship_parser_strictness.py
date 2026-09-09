from __future__ import annotations

from io import BytesIO
from zipfile import ZipFile

import pytest

from markitdown.twoways._errors import OOXMLPackageError
from markitdown.twoways.formats.docx.relationships import relationships_for_part

_RELATIONSHIPS_NS = "http://schemas.openxmlformats.org/package/2006/relationships"


def _package(relationships_xml: bytes) -> bytes:
    output = BytesIO()
    with ZipFile(output, "w") as archive:
        archive.writestr("word/_rels/document.xml.rels", relationships_xml)
    return output.getvalue()


def test_docx_parser_rejects_wrong_relationship_root_namespace():
    source = _package(b'<Relationships xmlns="urn:not-opc"/>')

    with pytest.raises(OOXMLPackageError) as exc:
        relationships_for_part(source, "/word/document.xml")

    assert exc.value.details["reason"] == "malformed_relationship_part"


@pytest.mark.parametrize("missing_attribute", ["Id", "Type", "Target"])
def test_docx_parser_rejects_missing_required_attributes(missing_attribute: str):
    attributes = {
        "Id": "rId1",
        "Type": "image",
        "Target": "media/image1.png",
    }
    del attributes[missing_attribute]
    rendered = " ".join(
        f'{name}="{value}"' for name, value in attributes.items()
    )
    rels = (
        f'<Relationships xmlns="{_RELATIONSHIPS_NS}">'
        f"<Relationship {rendered}/>"
        "</Relationships>"
    ).encode("utf-8")

    with pytest.raises(OOXMLPackageError) as exc:
        relationships_for_part(_package(rels), "/word/document.xml")

    assert exc.value.details["reason"] == "malformed_relationship"
    assert exc.value.details["attribute"] == missing_attribute


def test_docx_parser_normalizes_malformed_relationship_xml():
    rels = (
        f'<Relationships xmlns="{_RELATIONSHIPS_NS}">'
        '<Relationship Id="rId1"></Relationships>'
    ).encode("utf-8")

    with pytest.raises(OOXMLPackageError) as exc:
        relationships_for_part(_package(rels), "/word/document.xml")

    assert exc.value.details["reason"] == "malformed_relationship_part"


def test_docx_parser_allows_empty_valid_relationship_part():
    rels = f'<Relationships xmlns="{_RELATIONSHIPS_NS}"/>'.encode("utf-8")

    assert relationships_for_part(_package(rels), "/word/document.xml") == {}
