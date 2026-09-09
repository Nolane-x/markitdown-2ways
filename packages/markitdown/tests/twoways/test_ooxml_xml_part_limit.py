from io import BytesIO
from zipfile import ZipFile

import pytest

from markitdown.twoways._errors import OOXMLPackageError
from markitdown.twoways.ooxml import OOXMLPackageLimits, snapshot_package


def _zip_bytes(name: str, data: bytes) -> bytes:
    output = BytesIO()
    with ZipFile(output, "w") as archive:
        archive.writestr(name, data)
    return output.getvalue()


def _limits() -> OOXMLPackageLimits:
    return OOXMLPackageLimits(
        max_members=10,
        max_member_uncompressed_bytes=100,
        max_total_uncompressed_bytes=100,
        max_compression_ratio=200.0,
        max_xml_part_bytes=4,
    )


@pytest.mark.parametrize(
    "name",
    ["word/document.xml", "word/_rels/document.xml.rels"],
)
def test_xml_parts_have_a_dedicated_pre_read_limit(name: str):
    with pytest.raises(OOXMLPackageError) as exc:
        snapshot_package(_zip_bytes(name, b"12345"), limits=_limits())

    assert exc.value.details["reason"] == "xml_part_too_large"
    assert exc.value.details["member"] == name
    assert exc.value.details["limit"] == 4


def test_non_xml_member_is_not_subject_to_xml_part_limit():
    snapshot = snapshot_package(
        _zip_bytes("word/media/image.bin", b"12345"),
        limits=_limits(),
    )
    assert snapshot.entries[0].uncompressed_size == 5


def test_xml_part_limit_must_be_positive():
    with pytest.raises(ValueError, match="max_xml_part_bytes"):
        OOXMLPackageLimits(max_xml_part_bytes=0)


def test_legacy_positional_limit_order_is_preserved():
    limits = OOXMLPackageLimits(10, 100, 100, 2.0)
    assert limits.max_compression_ratio == 2.0
    assert limits.max_xml_part_bytes == 64 * 1024 * 1024
