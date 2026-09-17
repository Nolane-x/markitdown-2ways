from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PngChunk:
    index: int
    chunk_type: str
    length: int
    start: int
    end: int
    data_start: int
    data_end: int
    stored_crc: int
    computed_crc: int
    raw_sha256: str
    data_sha256: str
    raw: bytes
    data: bytes


@dataclass(frozen=True)
class PngTextOwner:
    chunk_index: int
    keyword: str
    value: str
    raw_sha256: str
    data_sha256: str


@dataclass(frozen=True)
class ParsedPng:
    source_size: int
    chunks: tuple[PngChunk, ...]
    text_owners: tuple[PngTextOwner, ...]
    is_apng: bool = False

    def chunk(self, index: int) -> PngChunk:
        if index < 0 or index >= len(self.chunks):
            raise IndexError(index)
        return self.chunks[index]

    def text_owner(self, index: int) -> PngTextOwner | None:
        for owner in self.text_owners:
            if owner.chunk_index == index:
                return owner
        return None
