from __future__ import annotations

from hashlib import sha256
from io import BytesIO

import pytest

from markitdown._stream_info import StreamInfo
from markitdown.twoways import (
    CapabilityState,
    PdfConverterExtractionSnapshot,
    build_capability_report,
    canonical_json_bytes,
    canonical_json_digest,
    capabilities_for_node,
    decode_document,
    read_pdf_converter_snapshot_ir,
)
from markitdown.twoways.ir.nodes import TextPayload


SOURCE = b"%PDF-1.7\nH27 derived fixture\n"
RAW_TEXT = (
    "SECTION 01\n"
    ".1\n"
    "\n"
    "General requirements\n"
    ".2\n"
    "Second requirement\n"
    "Tail\n"
)
EXPECTED = (
    "SECTION 01\n"
    ".1 General requirements\n"
    ".2 Second requirement\n"
    "Tail\n"
)
INFO = StreamInfo(
    extension=".pdf",
    mimetype="application/pdf",
    filename="fixture.pdf",
)


def _snapshot(**updates: object) -> PdfConverterExtractionSnapshot:
    values = {
        "extracted_text": RAW_TEXT,
        "provider": "offline-pdf-materializer",
        "extraction_path": "pdfminer-whole-document",
        "materialization_id": "pdf-001",
    }
    values.update(updates)
    return PdfConverterExtractionSnapshot(**values)


def _root(document):
    assert len(document.root_node_ids) == 1
    return document.nodes[document.root_node_ids[0]]


def test_reader_binds_source_snapshot_and_exact_postprocess() -> None:
    document = read_pdf_converter_snapshot_ir(
        BytesIO(SOURCE),
        stream_info=INFO,
        snapshot=_snapshot(),
    )
    node = _root(document)

    assert isinstance(node.payload, TextPayload)
    assert node.payload.text == EXPECTED
    assert node.semantic_role == "derived_document"
    assert node.native_locator is None
    assert document.canvases[0].kind == "derived-pdf-extraction"
    assert document.canvases[0].native_locator is None

    assert document.source is not None
    assert document.source.format == "pdf-converter-derived-source"
    assert document.source.filename == "fixture.pdf"
    assert document.source.mimetype == "application/pdf"
    assert document.source.sha256 == sha256(SOURCE).hexdigest()
    assert document.source.size_bytes == len(SOURCE)

    evidence = document.metadata.custom["twoways.pdf_converter_snapshot.v1"]
    raw_bytes = RAW_TEXT.encode("utf-8")
    markdown_bytes = EXPECTED.encode("utf-8")
    assert evidence["source_sha256"] == sha256(SOURCE).hexdigest()
    assert evidence["source_size_bytes"] == len(SOURCE)
    assert evidence["accepted_by"] == "extension"
    assert evidence["provider"] == "offline-pdf-materializer"
    assert evidence["extraction_path"] == "pdfminer-whole-document"
    assert evidence["materialization_id"] == "pdf-001"
    assert evidence["extracted_text_sha256"] == sha256(raw_bytes).hexdigest()
    assert evidence["extracted_text_utf8_size_bytes"] == len(raw_bytes)
    assert evidence["markdown_sha256"] == sha256(markdown_bytes).hexdigest()
    assert evidence["markdown_utf8_size_bytes"] == len(markdown_bytes)
    assert evidence["pdf_parsing_performed_by_twoways"] is False
    assert evidence["pdfminer_executed_by_twoways"] is False
    assert evidence["pdfplumber_executed_by_twoways"] is False
    assert evidence["network_performed_by_twoways"] is False
    assert evidence["subprocess_performed_by_twoways"] is False
    assert evidence["extraction_path_verified_by_twoways"] is False


@pytest.mark.parametrize(
    ("raw", "expected"),
    (
        (".1\nText", ".1 Text"),
        (".10\n\n\nText", ".10 Text"),
        (" .2 \nNext", ".2 Next"),
        (".3", ".3"),
        (".4\n\n", ".4\n\n"),
        (".A\nText", ".A\nText"),
        ("1.\nText", "1.\nText"),
        ("prefix\n.5\nNext\nsuffix", "prefix\n.5 Next\nsuffix"),
        ("", ""),
    ),
)
def test_partial_numbering_semantics_are_exact(raw: str, expected: str) -> None:
    document = read_pdf_converter_snapshot_ir(
        BytesIO(SOURCE),
        stream_info=INFO,
        snapshot=_snapshot(extracted_text=raw),
    )
    assert _root(document).payload.text == expected


def test_root_is_derived_and_h9_h11_remain_native_authority() -> None:
    document = read_pdf_converter_snapshot_ir(
        BytesIO(SOURCE),
        stream_info=INFO,
        snapshot=_snapshot(),
    )
    node = _root(document)
    decision = capabilities_for_node(node).for_operation("replace_text")

    assert decision.state is CapabilityState.DERIVED
    assert decision.reason_code == "pdf.output.not_native_writable"
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


def test_source_and_extraction_are_independent_identity_authorities() -> None:
    baseline = read_pdf_converter_snapshot_ir(
        BytesIO(SOURCE), stream_info=INFO, snapshot=_snapshot()
    )
    changed_source = read_pdf_converter_snapshot_ir(
        BytesIO(SOURCE + b"x"), stream_info=INFO, snapshot=_snapshot()
    )
    changed_snapshot = read_pdf_converter_snapshot_ir(
        BytesIO(SOURCE),
        stream_info=INFO,
        snapshot=_snapshot(extracted_text=RAW_TEXT + "changed"),
    )

    assert baseline.source is not None
    assert changed_source.source is not None
    assert changed_snapshot.source is not None
    assert len(
        {
            baseline.document_id,
            changed_source.document_id,
            changed_snapshot.document_id,
        }
    ) == 3
    assert baseline.source.sha256 != changed_source.source.sha256
    assert baseline.source.sha256 == changed_snapshot.source.sha256


def test_repeated_reads_and_canonical_round_trip_are_deterministic() -> None:
    first = read_pdf_converter_snapshot_ir(
        BytesIO(SOURCE), stream_info=INFO, snapshot=_snapshot()
    )
    second = read_pdf_converter_snapshot_ir(
        BytesIO(SOURCE), stream_info=INFO, snapshot=_snapshot()
    )

    assert canonical_json_digest(first) == canonical_json_digest(second)
    encoded = canonical_json_bytes(first)
    decoded = decode_document(encoded)
    assert canonical_json_bytes(decoded) == encoded


@pytest.mark.parametrize(
    ("info", "accepted_by"),
    (
        (StreamInfo(extension=".pdf"), "extension"),
        (StreamInfo(extension=".PDF"), "extension"),
        (StreamInfo(mimetype="application/pdf"), "mimetype"),
        (StreamInfo(mimetype="application/x-pdf"), "mimetype"),
        (StreamInfo(mimetype="application/pdf; charset=binary"), "mimetype"),
    ),
)
def test_explicit_one_way_acceptance_surface(
    info: StreamInfo, accepted_by: str
) -> None:
    document = read_pdf_converter_snapshot_ir(
        BytesIO(SOURCE),
        stream_info=info,
        snapshot=_snapshot(),
    )
    evidence = document.metadata.custom["twoways.pdf_converter_snapshot.v1"]
    assert evidence["accepted_by"] == accepted_by


@pytest.mark.parametrize(
    "info",
    (
        StreamInfo(),
        StreamInfo(extension=".txt"),
        StreamInfo(mimetype="text/plain"),
        StreamInfo(extension=".pdfx"),
    ),
)
def test_outside_explicit_surface_fails_closed(info: StreamInfo) -> None:
    with pytest.raises(ValueError, match="PdfConverter"):
        read_pdf_converter_snapshot_ir(
            BytesIO(SOURCE),
            stream_info=info,
            snapshot=_snapshot(),
        )
