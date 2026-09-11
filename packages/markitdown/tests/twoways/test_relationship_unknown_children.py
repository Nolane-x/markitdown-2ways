from __future__ import annotations

from io import BytesIO
from zipfile import ZipFile

import pytest

from markitdown.twoways._errors import OOXMLPackageError
from markitdown.twoways.formats.docx.relationships import relationships_for_part
from markitdown.twoways.ooxml import snapshot_package

_RELATIONSHIPS_NS = "http://schemas.openxmlformats.org/package/2006/relationships"


def _package(child_xml: str) -> bytes:
    rels = (
        f'<Relationships xmlns="{_RELATIONSHIPS_NS}">' f"{child_xml}" "</Relationships>"
    ).encode("utf-8")
    output = BytesIO()
    with ZipFile(output, "w") as archive:
        archive.writestr("word/_rels/document.xml.rels", rels)
    return output.getvalue()


@pytest.mark.parametrize(
    "child_xml",
    [
        "<Foo/>",
        '<x:Foo xmlns:x="urn:not-opc"/>',
    ],
)
def test_snapshot_rejects_unknown_relationship_children(child_xml: str):
    with pytest.raises(OOXMLPackageError) as exc:
        snapshot_package(_package(child_xml))

    assert exc.value.details["reason"] == "malformed_relationship_part"


def test_docx_parser_rejects_unknown_relationship_child():
    with pytest.raises(OOXMLPackageError) as exc:
        relationships_for_part(_package("<Foo/>"), "/word/document.xml")

    assert exc.value.details["reason"] == "malformed_relationship_part"
