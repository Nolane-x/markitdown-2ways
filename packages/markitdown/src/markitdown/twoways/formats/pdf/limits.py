from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PdfNativeLimits:
    max_source_bytes: int = 512 * 1024 * 1024
    max_pages: int = 20_000
    max_increment_bytes: int = 4 * 1024 * 1024
    max_metadata_value_chars: int = 64 * 1024
    max_total_metadata_chars: int = 256 * 1024

    def __post_init__(self) -> None:
        for name, value in (
            ("max_source_bytes", self.max_source_bytes),
            ("max_pages", self.max_pages),
            ("max_increment_bytes", self.max_increment_bytes),
            ("max_metadata_value_chars", self.max_metadata_value_chars),
            ("max_total_metadata_chars", self.max_total_metadata_chars),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"{name} must be a positive integer")
