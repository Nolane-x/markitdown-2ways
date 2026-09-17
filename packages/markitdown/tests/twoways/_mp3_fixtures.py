from __future__ import annotations

import struct
from collections.abc import Iterable

_MPEG1_L3_KBPS = (0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320, 0)
_MPEG2_L3_KBPS = (0, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160, 0)
_SAMPLE_RATES = {
    0b11: (44100, 48000, 32000),
    0b10: (22050, 24000, 16000),
    0b00: (11025, 12000, 8000),
}


def _encode_field(value: str, width: int) -> bytes:
    encoded = value.encode("iso-8859-1")
    if len(encoded) > width:
        raise ValueError("fixture field is too wide")
    return encoded + (b"\x00" * (width - len(encoded)))


def mpeg_l3_header(
    *,
    version_bits: int = 0b11,
    layer_bits: int = 0b01,
    bitrate_index: int = 9,
    sample_rate_index: int = 0,
    padding: int = 0,
) -> bytes:
    value = 0x7FF << 21
    value |= (version_bits & 0b11) << 19
    value |= (layer_bits & 0b11) << 17
    value |= 1 << 16  # no CRC
    value |= (bitrate_index & 0xF) << 12
    value |= (sample_rate_index & 0b11) << 10
    value |= (padding & 1) << 9
    return struct.pack(">I", value)


def mpeg_l3_frame(
    *,
    version_bits: int = 0b11,
    bitrate_index: int = 9,
    sample_rate_index: int = 0,
    padding: int = 0,
    fill: int = 0x55,
) -> bytes:
    rates = _SAMPLE_RATES[version_bits]
    sample_rate = rates[sample_rate_index]
    kbps_table = _MPEG1_L3_KBPS if version_bits == 0b11 else _MPEG2_L3_KBPS
    bitrate = kbps_table[bitrate_index] * 1000
    coefficient = 144 if version_bits == 0b11 else 72
    frame_length = (coefficient * bitrate) // sample_rate + padding
    header = mpeg_l3_header(
        version_bits=version_bits,
        bitrate_index=bitrate_index,
        sample_rate_index=sample_rate_index,
        padding=padding,
    )
    return header + bytes((fill,)) * (frame_length - 4)


def id3v1_tag(
    *,
    title: str = "Alpha",
    artist: str = "Nolane",
    album: str = "Lab",
    year: str = "2026",
    comment: str = "Comment",
    genre: int = 13,
    track: int | None = None,
    title_slot: bytes | None = None,
    artist_slot: bytes | None = None,
    album_slot: bytes | None = None,
) -> bytes:
    if not 0 <= genre <= 255:
        raise ValueError("genre must fit in one byte")
    title_raw = title_slot if title_slot is not None else _encode_field(title, 30)
    artist_raw = artist_slot if artist_slot is not None else _encode_field(artist, 30)
    album_raw = album_slot if album_slot is not None else _encode_field(album, 30)
    if any(len(slot) != 30 for slot in (title_raw, artist_raw, album_raw)):
        raise ValueError("ID3v1 fixture slots must be exactly 30 bytes")
    year_raw = _encode_field(year, 4)
    if track is None:
        comment_raw = _encode_field(comment, 30)
    else:
        if not 1 <= track <= 255:
            raise ValueError("track must be 1..255")
        comment_raw = _encode_field(comment, 28) + b"\x00" + bytes((track,))
    return (
        b"TAG"
        + title_raw
        + artist_raw
        + album_raw
        + year_raw
        + comment_raw
        + bytes((genre,))
    )


def leading_id3v2() -> bytes:
    return b"ID3\x04\x00\x00\x00\x00\x00\x00"


def apev2_tag() -> bytes:
    return (
        b"APETAGEX"
        + struct.pack("<I", 2000)
        + struct.pack("<I", 32)
        + struct.pack("<I", 0)
        + struct.pack("<I", 0)
        + (b"\x00" * 8)
    )


def lyrics3v1_tag() -> bytes:
    return b"LYRICSBEGINfixture lyricsLYRICSEND"


def lyrics3v2_tag() -> bytes:
    body = b"LYRICSBEGIN" + b"ETT00005Alpha"
    return body + f"{len(body):06d}".encode("ascii") + b"LYRICS200"


def make_mp3(
    *,
    title: str = "Alpha",
    artist: str = "Nolane",
    album: str = "Lab",
    frames: Iterable[bytes] | None = None,
    leading: bytes = b"",
    terminal_metadata: bytes = b"",
    track: int | None = None,
    title_slot: bytes | None = None,
    artist_slot: bytes | None = None,
    album_slot: bytes | None = None,
) -> bytes:
    audio_frames = tuple(frames) if frames is not None else (
        mpeg_l3_frame(fill=0x11),
        mpeg_l3_frame(fill=0x22),
    )
    return (
        leading
        + b"".join(audio_frames)
        + terminal_metadata
        + id3v1_tag(
            title=title,
            artist=artist,
            album=album,
            track=track,
            title_slot=title_slot,
            artist_slot=artist_slot,
            album_slot=album_slot,
        )
    )
