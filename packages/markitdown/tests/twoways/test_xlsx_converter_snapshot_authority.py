from __future__ import annotations

from io import BytesIO

import pytest

from markitdown.twoways import (
    XlsxConverterSnapshot,
    XlsxDerivedLimits,
    XlsxSheetMarkdownSnapshot,
    read_xlsx_converter_snapshot_ir,
)

from .test_xlsx_converter_snapshot_reader import EXPECTED, INFO, SHEETS, SOURCE, _snapshot


class _BoundedReadProbe(BytesIO):
    def __init__(self, data: bytes, *, maximum_request: int) -> None:
        super().__init__(data)
        self.maximum_request = maximum_request
        self.requests: list[int] = []

    def read(self, size: int = -1) -> bytes:
        self.requests.append(size)
        if size < 0 or size > self.maximum_request:
            raise AssertionError(f"unbounded read request: {size}")
        return super().read(size)


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("name", ""),
        ("name", "   "),
        ("materialization_id", ""),
    ),
)
def test_sheet_snapshot_descriptors_reject_blank_values(
    field: str,
    value: str,
) -> None:
    values = {"name": "Sheet1", "markdown": "value", "materialization_id": "id-1"}
    values[field] = value
    with pytest.raises(ValueError, match=field):
        XlsxSheetMarkdownSnapshot(**values)


def test_sheet_snapshot_rejects_non_string_markdown() -> None:
    with pytest.raises(TypeError, match="markdown"):
        XlsxSheetMarkdownSnapshot(name="Sheet1", markdown=b"bytes")


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("provider", ""),
        ("provider", "   "),
        ("materialization_id", ""),
        ("table_provider", " "),
        ("html_markdown_provider", ""),
        ("materialization_path", " "),
    ),
)
def test_workbook_snapshot_descriptors_reject_blank_values(
    field: str,
    value: str,
) -> None:
    values = {
        "sheets": SHEETS,
        "provider": "fixture",
        "materialization_id": "workbook-id",
        "table_provider": "table-provider",
        "html_markdown_provider": "html-provider",
        "materialization_path": "openpyxl-direct",
    }
    values[field] = value
    with pytest.raises(ValueError, match=field):
        XlsxConverterSnapshot(**values)


def test_workbook_snapshot_requires_non_empty_tuple_and_unique_names() -> None:
    with pytest.raises(TypeError, match="tuple"):
        XlsxConverterSnapshot(sheets=list(SHEETS), provider="fixture")

    with pytest.raises(ValueError, match="non-empty"):
        XlsxConverterSnapshot(sheets=(), provider="fixture")

    duplicate = (
        XlsxSheetMarkdownSnapshot(name="A", markdown="one"),
        XlsxSheetMarkdownSnapshot(name="A", markdown="two"),
    )
    with pytest.raises(ValueError, match="unique"):
        XlsxConverterSnapshot(sheets=duplicate, provider="fixture")


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("max_source_bytes", 0),
        ("max_sheet_count", 0),
        ("max_materialized_utf8_bytes", 0),
        ("max_markdown_utf8_bytes", 0),
        ("max_source_bytes", True),
        ("max_sheet_count", False),
        ("max_materialized_utf8_bytes", 1.5),
    ),
)
def test_limits_fail_closed(field: str, value: object) -> None:
    with pytest.raises((TypeError, ValueError)):
        XlsxDerivedLimits(**{field: value})


def test_source_limit_accepts_exact_boundary_and_reads_bounded() -> None:
    probe = _BoundedReadProbe(SOURCE, maximum_request=64 * 1024)
    exact = read_xlsx_converter_snapshot_ir(
        probe,
        stream_info=INFO,
        snapshot=_snapshot(),
        limits=XlsxDerivedLimits(max_source_bytes=len(SOURCE)),
    )
    assert exact.source is not None
    assert exact.source.size_bytes == len(SOURCE)
    assert probe.requests
    assert all(0 <= size <= 64 * 1024 for size in probe.requests)

    with pytest.raises(ValueError, match="max_source_bytes"):
        read_xlsx_converter_snapshot_ir(
            BytesIO(SOURCE),
            stream_info=INFO,
            snapshot=_snapshot(),
            limits=XlsxDerivedLimits(max_source_bytes=len(SOURCE) - 1),
        )


def test_sheet_count_and_markdown_limits_have_exact_boundaries() -> None:
    raw_size = sum(len(sheet.markdown.encode("utf-8")) for sheet in SHEETS)
    markdown_size = len(EXPECTED.encode("utf-8"))

    exact = read_xlsx_converter_snapshot_ir(
        BytesIO(SOURCE),
        stream_info=INFO,
        snapshot=_snapshot(),
        limits=XlsxDerivedLimits(
            max_sheet_count=len(SHEETS),
            max_materialized_utf8_bytes=raw_size,
            max_markdown_utf8_bytes=markdown_size,
        ),
    )
    assert exact.root_node_ids

    with pytest.raises(ValueError, match="max_sheet_count"):
        read_xlsx_converter_snapshot_ir(
            BytesIO(SOURCE),
            stream_info=INFO,
            snapshot=_snapshot(),
            limits=XlsxDerivedLimits(max_sheet_count=len(SHEETS) - 1),
        )

    with pytest.raises(ValueError, match="max_materialized_utf8_bytes"):
        read_xlsx_converter_snapshot_ir(
            BytesIO(SOURCE),
            stream_info=INFO,
            snapshot=_snapshot(),
            limits=XlsxDerivedLimits(max_materialized_utf8_bytes=raw_size - 1),
        )

    with pytest.raises(ValueError, match="max_markdown_utf8_bytes"):
        read_xlsx_converter_snapshot_ir(
            BytesIO(SOURCE),
            stream_info=INFO,
            snapshot=_snapshot(),
            limits=XlsxDerivedLimits(max_markdown_utf8_bytes=markdown_size - 1),
        )


def test_snapshot_must_use_explicit_type() -> None:
    with pytest.raises(TypeError, match="XlsxConverterSnapshot"):
        read_xlsx_converter_snapshot_ir(
            BytesIO(SOURCE),
            stream_info=INFO,
            snapshot={"sheets": []},
        )


def test_source_stream_must_return_bytes() -> None:
    class _TextStream:
        def read(self, size: int = -1) -> str:
            return "text"

    with pytest.raises(TypeError, match="bytes"):
        read_xlsx_converter_snapshot_ir(
            _TextStream(),
            stream_info=INFO,
            snapshot=_snapshot(),
        )
