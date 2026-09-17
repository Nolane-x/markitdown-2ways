from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class JpegLimits:
    max_source_bytes: int = 64 * 1024 * 1024
    max_markers: int = 4096
    max_segment_data_bytes: int = 65533
    max_ifd_depth: int = 8
    max_ifd_entries: int = 4096
    max_total_ifd_entries: int = 8192
    max_tiff_value_bytes: int = 16 * 1024 * 1024
    max_text_value_bytes: int = 64 * 1024

    def __post_init__(self) -> None:
        for name, value in vars(self).items():
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"{name} must be a positive integer")
