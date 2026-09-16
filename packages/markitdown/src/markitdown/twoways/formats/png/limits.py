from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PngLimits:
    max_source_bytes: int = 64 * 1024 * 1024
    max_chunks: int = 16_384
    max_chunk_data_bytes: int = 16 * 1024 * 1024
    max_text_value_bytes: int = 1024 * 1024

    def __post_init__(self) -> None:
        for field_name in (
            "max_source_bytes",
            "max_chunks",
            "max_chunk_data_bytes",
            "max_text_value_bytes",
        ):
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"{field_name} must be a positive integer")
