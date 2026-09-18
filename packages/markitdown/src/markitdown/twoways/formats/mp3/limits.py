from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Mp3Limits:
    max_source_bytes: int = 64 * 1024 * 1024
    max_audio_frames: int = 1_000_000
    max_frame_bytes: int = 8192
    max_terminal_metadata_bytes: int = 1024 * 1024

    def __post_init__(self) -> None:
        for name, value in vars(self).items():
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"{name} must be a positive integer")
