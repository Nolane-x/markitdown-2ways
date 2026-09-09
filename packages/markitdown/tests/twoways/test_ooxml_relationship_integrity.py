from io import BytesIO
from zipfile import ZipFile

import pytest

from markitdown.twoways._errors import OOXMLPackageError
from markitdown.twoways.ooxml import snapshot_package


def _package_with_duplicate_relationship_id() -> bytes:
    rels = (
        b'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/'
        b'relationships">'
        b'<Relationship Id="rId1" Type="layout" '
        b'Target="../slideLayouts/slideLayout1.xml"/>'
        b'<Relationship Id="rId1" Type="layout" '
        b'Target="../slideLayouts/slideLayout1.xml"/>'
        b'</Relationships>'
    )
    output = BytesIO()
    with ZipFile(output, "w") as archive:
        archive.writestr("ppt/slides/_rels/slide1.xml.rels", rels)
    return output.getvalue()


def test_snapshot_rejects_duplicate_opc_relationship_ids():
    with pytest.raises(OOXMLPackageError) as exc:
        snapshot_package(_package_with_duplicate_relationship_id())
    assert exc.value.details["reason"] == "duplicate_relationship_id"
    assert exc.value.details["relationship_id"] == "rId1"


def test_relationship_ids_are_scoped_to_each_relationship_part():
    rels = (
        b'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/'
        b'relationships">'
        b'<Relationship Id="rId1" Type="layout" Target="target.xml"/>'
        b'</Relationships>'
    )
    output = BytesIO()
    with ZipFile(output, "w") as archive:
        archive.writestr("ppt/_rels/presentation.xml.rels", rels)
        archive.writestr("ppt/slides/_rels/slide1.xml.rels", rels)

    snapshot = snapshot_package(output.getvalue())
    assert len(snapshot.entries) == 2


@pytest.mark.parametrize("missing_attribute", ["Id", "Type", "Target"])
def test_snapshot_rejects_missing_required_relationship_attributes(
    missing_attribute: str,
):
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
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/'
        'relationships">'
        f"<Relationship {rendered}/>"
        "</Relationships>"
    ).encode("utf-8")
    output = BytesIO()
    with ZipFile(output, "w") as archive:
        archive.writestr("word/_rels/document.xml.rels", rels)

    with pytest.raises(OOXMLPackageError) as exc:
        snapshot_package(output.getvalue())

    assert exc.value.details["reason"] == "malformed_relationship"
    assert exc.value.details["attribute"] == missing_attribute


@pytest.mark.parametrize(
    "rels",
    [
        (
            b'<Relationships xmlns="urn:not-opc">'
            b'<Relationship Id="rId1" Type="image" Target="media/image1.png"/>'
            b'</Relationships>'
        ),
        (
            b'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/'
            b'relationships" xmlns:x="urn:not-opc">'
            b'<x:Relationship Id="rId1" Type="image" Target="media/image1.png"/>'
            b'</Relationships>'
        ),
    ],
)
def test_snapshot_rejects_wrong_relationship_namespace(rels: bytes):
    output = BytesIO()
    with ZipFile(output, "w") as archive:
        archive.writestr("word/_rels/document.xml.rels", rels)

    with pytest.raises(OOXMLPackageError) as exc:
        snapshot_package(output.getvalue())

    assert exc.value.details["reason"] == "malformed_relationship_part"
