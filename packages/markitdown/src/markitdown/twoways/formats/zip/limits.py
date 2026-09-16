from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ZipRecursiveLimits:
    max_depth: int = 4
    max_members_per_archive: int = 10_000
    max_global_members: int = 10_000
    max_member_uncompressed_bytes: int = 64 * 1024 * 1024
    max_archive_uncompressed_bytes: int = 512 * 1024 * 1024
    max_global_expanded_bytes: int = 512 * 1024 * 1024
    max_compression_ratio: float = 200.0

    def __post_init__(self) -> None:
        for name in (
            "max_depth",
            "max_members_per_archive",
            "max_global_members",
            "max_member_uncompressed_bytes",
            "max_archive_uncompressed_bytes",
            "max_global_expanded_bytes",
        ):
            if getattr(self, name) < 1:
                raise ValueError(f"{name} must be >= 1")
        if self.max_compression_ratio <= 0:
            raise ValueError("max_compression_ratio must be > 0")
