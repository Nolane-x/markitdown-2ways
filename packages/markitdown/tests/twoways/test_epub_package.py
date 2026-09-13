from __future__ import annotations

from zipfile import ZIP_DEFLATED

import pytest

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


@pytest.mark.parametrize("name", ["../escape", "/absolute", "C:/drive", "dir\\evil", "a/../evil"])
def test_unsafe_archive_member_names_fail_closed(name: str) -> None:
    with pytest.raises(EpubParseError):
        snapshot_epub_package(make_epub(extra_members={name: b"x"}))


def test_duplicate_archive_member_names_fail_closed() -> None:
    source = make_epub(extra_members={"OEBPS/style.css": b"duplicate"})
    with pytest.raises(EpubParseError):
        snapshot_epub_package(source)
