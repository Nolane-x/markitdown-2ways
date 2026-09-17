from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Mp3AudioFrame:
    index: int
    start: int
    end: int
    version_bits: int
    bitrate_index: int
    sample_rate_index: int
    padding: int
    frame_length: int
    raw_sha256: str


@dataclass(frozen=True)
class Mp3TerminalMetadata:
    kind: str
    start: int
    end: int
    raw_sha256: str


@dataclass(frozen=True)
class Mp3Id3v1Owner:
    field: str
    slot_start: int
    slot_end: int
    slot_length: int
    value: str
    slot_sha256: str
    full_width: bool
    canonical_padding: bool


@dataclass(frozen=True)
class ParsedMp3:
    source_size: int
    audio_start: int
    audio_end: int
    audio_frames: tuple[Mp3AudioFrame, ...]
    terminal_metadata: tuple[Mp3TerminalMetadata, ...]
    id3v1_start: int
    id3v1_end: int
    id3v1_sha256: str
    id3v1_version: str
    track: int | None
    owners: tuple[Mp3Id3v1Owner, ...]
    audio_authoritative: bool
    blockers: tuple[str, ...]

    def owner(self, field: str) -> Mp3Id3v1Owner:
        for owner in self.owners:
            if owner.field == field:
                return owner
        raise KeyError(field)
