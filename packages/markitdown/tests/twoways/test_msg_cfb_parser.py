from __future__ import annotations

import pytest

from markitdown.twoways.formats.msg import MsgFormatError, MsgLimits, parse_cfb

from ._msg_fixtures import (
    PROPERTIES_STREAM,
    SUBJECT_STREAM,
    make_cfb,
    make_truncated_cfb,
)


@pytest.mark.parametrize("major_version", (3, 4))
def test_parses_v3_and_v4_cfb_with_minifat_streams(major_version: int) -> None:
    fixture = make_cfb(major_version=major_version)

    parsed = parse_cfb(fixture.data)

    assert parsed.header.major_version == major_version
    assert parsed.header.sector_size == fixture.sector_size
    assert parsed.header.mini_sector_size == 64
    assert parsed.header.mini_stream_cutoff == 4096

    properties = parsed.stream(PROPERTIES_STREAM, parent_id=0)
    subject = parsed.stream(SUBJECT_STREAM, parent_id=0)

    assert properties.logical_bytes == fixture.properties_bytes
    assert subject.logical_bytes == fixture.subject_bytes
    assert properties.chain_kind == "mini"
    assert subject.chain_kind == "mini"
    assert sum(r.length for r in subject.physical_ranges) == len(
        fixture.subject_bytes
    )
    assert subject.physical_ranges[0].start == fixture.subject_physical_start


def test_directory_entries_and_top_level_stream_identity_are_stable() -> None:
    fixture = make_cfb()

    parsed = parse_cfb(fixture.data)

    root = parsed.directory_entries[0]
    properties = parsed.stream(PROPERTIES_STREAM, parent_id=0)
    subject = parsed.stream(SUBJECT_STREAM, parent_id=0)

    assert root.name == "Root Entry"
    assert root.object_type == 5
    assert properties.directory_id == 1
    assert subject.directory_id == 2
    assert properties.parent_id == 0
    assert subject.parent_id == 0
    assert len(properties.directory_entry_sha256) == 64
    assert len(subject.directory_entry_sha256) == 64
    assert len(parsed.topology_sha256) == 64


def test_duplicate_top_level_subject_stream_is_ambiguous() -> None:
    parsed = parse_cfb(make_cfb(duplicate_subject_name=True).data)

    with pytest.raises(MsgFormatError, match="ambiguous|duplicate"):
        parsed.stream(SUBJECT_STREAM, parent_id=0)


def test_fat_cycle_fails_closed() -> None:
    with pytest.raises(MsgFormatError, match="FAT.*cycle|cycle.*FAT"):
        parse_cfb(make_cfb(fat_cycle=True).data)


def test_minifat_cycle_fails_closed() -> None:
    with pytest.raises(MsgFormatError, match="MiniFAT.*cycle|cycle.*MiniFAT"):
        parse_cfb(make_cfb(mini_cycle=True).data)


def test_directory_sector_out_of_bounds_fails_closed() -> None:
    with pytest.raises(MsgFormatError, match="directory.*bounds|sector.*bounds"):
        parse_cfb(make_cfb(directory_sector_out_of_bounds=True).data)


def test_overlapping_stream_physical_ranges_fail_closed() -> None:
    with pytest.raises(MsgFormatError, match="overlap|alias"):
        parse_cfb(make_cfb(overlap_streams=True).data)


def test_truncated_sector_fails_closed() -> None:
    with pytest.raises(MsgFormatError, match="truncated|sector|size"):
        parse_cfb(make_truncated_cfb())


def test_invalid_signature_fails_closed() -> None:
    source = bytearray(make_cfb().data)
    source[0] ^= 0xFF

    with pytest.raises(MsgFormatError, match="signature"):
        parse_cfb(bytes(source))


def test_invalid_v3_sector_shift_fails_closed() -> None:
    source = bytearray(make_cfb(major_version=3).data)
    source[30:32] = (12).to_bytes(2, "little")

    with pytest.raises(MsgFormatError, match="sector shift|version"):
        parse_cfb(bytes(source))


def test_source_limit_fails_closed() -> None:
    source = make_cfb().data

    with pytest.raises(MsgFormatError, match="source.*limit|resource"):
        parse_cfb(
            source,
            limits=MsgLimits(max_source_bytes=len(source) - 1),
        )


def test_directory_entry_limit_fails_closed() -> None:
    source = make_cfb().data

    with pytest.raises(MsgFormatError, match="directory.*limit|resource"):
        parse_cfb(
            source,
            limits=MsgLimits(max_directory_entries=2),
        )
