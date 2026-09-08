from __future__ import annotations

from io import BytesIO
from struct import pack, unpack_from
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

import pytest


def _zip_bytes(entries: list[tuple[str, bytes]]) -> bytes:
    out = BytesIO()
    with ZipFile(out, "w", compression=ZIP_DEFLATED) as archive:
        for name, data in entries:
            archive.writestr(name, data)
    return out.getvalue()


def _encrypted_flag_zip() -> bytes:
    data = bytearray(_zip_bytes([("ppt/presentation.xml", b"<p/>")]))
    local = data.find(b"PK\x03\x04")
    central = data.find(b"PK\x01\x02")
    assert local >= 0 and central >= 0
    local_flags = unpack_from("<H", data, local + 6)[0] | 0x1
    central_flags = unpack_from("<H", data, central + 8)[0] | 0x1
    data[local + 6 : local + 8] = pack("<H", local_flags)
    data[central + 8 : central + 10] = pack("<H", central_flags)
    return bytes(data)


def test_snapshot_preserves_order_and_uncompressed_digests():
    from markitdown.twoways.ooxml import snapshot_package

    source = _zip_bytes(
        [
            ("[Content_Types].xml", b"types"),
            ("ppt/presentation.xml", b"presentation"),
            ("ppt/slides/slide1.xml", b"slide"),
        ]
    )
    snapshot = snapshot_package(source)

    assert [entry.name for entry in snapshot.entries] == [
        "[Content_Types].xml",
        "ppt/presentation.xml",
        "ppt/slides/slide1.xml",
    ]
    assert snapshot.entries[2].uncompressed_size == 5
    assert snapshot.entries[2].uncompressed_sha256 == (
        "b8a7e24e95497806eafbe1b4a897b70ecf6e57f4bfca8c770091e1f075304006"
    )


def test_duplicate_member_names_fail_closed():
    from markitdown.twoways import OOXMLPackageError
    from markitdown.twoways.ooxml import snapshot_package

    out = BytesIO()
    with pytest.warns(UserWarning, match="Duplicate name"):
        with ZipFile(out, "w") as archive:
            archive.writestr("ppt/presentation.xml", b"one")
            archive.writestr("ppt/presentation.xml", b"two")

    with pytest.raises(OOXMLPackageError) as exc:
        snapshot_package(out.getvalue())
    assert exc.value.code == "two_way.ooxml_package"
    assert exc.value.details["reason"] == "duplicate_member"


@pytest.mark.parametrize(
    "name",
    [
        "../evil.xml",
        "ppt/../evil.xml",
        "/absolute.xml",
        "C:/absolute.xml",
        "word/./document.xml",
        "word//document.xml",
    ],
)
def test_unsafe_member_paths_fail_closed(name: str):
    from markitdown.twoways import OOXMLPackageError
    from markitdown.twoways.ooxml import snapshot_package

    with pytest.raises(OOXMLPackageError) as exc:
        snapshot_package(_zip_bytes([(name, b"x")]))
    assert exc.value.details["reason"] == "unsafe_member_path"


def test_encrypted_member_fails_closed():
    from markitdown.twoways import OOXMLPackageError
    from markitdown.twoways.ooxml import snapshot_package

    with pytest.raises(OOXMLPackageError) as exc:
        snapshot_package(_encrypted_flag_zip())
    assert exc.value.details["reason"] == "encrypted_member"


def test_member_and_total_limits_fail_before_mutation():
    from markitdown.twoways import OOXMLPackageError
    from markitdown.twoways.ooxml import OOXMLPackageLimits, snapshot_package

    source = _zip_bytes([("a.xml", b"12345"), ("b.xml", b"67890")])
    with pytest.raises(OOXMLPackageError) as exc:
        snapshot_package(
            source,
            limits=OOXMLPackageLimits(
                max_members=10,
                max_member_uncompressed_bytes=4,
                max_total_uncompressed_bytes=100,
            ),
        )
    assert exc.value.details["reason"] == "member_too_large"

    with pytest.raises(OOXMLPackageError) as exc:
        snapshot_package(
            source,
            limits=OOXMLPackageLimits(
                max_members=10,
                max_member_uncompressed_bytes=10,
                max_total_uncompressed_bytes=9,
            ),
        )
    assert exc.value.details["reason"] == "package_too_large"


def test_noop_write_is_byte_exact():
    from markitdown.twoways.ooxml import snapshot_package, write_package

    source = _zip_bytes([("a.xml", b"one"), ("b.xml", b"two")])
    snapshot = snapshot_package(source)
    output = BytesIO()

    write_package(snapshot, source, output, replacements={})
    assert output.getvalue() == source


def test_sparse_write_changes_only_replaced_member_content():
    from markitdown.twoways.ooxml import snapshot_package, write_package

    source = _zip_bytes(
        [("a.xml", b"one"), ("ppt/slides/slide1.xml", b"old"), ("b.xml", b"two")]
    )
    snapshot = snapshot_package(source)
    output = BytesIO()
    write_package(
        snapshot,
        source,
        output,
        replacements={"ppt/slides/slide1.xml": b"new"},
    )

    with ZipFile(BytesIO(source)) as before, ZipFile(BytesIO(output.getvalue())) as after:
        assert after.namelist() == before.namelist()
        assert after.read("a.xml") == before.read("a.xml")
        assert after.read("b.xml") == before.read("b.xml")
        assert after.read("ppt/slides/slide1.xml") == b"new"


def test_xml_parser_does_not_expand_external_entities():
    from markitdown.twoways.ooxml import parse_xml_part

    root = parse_xml_part(
        b'<!DOCTYPE foo [<!ENTITY xxe SYSTEM "file:///etc/passwd">]><foo>&xxe;</foo>'
    )
    assert root.tag == "foo"
    assert root.text in {None, ""}
