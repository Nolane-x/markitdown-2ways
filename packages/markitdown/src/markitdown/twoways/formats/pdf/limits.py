from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PdfNativeLimits:
    max_source_bytes: int = 512 * 1024 * 1024
    max_pages: int = 20_000
    max_increment_bytes: int = 4 * 1024 * 1024
    max_metadata_value_chars: int = 64 * 1024
    max_total_metadata_chars: int = 256 * 1024
    max_total_annotations: int = 10_000
    max_annotations_per_page: int = 2_000
    max_uri_chars: int = 16 * 1024
    max_total_uri_chars: int = 256 * 1024
    max_total_form_fields: int = 10_000
    max_field_tree_depth: int = 64
    max_field_name_chars: int = 4 * 1024
    max_form_value_chars: int = 64 * 1024
    max_total_form_value_chars: int = 256 * 1024

    def __post_init__(self) -> None:
        for name, value in (
            ("max_source_bytes", self.max_source_bytes),
            ("max_pages", self.max_pages),
            ("max_increment_bytes", self.max_increment_bytes),
            ("max_metadata_value_chars", self.max_metadata_value_chars),
            ("max_total_metadata_chars", self.max_total_metadata_chars),
            ("max_total_annotations", self.max_total_annotations),
            ("max_annotations_per_page", self.max_annotations_per_page),
            ("max_uri_chars", self.max_uri_chars),
            ("max_total_uri_chars", self.max_total_uri_chars),
            ("max_total_form_fields", self.max_total_form_fields),
            ("max_field_tree_depth", self.max_field_tree_depth),
            ("max_field_name_chars", self.max_field_name_chars),
            ("max_form_value_chars", self.max_form_value_chars),
            ("max_total_form_value_chars", self.max_total_form_value_chars),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"{name} must be a positive integer")
