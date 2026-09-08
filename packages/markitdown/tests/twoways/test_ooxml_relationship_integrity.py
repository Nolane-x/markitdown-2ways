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
