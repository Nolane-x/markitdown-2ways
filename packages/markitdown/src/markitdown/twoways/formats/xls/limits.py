from __future__ import annotations

from dataclasses import dataclass, fields


@dataclass(frozen=True)
class XlsLimits:
    max_source_bytes: int = 64 * 1024 * 1024
    max_difat_sectors: int = 4096
    max_fat_sectors: int = 8192
    max_chain_sectors: int = 131072
    max_directory_entries: int = 16384
    max_minifat_sectors: int = 8192
    max_stream_bytes: int = 48 * 1024 * 1024
    max_total_owned_stream_bytes: int = 64 * 1024 * 1024
    max_workbook_bytes: int = 48 * 1024 * 1024
    max_biff_records: int = 1_000_000
    max_sheets: int = 4096
    max_number_owners: int = 1_000_000

    def __post_init__(self) -> None:
        for field in fields(self):
            value = getattr(self, field.name)
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"{field.name} must be a positive integer")
