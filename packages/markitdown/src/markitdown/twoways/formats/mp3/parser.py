from __future__ import annotations

from hashlib import sha256

from .limits import Mp3Limits
from .model import Mp3AudioFrame, Mp3Id3v1Owner, Mp3TerminalMetadata, ParsedMp3


class Mp3FormatError(ValueError):
    """Raised when a source cannot satisfy the bounded H15 MP3 contract."""


_MPEG1_L3_KBPS = (0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320, 0)
_MPEG2_L3_KBPS = (0, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160, 0)
_SAMPLE_RATES = {
    0b11: (44100, 48000, 32000),
    0b10: (22050, 24000, 16000),
    0b00: (11025, 12000, 8000),
}
_FIELD_LAYOUT = (
    ("Title", 3),
    ("Artist", 33),
    ("Album", 63),
)


def _append_unique(items: list[str], value: str) -> None:
    if value not in items:
        items.append(value)


def _parse_owner(data: bytes, *, tag_start: int, field: str, relative: int) -> Mp3Id3v1Owner:
    slot_start = tag_start + relative
    slot_end = slot_start + 30
    raw = data[slot_start:slot_end]
    nul = raw.find(b"\x00")
    if nul < 0:
        value_raw = raw
        full_width = True
        canonical_padding = True
    else:
        value_raw = raw[:nul]
        full_width = False
        canonical_padding = all(byte == 0 for byte in raw[nul:])
    return Mp3Id3v1Owner(
        field=field,
        slot_start=slot_start,
        slot_end=slot_end,
        slot_length=30,
        value=value_raw.decode("iso-8859-1"),
        slot_sha256=sha256(raw).hexdigest(),
        full_width=full_width,
        canonical_padding=canonical_padding,
    )


def _terminal_metadata(
    data: bytes,
    *,
    id3v1_start: int,
    limits: Mp3Limits,
) -> tuple[int, tuple[Mp3TerminalMetadata, ...], tuple[str, ...]]:
    cursor = id3v1_start
    records: list[Mp3TerminalMetadata] = []
    blockers: list[str] = []
    total = 0

    while cursor > 0:
        if cursor >= 32 and data[cursor - 32 : cursor - 24] == b"APETAGEX":
            footer_start = cursor - 32
            declared_size = int.from_bytes(
                data[footer_start + 12 : footer_start + 16], "little"
            )
            _append_unique(blockers, "mp3.metadata.ape_read_only")
            if declared_size < 32 or declared_size > cursor:
                _append_unique(blockers, "mp3.structure.invalid")
                break
            start = cursor - declared_size
            total += declared_size
            if total > limits.max_terminal_metadata_bytes:
                raise Mp3FormatError("MP3 terminal metadata byte limit exceeded")
            records.append(
                Mp3TerminalMetadata(
                    kind="apev2",
                    start=start,
                    end=cursor,
                    raw_sha256=sha256(data[start:cursor]).hexdigest(),
                )
            )
            cursor = start
            continue

        if cursor >= 15 and data[cursor - 9 : cursor] == b"LYRICS200":
            _append_unique(blockers, "mp3.metadata.lyrics3_read_only")
            size_raw = data[cursor - 15 : cursor - 9]
            if not size_raw.isdigit():
                _append_unique(blockers, "mp3.structure.invalid")
                break
            body_size = int(size_raw.decode("ascii"))
            start = cursor - 15 - body_size
            if start < 0 or data[start : start + 11] != b"LYRICSBEGIN":
                _append_unique(blockers, "mp3.structure.invalid")
                break
            length = cursor - start
            total += length
            if total > limits.max_terminal_metadata_bytes:
                raise Mp3FormatError("MP3 terminal metadata byte limit exceeded")
            records.append(
                Mp3TerminalMetadata(
                    kind="lyrics3v2",
                    start=start,
                    end=cursor,
                    raw_sha256=sha256(data[start:cursor]).hexdigest(),
                )
            )
            cursor = start
            continue

        if cursor >= 9 and data[cursor - 9 : cursor] == b"LYRICSEND":
            _append_unique(blockers, "mp3.metadata.lyrics3_read_only")
            search_budget = min(5100, limits.max_terminal_metadata_bytes)
            lower = max(0, cursor - 9 - search_budget)
            start = data.rfind(b"LYRICSBEGIN", lower, cursor - 9)
            if start < 0:
                _append_unique(blockers, "mp3.structure.invalid")
                break
            length = cursor - start
            total += length
            if total > limits.max_terminal_metadata_bytes:
                raise Mp3FormatError("MP3 terminal metadata byte limit exceeded")
            records.append(
                Mp3TerminalMetadata(
                    kind="lyrics3v1",
                    start=start,
                    end=cursor,
                    raw_sha256=sha256(data[start:cursor]).hexdigest(),
                )
            )
            cursor = start
            continue

        break

    records.reverse()
    return cursor, tuple(records), tuple(blockers)


def _parse_audio_frames(
    data: bytes,
    *,
    start: int,
    end: int,
    limits: Mp3Limits,
) -> tuple[tuple[Mp3AudioFrame, ...], str | None]:
    frames: list[Mp3AudioFrame] = []
    position = start

    while position < end:
        if len(frames) >= limits.max_audio_frames:
            raise Mp3FormatError("MP3 audio frame limit exceeded")
        if end - position < 4:
            return tuple(frames), "mp3.audio_structure_unproven"

        header = int.from_bytes(data[position : position + 4], "big")
        if (header >> 21) & 0x7FF != 0x7FF:
            return tuple(frames), "mp3.audio_structure_unproven"

        version_bits = (header >> 19) & 0b11
        layer_bits = (header >> 17) & 0b11
        bitrate_index = (header >> 12) & 0xF
        sample_rate_index = (header >> 10) & 0b11
        padding = (header >> 9) & 1

        if version_bits == 0b01:
            return tuple(frames), "mp3.audio_structure_unproven"
        if layer_bits != 0b01:
            return tuple(frames), "mp3.audio.unsupported_layer"
        if bitrate_index == 0:
            return tuple(frames), "mp3.audio.free_format_unsupported"
        if bitrate_index == 0xF or sample_rate_index == 0b11:
            return tuple(frames), "mp3.audio_structure_unproven"

        sample_rate = _SAMPLE_RATES[version_bits][sample_rate_index]
        table = _MPEG1_L3_KBPS if version_bits == 0b11 else _MPEG2_L3_KBPS
        bitrate = table[bitrate_index] * 1000
        if bitrate <= 0:
            return tuple(frames), "mp3.audio_structure_unproven"
        coefficient = 144 if version_bits == 0b11 else 72
        frame_length = (coefficient * bitrate) // sample_rate + padding
        if frame_length < 4:
            return tuple(frames), "mp3.audio_structure_unproven"
        if frame_length > limits.max_frame_bytes:
            raise Mp3FormatError("MP3 frame byte limit exceeded")
        frame_end = position + frame_length
        if frame_end > end:
            return tuple(frames), "mp3.audio_structure_unproven"

        frames.append(
            Mp3AudioFrame(
                index=len(frames),
                start=position,
                end=frame_end,
                version_bits=version_bits,
                bitrate_index=bitrate_index,
                sample_rate_index=sample_rate_index,
                padding=padding,
                frame_length=frame_length,
                raw_sha256=sha256(data[position:frame_end]).hexdigest(),
            )
        )
        position = frame_end

    if position != end or len(frames) < 2:
        return tuple(frames), "mp3.audio_structure_unproven"
    return tuple(frames), None


def parse_mp3(data: bytes, *, limits: Mp3Limits | None = None) -> ParsedMp3:
    active_limits = limits or Mp3Limits()
    if len(data) > active_limits.max_source_bytes:
        raise Mp3FormatError("MP3 source exceeds source byte limit")
    if len(data) < 128 or data[-128:-125] != b"TAG":
        raise Mp3FormatError("MP3 source is missing a terminal ID3v1 tag")

    id3v1_start = len(data) - 128
    id3v1_end = len(data)
    id3v1_raw = data[id3v1_start:id3v1_end]
    blockers: list[str] = []

    owners = tuple(
        _parse_owner(data, tag_start=id3v1_start, field=field, relative=relative)
        for field, relative in _FIELD_LAYOUT
    )
    if any(not owner.canonical_padding for owner in owners):
        _append_unique(blockers, "mp3.id3v1.invalid_padding")

    comment_raw = id3v1_raw[97:127]
    if comment_raw[28] == 0 and comment_raw[29] != 0:
        id3v1_version = "1.1"
        track: int | None = comment_raw[29]
    else:
        id3v1_version = "1.0"
        track = None

    audio_end, terminal_metadata, terminal_blockers = _terminal_metadata(
        data,
        id3v1_start=id3v1_start,
        limits=active_limits,
    )
    for blocker in terminal_blockers:
        _append_unique(blockers, blocker)

    if data.startswith(b"ID3"):
        _append_unique(blockers, "mp3.metadata.id3v2_read_only")

    audio_frames, audio_reason = _parse_audio_frames(
        data,
        start=0,
        end=audio_end,
        limits=active_limits,
    )
    if audio_reason is not None:
        _append_unique(blockers, audio_reason)

    competing = any(
        blocker
        in {
            "mp3.metadata.id3v2_read_only",
            "mp3.metadata.ape_read_only",
            "mp3.metadata.lyrics3_read_only",
        }
        for blocker in blockers
    )
    audio_authoritative = audio_reason is None and not competing

    return ParsedMp3(
        source_size=len(data),
        audio_start=0,
        audio_end=audio_end,
        audio_frames=audio_frames,
        terminal_metadata=terminal_metadata,
        id3v1_start=id3v1_start,
        id3v1_end=id3v1_end,
        id3v1_sha256=sha256(id3v1_raw).hexdigest(),
        id3v1_version=id3v1_version,
        track=track,
        owners=owners,
        audio_authoritative=audio_authoritative,
        blockers=tuple(blockers),
    )
