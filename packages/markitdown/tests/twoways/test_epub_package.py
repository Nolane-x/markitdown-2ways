from __future__ import annotations

from io import BytesIO
import stat
from zipfile import ZIP_BZIP2, ZIP_DEFLATED, ZipFile

import pytest

from markitdown.twoways.formats.epub.limits import EpubPackageLimits
from markitdown.twoways.formats.epub.model import EpubParseError
from markitdown.twoways.formats.epub.package import snapshot_epub_package

from ._epub_fixtures import make_epub


def test_epub_snapshot_records_ordered_safe_ocf_inventory() -> None:
    source = make_epub()
    snapshot = snapshot_epub_package(source)

    assert snapshot.source_size == len(source)
    assert snapshot.source_sha256
    assert snapshot.entries[0].name == "mimetype"
    assert snapshot.entries[0].compression_method == 0
    assert snapshot.entry_by_name["META-INF/container.xml"].uncompressed_sha256
    assert tuple(entry.name for entry in snapshot.entries)[-1] == "OEBPS/cover.png"


@pytest.mark.parametrize(
    "kwargs",
    [
        {"mimetype_first": False},
        {"mimetype_compression": ZIP_DEFLATED},
        {"mimetype_extra": b"\x01\x00\x00\x00"},
        {"mimetype_payload": b"application/not-epub"},
    ],
)
def test_ocf_mimetype_contract_fails_closed(kwargs: dict[str, object]) -> None:
    with pytest.raises(EpubParseError):
        snapshot_epub_package(make_epub(**kwargs))


@pytest.mark.parametrize(
    "name",
    ["../escape", "/absolute", "C:/drive", "dir\\evil", "a/../evil"],
)
def test_unsafe_archive_member_names_fail_closed(name: str) -> None:
    with pytest.raises(EpubParseError):
        snapshot_epub_package(make_epub(extra_members={name: b"x"}))


def test_duplicate_archive_member_names_fail_closed() -> None:
    source = make_epub(extra_members={"OEBPS/style.css": b"duplicate"})
    with pytest.raises(EpubParseError):
        snapshot_epub_package(source)


def test_unsupported_archive_compression_method_fails_closed() -> None:
    source = make_epub()
    output = BytesIO()
    with ZipFile(BytesIO(source), "r") as before, ZipFile(output, "w") as after:
        after.comment = before.comment
        for info in before.infolist():
            payload = before.read(info)
            if info.filename == "OEBPS/style.css":
                info.compress_type = ZIP_BZIP2
            after.writestr(info, payload)

    with pytest.raises(EpubParseError, match="compression"):
        snapshot_epub_package(output.getvalue())


@pytest.mark.parametrize(
    "limits",
    [
        EpubPackageLimits(max_members=1),
        EpubPackageLimits(max_member_uncompressed_bytes=8),
        EpubPackageLimits(max_total_uncompressed_bytes=32),
        EpubPackageLimits(max_xml_member_bytes=32),
    ],
)
def test_package_resource_limits_fail_closed(limits: EpubPackageLimits) -> None:
    with pytest.raises(EpubParseError):
        snapshot_epub_package(make_epub(), limits=limits)


def test_symbolic_link_archive_member_fails_closed() -> None:
    source = make_epub()
    output = BytesIO()
    with ZipFile(BytesIO(source), "r") as before, ZipFile(output, "w") as after:
        after.comment = before.comment
        for info in before.infolist():
            payload = before.read(info)
            if info.filename == "OEBPS/style.css":
                info.create_system = 3
                info.external_attr = (stat.S_IFLNK | 0o777) << 16
            after.writestr(info, payload)

    with pytest.raises(EpubParseError, match="Symbolic-link"):
        snapshot_epub_package(output.getvalue())
