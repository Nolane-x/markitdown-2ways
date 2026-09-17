from __future__ import annotations

import pytest

from markitdown.twoways.formats.mp3 import Mp3Limits
from markitdown.twoways.formats.mp3.parser import Mp3FormatError, parse_mp3

from ._mp3_fixtures import (
    apev2_tag,
    id3v1_tag,
    leading_id3v2,
    lyrics3v1_tag,
    lyrics3v2_tag,
    make_mp3,
    mpeg_l3_frame,
    mpeg_l3_header,
)


def test_parses_terminal_id3v1_fields_and_mpeg_frame_chain() -> None:
    source = make_mp3(title="Alpha", artist="Nolane", album="Lab")

    parsed = parse_mp3(source)

    assert parsed.id3v1_start == len(source) - 128
    assert parsed.id3v1_end == len(source)
    assert parsed.owner("Title").value == "Alpha"
    assert parsed.owner("Artist").value == "Nolane"
    assert parsed.owner("Album").value == "Lab"
    assert parsed.owner("Title").slot_start == parsed.id3v1_start + 3
    assert parsed.owner("Artist").slot_start == parsed.id3v1_start + 33
    assert parsed.owner("Album").slot_start == parsed.id3v1_start + 63
    assert all(owner.slot_length == 30 for owner in parsed.owners)
    assert len(parsed.audio_frames) == 2
    assert parsed.audio_authoritative is True
    assert parsed.blockers == ()


def test_full_width_latin1_field_without_nul_is_valid() -> None:
    value = "A" * 29 + "é"
    source = make_mp3(title_slot=value.encode("iso-8859-1"))

    owner = parse_mp3(source).owner("Title")

    assert owner.value == value
    assert owner.full_width is True
    assert owner.canonical_padding is True


def test_nonzero_bytes_after_first_nul_are_inspectable_but_not_writable() -> None:
    slot = b"Alpha\x00" + b"B" + (b"\x00" * 23)
    source = make_mp3(title_slot=slot)

    parsed = parse_mp3(source)

    assert parsed.owner("Title").value == "Alpha"
    assert parsed.owner("Title").canonical_padding is False
    assert "mp3.id3v1.invalid_padding" in parsed.blockers
    assert parsed.audio_authoritative is True


def test_id3v11_track_is_detected_without_changing_supported_owner_set() -> None:
    source = make_mp3(track=7)

    parsed = parse_mp3(source)

    assert parsed.id3v1_version == "1.1"
    assert parsed.track == 7
    assert tuple(owner.field for owner in parsed.owners) == ("Title", "Artist", "Album")


@pytest.mark.parametrize("version_bits", [0b11, 0b10, 0b00])
def test_mpeg1_2_and_25_layer3_frames_are_traversed(version_bits: int) -> None:
    source = make_mp3(
        frames=(
            mpeg_l3_frame(version_bits=version_bits, fill=0x31),
            mpeg_l3_frame(version_bits=version_bits, fill=0x32),
        )
    )

    parsed = parse_mp3(source)

    assert parsed.audio_authoritative is True
    assert len(parsed.audio_frames) == 2
    assert {frame.version_bits for frame in parsed.audio_frames} == {version_bits}


def test_single_frame_is_not_sufficient_writable_audio_authority() -> None:
    source = make_mp3(frames=(mpeg_l3_frame(),))

    parsed = parse_mp3(source)

    assert parsed.audio_authoritative is False
    assert "mp3.audio_structure_unproven" in parsed.blockers


def test_free_format_bitrate_is_read_only_authority() -> None:
    bad_audio = mpeg_l3_header(bitrate_index=0) + (b"\x00" * 200)
    source = bad_audio + id3v1_tag()

    parsed = parse_mp3(source)

    assert parsed.audio_authoritative is False
    assert "mp3.audio.free_format_unsupported" in parsed.blockers


def test_reserved_layer_is_read_only_authority() -> None:
    bad_audio = mpeg_l3_header(layer_bits=0b00) + (b"\x00" * 200)
    source = bad_audio + id3v1_tag()

    parsed = parse_mp3(source)

    assert parsed.audio_authoritative is False
    assert "mp3.audio.unsupported_layer" in parsed.blockers


def test_truncated_frame_is_read_only_authority() -> None:
    frame = mpeg_l3_frame()
    source = frame[:-7] + id3v1_tag()

    parsed = parse_mp3(source)

    assert parsed.audio_authoritative is False
    assert "mp3.audio_structure_unproven" in parsed.blockers


def test_leading_id3v2_is_competing_metadata_blocker() -> None:
    source = make_mp3(leading=leading_id3v2())

    parsed = parse_mp3(source)

    assert "mp3.metadata.id3v2_read_only" in parsed.blockers
    assert parsed.audio_authoritative is False


def test_terminal_apev2_is_competing_metadata_blocker() -> None:
    source = make_mp3(terminal_metadata=apev2_tag())

    parsed = parse_mp3(source)

    assert "mp3.metadata.ape_read_only" in parsed.blockers
    assert parsed.audio_authoritative is False


@pytest.mark.parametrize("lyrics", [lyrics3v1_tag(), lyrics3v2_tag()])
def test_terminal_lyrics3_is_competing_metadata_blocker(lyrics: bytes) -> None:
    source = make_mp3(terminal_metadata=lyrics)

    parsed = parse_mp3(source)

    assert "mp3.metadata.lyrics3_read_only" in parsed.blockers
    assert parsed.audio_authoritative is False


def test_missing_terminal_id3v1_fails_closed() -> None:
    with pytest.raises(Mp3FormatError, match="ID3v1"):
        parse_mp3(mpeg_l3_frame() + mpeg_l3_frame())


def test_source_limit_fails_closed() -> None:
    source = make_mp3()

    with pytest.raises(Mp3FormatError, match="source.*limit"):
        parse_mp3(source, limits=Mp3Limits(max_source_bytes=len(source) - 1))


def test_frame_count_limit_fails_closed() -> None:
    source = make_mp3()

    with pytest.raises(Mp3FormatError, match="frame.*limit"):
        parse_mp3(source, limits=Mp3Limits(max_audio_frames=1))
