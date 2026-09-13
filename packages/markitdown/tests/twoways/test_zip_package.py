from __future__ import annotations

from hashlib import sha256
from io import BytesIO
from zipfile import ZIP_BZIP2, ZipFile

import pytest

from markitdown.twoways.formats.zip.limits import ZipRecursiveLimits
from markitdown.twoways.formats.zip.model import ZipParseError
from markitdown.twoways.formats.zip.package import (
    build_zip_candidate,
    read_zip_member,
    snapshot_zip_package,
)

from ._zip_fixtures import make_zip, make_zip_entries, mark_single_member_encrypted


def _assert_reason(exc: pytest.ExceptionInfo[ZipParseError], prefix: str) -> None:
    assert exc.value.reason.startswith(prefix)


def test_zip_snapshot_records_ordered_inventory_and_member_digests() -> None:
    source = make_zip(archive_comment=b"h8")
    snapshot = snapshot_zip_package(source)

    assert snapshot.source_sha256 == sha256(source).hexdigest()
    assert snapshot.source_size == len(source)
    assert snapshot.archive_comment == b"h8"
    assert tuple(entry.name for entry in snapshot.entries) == (
        "docs/readme.txt",
        "data/config.json",
    )
    assert (
        snapshot.entry_by_name["docs/readme.txt"].uncompressed_sha256
        == sha256(b"hello\n").hexdigest()
    )
    assert read_zip_member(source, "data/config.json") == b'{"name":"Ada"}\n'


@pytest.mark.parametrize(
    "name",
    ["../escape", "/absolute", "C:/drive", "dir\\evil", "a/../evil"],
)
def test_zip_unsafe_member_paths_fail_closed(name: str) -> None:
    with pytest.raises(ZipParseError) as exc:
        snapshot_zip_package(make_zip(members={name: b"x"}))
    _assert_reason(exc, "zip.package.unsafe_member_path")


def test_duplicate_member_names_fail_closed() -> None:
    with pytest.warns(UserWarning, match="Duplicate name"):
        source = make_zip_entries((("dup.txt", b"a"), ("dup.txt", b"b")))
    with pytest.raises(ZipParseError) as exc:
        snapshot_zip_package(source)
    _assert_reason(exc, "zip.package.duplicate_member")


def test_symlink_member_fails_closed() -> None:
    source = make_zip(members={"link": b"target"}, symlink_name="link")
    with pytest.raises(ZipParseError) as exc:
        snapshot_zip_package(source)
    _assert_reason(exc, "zip.package.symlink_member")


def test_encrypted_member_fails_closed() -> None:
    source = mark_single_member_encrypted(make_zip(members={"secret.txt": b"secret"}))
    with pytest.raises(ZipParseError) as exc:
        snapshot_zip_package(source)
    _assert_reason(exc, "zip.package.encrypted_member")


def test_bzip2_member_fails_closed() -> None:
    source = make_zip(
        members={"docs/readme.txt": b"hello"},
        per_member_compression={"docs/readme.txt": ZIP_BZIP2},
    )
    with pytest.raises(ZipParseError, match="compression") as exc:
        snapshot_zip_package(source)
    _assert_reason(exc, "zip.package.unsupported_compression")


def test_member_count_limit_fails_closed() -> None:
    with pytest.raises(ZipParseError) as exc:
        snapshot_zip_package(
            make_zip(),
            limits=ZipRecursiveLimits(max_members_per_archive=1),
        )
    _assert_reason(exc, "zip.package.too_many_members")


def test_member_size_limit_fails_closed() -> None:
    with pytest.raises(ZipParseError) as exc:
        snapshot_zip_package(
            make_zip(members={"large.bin": b"12345"}),
            limits=ZipRecursiveLimits(max_member_uncompressed_bytes=4),
        )
    _assert_reason(exc, "zip.package.member_too_large")


def test_archive_total_size_limit_fails_closed() -> None:
    with pytest.raises(ZipParseError) as exc:
        snapshot_zip_package(
            make_zip(members={"a.bin": b"1234", "b.bin": b"5678"}),
            limits=ZipRecursiveLimits(max_archive_uncompressed_bytes=7),
        )
    _assert_reason(exc, "zip.package.archive_too_large")


def test_compression_ratio_limit_fails_closed() -> None:
    with pytest.raises(ZipParseError) as exc:
        snapshot_zip_package(
            make_zip(members={"bomb.txt": b"A" * 16_384}),
            limits=ZipRecursiveLimits(max_compression_ratio=2.0),
        )
    _assert_reason(exc, "zip.package.compression_ratio_too_high")


def test_malformed_zip_fails_closed() -> None:
    with pytest.raises(ZipParseError) as exc:
        snapshot_zip_package(b"not a ZIP archive")
    _assert_reason(exc, "zip.package.malformed_zip")


def test_zip_candidate_zero_replacements_returns_exact_source_bytes() -> None:
    source = make_zip()
    snapshot = snapshot_zip_package(source)

    assert build_zip_candidate(snapshot, source, replacements={}) == source


def test_zip_candidate_replaces_only_known_regular_member() -> None:
    source = make_zip()
    snapshot = snapshot_zip_package(source)
    candidate = build_zip_candidate(
        snapshot,
        source,
        replacements={"docs/readme.txt": b"updated\n"},
    )

    with ZipFile(BytesIO(candidate), "r") as archive:
        assert archive.read("docs/readme.txt") == b"updated\n"
        assert archive.read("data/config.json") == b'{"name":"Ada"}\n'
        assert archive.namelist() == ["docs/readme.txt", "data/config.json"]


def test_zip_candidate_rejects_unknown_member() -> None:
    source = make_zip()
    snapshot = snapshot_zip_package(source)

    with pytest.raises(ZipParseError) as exc:
        build_zip_candidate(
            snapshot,
            source,
            replacements={"missing.txt": b"new"},
        )
    _assert_reason(exc, "zip.package.unknown_replacement_member")


def test_zip_candidate_rejects_directory_replacement() -> None:
    source = make_zip_entries((("folder/", b""), ("folder/file.txt", b"x")))
    snapshot = snapshot_zip_package(source)

    with pytest.raises(ZipParseError) as exc:
        build_zip_candidate(
            snapshot,
            source,
            replacements={"folder/": b"not-a-directory"},
        )
    _assert_reason(exc, "zip.package.directory_replacement")


def test_zip_candidate_rejects_snapshot_source_mismatch() -> None:
    source = make_zip()
    snapshot = snapshot_zip_package(source)
    other = make_zip(members={"other.txt": b"other"})

    with pytest.raises(ZipParseError) as exc:
        build_zip_candidate(snapshot, other, replacements={"docs/readme.txt": b"x"})
    _assert_reason(exc, "zip.package.snapshot_source_mismatch")