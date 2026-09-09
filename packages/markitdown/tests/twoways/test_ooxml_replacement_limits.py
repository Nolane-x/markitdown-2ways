from __future__ import annotations

from io import BytesIO
from zipfile import ZipFile

import pytest

from markitdown.twoways._errors import OOXMLPackageError
from markitdown.twoways.ooxml import OOXMLPackageLimits, snapshot_package, write_package


def _source_bytes() -> bytes:
    output = BytesIO()
    with ZipFile(output, "w") as archive:
        archive.writestr("word/document.xml", b"1234")
        archive.writestr("word/media/image.bin", b"ABCD")
    return output.getvalue()


def _limits(
    *,
    member: int = 10,
    total: int = 20,
    xml: int = 4,
) -> OOXMLPackageLimits:
    return OOXMLPackageLimits(
        max_members=10,
        max_member_uncompressed_bytes=member,
        max_total_uncompressed_bytes=total,
        max_compression_ratio=200.0,
        max_xml_part_bytes=xml,
    )


def test_write_package_rejects_oversized_xml_replacement_before_output():
    source = _source_bytes()
    limits = _limits()
    snapshot = snapshot_package(source, limits=limits)
    output = BytesIO()

    with pytest.raises(OOXMLPackageError) as exc:
        write_package(
            snapshot,
            source,
            output,
            replacements={"word/document.xml": b"12345"},
            limits=limits,
        )

    assert exc.value.details["reason"] == "xml_part_too_large"
    assert output.getvalue() == b""


def test_write_package_allows_non_xml_replacement_above_xml_limit():
    source = _source_bytes()
    limits = _limits()
    snapshot = snapshot_package(source, limits=limits)
    output = BytesIO()

    write_package(
        snapshot,
        source,
        output,
        replacements={"word/media/image.bin": b"ABCDE"},
        limits=limits,
    )

    with ZipFile(BytesIO(output.getvalue()), "r") as archive:
        assert archive.read("word/media/image.bin") == b"ABCDE"


def test_write_package_rejects_replacement_above_member_limit():
    source = _source_bytes()
    limits = _limits(member=4, xml=4)
    snapshot = snapshot_package(source, limits=limits)
    output = BytesIO()

    with pytest.raises(OOXMLPackageError) as exc:
        write_package(
            snapshot,
            source,
            output,
            replacements={"word/media/image.bin": b"ABCDE"},
            limits=limits,
        )

    assert exc.value.details["reason"] == "member_too_large"
    assert output.getvalue() == b""


def test_write_package_rejects_replacement_above_total_output_limit():
    source = _source_bytes()
    limits = _limits(total=8, xml=10)
    snapshot = snapshot_package(source, limits=limits)
    output = BytesIO()

    with pytest.raises(OOXMLPackageError) as exc:
        write_package(
            snapshot,
            source,
            output,
            replacements={"word/document.xml": b"12345"},
            limits=limits,
        )

    assert exc.value.details["reason"] == "package_too_large"
    assert output.getvalue() == b""
