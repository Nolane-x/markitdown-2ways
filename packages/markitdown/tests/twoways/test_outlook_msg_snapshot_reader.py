from __future__ import annotations

from hashlib import sha256
from io import BytesIO

import pytest

from markitdown._stream_info import StreamInfo
from markitdown.twoways import (
    CapabilityState,
    OutlookMsgConverterSnapshot,
    build_capability_report,
    canonical_json_bytes,
    canonical_json_digest,
    capabilities_for_node,
    decode_document,
    read_outlook_msg_snapshot_ir,
)
from markitdown.twoways.ir.nodes import TextPayload


SOURCE = b"outlook msg derived fixture"
INFO = StreamInfo(
    extension=".msg",
    mimetype="application/vnd.ms-outlook",
    filename="mail.msg",
)
SNAPSHOT = OutlookMsgConverterSnapshot(
    sender="alice@example.com",
    recipients="bob@example.com",
    subject="Quarterly update",
    body="Hello Bob,\n\nThe report is attached.",
    provider="offline-msg-materializer",
    materialization_id="msg-001",
    message_encoding="utf-16-le",
    internet_encoding="utf-8",
)


def _root(document):
    assert len(document.root_node_ids) == 1
    return document.nodes[document.root_node_ids[0]]


def test_full_snapshot_reconstructs_exact_one_way_projection_and_title() -> None:
    document = read_outlook_msg_snapshot_ir(
        BytesIO(SOURCE),
        stream_info=INFO,
        snapshot=SNAPSHOT,
    )
    node = _root(document)

    assert isinstance(node.payload, TextPayload)
    assert node.payload.text == (
        "# Email Message\n\n"
        "**From:** alice@example.com\n"
        "**To:** bob@example.com\n"
        "**Subject:** Quarterly update\n"
        "\n## Content\n\n"
        "Hello Bob,\n\nThe report is attached."
    )
    assert node.semantic_role == "derived_message"
    assert node.native_locator is None
    assert document.canvases[0].kind == "derived-message"
    assert document.canvases[0].native_locator is None

    assert document.source is not None
    assert document.source.format == "outlook-msg-converter-derived-source"
    assert document.source.sha256 == sha256(SOURCE).hexdigest()
    assert document.source.size_bytes == len(SOURCE)
    assert document.metadata.title == "Quarterly update"

    evidence = document.metadata.custom["twoways.outlook_msg_converter_snapshot.v1"]
    assert evidence["accepted_by"] == "extension"
    assert evidence["provider"] == "offline-msg-materializer"
    assert evidence["materialization_id"] == "msg-001"
    assert evidence["message_encoding"] == "utf-16-le"
    assert evidence["internet_encoding"] == "utf-8"
    assert evidence["ole_parser_executed_by_twoways"] is False
    assert evidence["charset_detection_executed_by_twoways"] is False
    assert evidence["network_performed_by_twoways"] is False
    assert evidence["subprocess_performed_by_twoways"] is False


def test_falsey_fields_follow_one_way_truthiness_and_final_strip() -> None:
    document = read_outlook_msg_snapshot_ir(
        BytesIO(SOURCE),
        stream_info=INFO,
        snapshot=OutlookMsgConverterSnapshot(
            sender="",
            recipients=None,
            subject="Only subject",
            body="",
            provider="fixture",
        ),
    )

    assert _root(document).payload.text == (
        "# Email Message\n\n" "**Subject:** Only subject\n" "\n## Content"
    )
    assert document.metadata.title == "Only subject"


def test_empty_snapshot_still_matches_one_way_scaffold() -> None:
    document = read_outlook_msg_snapshot_ir(
        BytesIO(SOURCE),
        stream_info=INFO,
        snapshot=OutlookMsgConverterSnapshot(provider="fixture"),
    )
    assert _root(document).payload.text == "# Email Message\n\n\n## Content"
    assert document.metadata.title is None


def test_root_is_derived_and_h16_remains_native_authority() -> None:
    document = read_outlook_msg_snapshot_ir(
        BytesIO(SOURCE),
        stream_info=INFO,
        snapshot=SNAPSHOT,
    )
    node = _root(document)
    decision = capabilities_for_node(node).for_operation("replace_text")

    assert decision.state is CapabilityState.DERIVED
    assert decision.reason_code == "msg.output.not_native_writable"
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


def test_source_headers_and_body_are_independent_identity_authorities() -> None:
    baseline = read_outlook_msg_snapshot_ir(
        BytesIO(SOURCE), stream_info=INFO, snapshot=SNAPSHOT
    )
    changed_source = read_outlook_msg_snapshot_ir(
        BytesIO(SOURCE + b"x"), stream_info=INFO, snapshot=SNAPSHOT
    )
    changed_subject = read_outlook_msg_snapshot_ir(
        BytesIO(SOURCE),
        stream_info=INFO,
        snapshot=OutlookMsgConverterSnapshot(
            sender=SNAPSHOT.sender,
            recipients=SNAPSHOT.recipients,
            subject="Changed",
            body=SNAPSHOT.body,
            provider=SNAPSHOT.provider,
        ),
    )
    changed_body = read_outlook_msg_snapshot_ir(
        BytesIO(SOURCE),
        stream_info=INFO,
        snapshot=OutlookMsgConverterSnapshot(
            sender=SNAPSHOT.sender,
            recipients=SNAPSHOT.recipients,
            subject=SNAPSHOT.subject,
            body="Changed body",
            provider=SNAPSHOT.provider,
        ),
    )

    assert (
        len(
            {
                baseline.document_id,
                changed_source.document_id,
                changed_subject.document_id,
                changed_body.document_id,
            }
        )
        == 4
    )


def test_repeated_reads_and_canonical_round_trip_are_deterministic() -> None:
    first = read_outlook_msg_snapshot_ir(
        BytesIO(SOURCE), stream_info=INFO, snapshot=SNAPSHOT
    )
    second = read_outlook_msg_snapshot_ir(
        BytesIO(SOURCE), stream_info=INFO, snapshot=SNAPSHOT
    )

    assert canonical_json_digest(first) == canonical_json_digest(second)
    encoded = canonical_json_bytes(first)
    decoded = decode_document(encoded)
    assert canonical_json_bytes(decoded) == encoded


@pytest.mark.parametrize(
    ("info", "accepted_by"),
    (
        (StreamInfo(extension=".msg"), "extension"),
        (StreamInfo(extension=".MSG"), "extension"),
        (StreamInfo(mimetype="application/vnd.ms-outlook"), "mimetype"),
        (
            StreamInfo(mimetype="application/vnd.ms-outlook; x-test=1"),
            "mimetype",
        ),
    ),
)
def test_explicit_one_way_acceptance_surface(
    info: StreamInfo,
    accepted_by: str,
) -> None:
    document = read_outlook_msg_snapshot_ir(
        BytesIO(SOURCE),
        stream_info=info,
        snapshot=OutlookMsgConverterSnapshot(provider="fixture"),
    )
    evidence = document.metadata.custom["twoways.outlook_msg_converter_snapshot.v1"]
    assert evidence["accepted_by"] == accepted_by


@pytest.mark.parametrize(
    "info",
    (
        StreamInfo(),
        StreamInfo(extension=".eml"),
        StreamInfo(mimetype="message/rfc822"),
    ),
)
def test_outside_explicit_surface_fails_closed(info: StreamInfo) -> None:
    with pytest.raises(ValueError, match="OutlookMsgConverter"):
        read_outlook_msg_snapshot_ir(
            BytesIO(SOURCE),
            stream_info=info,
            snapshot=OutlookMsgConverterSnapshot(provider="fixture"),
        )
