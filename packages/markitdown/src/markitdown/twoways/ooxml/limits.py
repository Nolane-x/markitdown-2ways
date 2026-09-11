from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class OOXMLPackageLimits:
    max_members: int = 10_000
    max_member_uncompressed_bytes: int = 64 * 1024 * 1024
    max_total_uncompressed_bytes: int = 512 * 1024 * 1024
    max_compression_ratio: float = 200.0
    max_xml_part_bytes: int = 64 * 1024 * 1024

    def __post_init__(self) -> None:
        if self.max_members < 1:
            raise ValueError("max_members must be >= 1")
        if self.max_member_uncompressed_bytes < 1:
            raise ValueError("max_member_uncompressed_bytes must be >= 1")
        if self.max_total_uncompressed_bytes < 1:
            raise ValueError("max_total_uncompressed_bytes must be >= 1")
        if self.max_xml_part_bytes < 1:
            raise ValueError("max_xml_part_bytes must be >= 1")
        if self.max_compression_ratio <= 0:
            raise ValueError("max_compression_ratio must be > 0")
