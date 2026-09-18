from __future__ import annotations

from hashlib import sha256
from io import BytesIO

import pytest

from markitdown._stream_info import StreamInfo
from markitdown.twoways import (
    CapabilityState,
    XlsxConverterSnapshot,
    XlsxSheetMarkdownSnapshot,
    build_capability_report,
    canonical_json_bytes,
    canonical_json_digest,
    capabilities_for_node,
    decode_document,
    read_xlsx_converter_snapshot_ir,
)
from markitdown.twoways.ir.nodes import TextPayload


SOURCE = b"PK\x03\x04H29 derived XLSX fixture"
INFO = StreamInfo(
    extension=".xlsx",
    mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    filename="fixture.xlsx",
)
SHEETS = (
    XlsxSheetMarkdownSnapshot(
        name="Summary",
        markdown="\n| Region | Revenue |\n| --- | --- |\n| APAC | 38 |\n\n",
        materialization_id="sheet-1",
    ),
    XlsxSheetMarkdownSnapshot(
        name="Data",
        markdown="  second sheet  ",
        materialization_id="sheet-2",
    ),
)
EXPECTED = (
    "## Summary\n"
    "| Region | Revenue |\n"
    "| --- | --- |\n"
    "| APAC | 38 |\n\n"
    "## Data\n"
    "second sheet"
)


def _snapshot(
    *,
    sheets: tuple[XlsxSheetMarkdownSnapshot, ...] = SHEETS,
    provider: str = "offline-xlsx-materializer",
) -> XlsxConverterSnapshot:
    return XlsxConverterSnapshot(
        sheets=sheets,
        provider=provider,
        materialization_id="workbook-001",
        table_provider="fake-pandas-openpyxl",
        html_markdown_provider="fake-html-converter",
        materialization_path="openpyxl-direct",
    )


def _root(document):
    assert len(document.root_node_ids) == 1
    return document.nodes[document.root_node_ids[0]]


def test_reader_binds_source_ordered_sheets_and_exact_projection() -> None:
    document = read_xlsx_converter_snapshot_ir(
        BytesIO(SOURCE),
        stream_info=INFO,
        snapshot=_snapshot(),
    )
    node = _root(document)

    assert isinstance(node.payload, TextPayload)
    assert node.payload.text == EXPECTED
    assert node.semantic_role == "derived_workbook"
    assert node.native_locator is None
    assert document.canvases[0].kind == "derived-xlsx-workbook"
    assert document.canvases[0].native_locator is None

    assert document.source is not None
    assert document.source.format == "xlsx-converter-derived-source"
    assert document.source.filename == "fixture.xlsx"
    assert document.source.mimetype == INFO.mimetype
    assert document.source.sha256 == sha256(SOURCE).hexdigest()
    assert document.source.size_bytes == len(SOURCE)

    evidence = document.metadata.custom["twoways.xlsx_converter_snapshot.v1"]
    assert evidence["source_sha256"] == sha256(SOURCE).hexdigest()
    assert evidence["source_size_bytes"] == len(SOURCE)
    assert evidence["accepted_by"] == "extension"
    assert evidence["provider"] == "offline-xlsx-materializer"
    assert evidence["materialization_id"] == "workbook-001"
    assert evidence["table_provider"] == "fake-pandas-openpyxl"
    assert evidence["html_markdown_provider"] == "fake-html-converter"
    assert evidence["materialization_path"] == "openpyxl-direct"
    assert evidence["materialization_path_verified_by_twoways"] is False
    assert evidence["sheet_count"] == 2
    assert evidence["sheet_names"] == ["Summary", "Data"]
    assert evidence["xlsx_parsing_performed_by_twoways"] is False
    assert evidence["pandas_executed_by_twoways"] is False
    assert evidence["openpyxl_executed_by_twoways"] is False
    assert evidence["show_zeroes_repair_executed_by_twoways"] is False
    assert evidence["html_conversion_executed_by_twoways"] is False
    assert evidence["network_performed_by_twoways"] is False
    assert evidence["subprocess_performed_by_twoways"] is False

    sheet_evidence = evidence["sheets"]
    assert sheet_evidence[0]["index"] == 0
    assert sheet_evidence[0]["name"] == "Summary"
    assert sheet_evidence[0]["raw_markdown_sha256"] == sha256(
        SHEETS[0].markdown.encode("utf-8")
    ).hexdigest()
    assert sheet_evidence[0]["stripped_markdown_sha256"] == sha256(
        SHEETS[0].markdown.strip().encode("utf-8")
    ).hexdigest()


@pytest.mark.parametrize(
    ("markdown", "expected"),
    (
        (" value ", "## Only\nvalue"),
        ("\n\nvalue\n\n", "## Only\nvalue"),
        ("", "## Only"),
        ("   ", "## Only"),
        ("a\n\nb", "## Only\na\n\nb"),
    ),
)
def test_per_sheet_strip_and_final_strip_are_exact(
    markdown: str,
    expected: str,
) -> None:
    document = read_xlsx_converter_snapshot_ir(
        BytesIO(SOURCE),
        stream_info=INFO,
        snapshot=_snapshot(
            sheets=(XlsxSheetMarkdownSnapshot(name="Only", markdown=markdown),)
        ),
    )
    assert _root(document).payload.text == expected


def test_sheet_order_is_identity_bearing_and_preserved() -> None:
    first = _snapshot(
        sheets=(
            XlsxSheetMarkdownSnapshot(name="A", markdown="alpha"),
            XlsxSheetMarkdownSnapshot(name="B", markdown="beta"),
        )
    )
    second = _snapshot(
        sheets=(
            XlsxSheetMarkdownSnapshot(name="B", markdown="beta"),
            XlsxSheetMarkdownSnapshot(name="A", markdown="alpha"),
        )
    )

    first_doc = read_xlsx_converter_snapshot_ir(
        BytesIO(SOURCE), stream_info=INFO, snapshot=first
    )
    second_doc = read_xlsx_converter_snapshot_ir(
        BytesIO(SOURCE), stream_info=INFO, snapshot=second
    )

    assert _root(first_doc).payload.text == "## A\nalpha\n\n## B\nbeta"
    assert _root(second_doc).payload.text == "## B\nbeta\n\n## A\nalpha"
    assert first_doc.document_id != second_doc.document_id


def test_root_is_derived_and_native_xlsx_remains_authoritative() -> None:
    document = read_xlsx_converter_snapshot_ir(
        BytesIO(SOURCE),
        stream_info=INFO,
        snapshot=_snapshot(),
    )
    node = _root(document)
    decision = capabilities_for_node(node).for_operation("replace_text")

    assert decision.state is CapabilityState.DERIVED
    assert decision.reason_code == "xlsx.output.not_native_writable"
    assert decision.constraints == {
        "identity_markdown": False,
        "native_owner": False,
        "remote_writeback": False,
        "materialization": "explicit-local-only",
    }

    report = build_capability_report(document)
    assert report.total_nodes == 1
    assert report.derived_nodes == 1
    assert report.writable_nodes == 0
    assert dict(report.writable_by_operation) == {}


def test_source_and_sheet_content_are_independent_identity_authorities() -> None:
    baseline = read_xlsx_converter_snapshot_ir(
        BytesIO(SOURCE), stream_info=INFO, snapshot=_snapshot()
    )
    changed_source = read_xlsx_converter_snapshot_ir(
        BytesIO(SOURCE + b"x"), stream_info=INFO, snapshot=_snapshot()
    )
    changed_sheet = read_xlsx_converter_snapshot_ir(
        BytesIO(SOURCE),
        stream_info=INFO,
        snapshot=_snapshot(
            sheets=(
                XlsxSheetMarkdownSnapshot(name="Summary", markdown="changed"),
                SHEETS[1],
            )
        ),
    )

    assert baseline.source is not None
    assert changed_source.source is not None
    assert changed_sheet.source is not None
    assert (
        len(
            {
                baseline.document_id,
                changed_source.document_id,
                changed_sheet.document_id,
            }
        )
        == 3
    )
    assert baseline.source.sha256 != changed_source.source.sha256
    assert baseline.source.sha256 == changed_sheet.source.sha256


def test_repeated_reads_and_canonical_round_trip_are_deterministic() -> None:
    first = read_xlsx_converter_snapshot_ir(
        BytesIO(SOURCE), stream_info=INFO, snapshot=_snapshot()
    )
    second = read_xlsx_converter_snapshot_ir(
        BytesIO(SOURCE), stream_info=INFO, snapshot=_snapshot()
    )

    assert canonical_json_digest(first) == canonical_json_digest(second)
    encoded = canonical_json_bytes(first)
    decoded = decode_document(encoded)
    assert canonical_json_bytes(decoded) == encoded


@pytest.mark.parametrize(
    ("info", "accepted_by"),
    (
        (StreamInfo(extension=".xlsx"), "extension"),
        (StreamInfo(extension=".XLSX"), "extension"),
        (
            StreamInfo(
                mimetype=(
                    "application/vnd.openxmlformats-officedocument."
                    "spreadsheetml.sheet"
                )
            ),
            "mimetype",
        ),
        (
            StreamInfo(
                mimetype=(
                    "application/vnd.openxmlformats-officedocument."
                    "spreadsheetml.sheet; charset=binary"
                )
            ),
            "mimetype",
        ),
    ),
)
def test_explicit_one_way_acceptance_surface(
    info: StreamInfo,
    accepted_by: str,
) -> None:
    document = read_xlsx_converter_snapshot_ir(
        BytesIO(SOURCE),
        stream_info=info,
        snapshot=_snapshot(),
    )
    evidence = document.metadata.custom["twoways.xlsx_converter_snapshot.v1"]
    assert evidence["accepted_by"] == accepted_by


@pytest.mark.parametrize(
    "info",
    (
        StreamInfo(),
        StreamInfo(extension=".xls"),
        StreamInfo(mimetype="application/vnd.ms-excel"),
        StreamInfo(extension=".xlsm"),
    ),
)
def test_outside_explicit_surface_fails_closed(info: StreamInfo) -> None:
    with pytest.raises(ValueError, match="XlsxConverter"):
        read_xlsx_converter_snapshot_ir(
            BytesIO(SOURCE),
            stream_info=info,
            snapshot=_snapshot(),
        )
