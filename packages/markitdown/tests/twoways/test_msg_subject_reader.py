from __future__ import annotations

from io import BytesIO

from markitdown.twoways.capabilities import CapabilityState, capabilities_for_node
from markitdown.twoways.formats.msg import MsgLimits, read_msg_ir
from markitdown.twoways.ir.nodes import TextPayload
from markitdown.twoways.ir.serialization import canonical_json_digest, validate_document

from ._msg_fixtures import PROPATTR_READABLE, make_msg_cfb


def _subject_node(document):
    return next(
        node
        for node in document.nodes.values()
        if node.semantic_role == "msg-subject-text"
    )


def test_reads_subject_into_deterministic_ir() -> None:
    source = make_msg_cfb(subject="Alpha").data

    first = read_msg_ir(
        BytesIO(source),
        filename="mail.msg",
        mimetype="application/vnd.ms-outlook",
    )
    second = read_msg_ir(
        BytesIO(source),
        filename="mail.msg",
        mimetype="application/vnd.ms-outlook",
    )

    validate_document(first)
    assert canonical_json_digest(first) == canonical_json_digest(second)
    assert first.source is not None
    assert first.source.format == "msg"
    assert first.source.filename == "mail.msg"
    assert first.source.mimetype == "application/vnd.ms-outlook"
    assert first.source.sha256 is not None
    assert first.source.size_bytes == len(source)
    assert first.source.preserved_source_ref == f"msg:sha256:{first.source.sha256}"
    assert len(first.canvases) == 1
    assert first.canvases[0].kind == "message"

    node = _subject_node(first)
    assert isinstance(node.payload, TextPayload)
    assert node.payload.text == "Alpha"
    assert node.native_locator is not None
    assert node.native_locator.backend == "msg"
    assert node.native_locator.part_uri == "/"
    assert node.native_locator.object_id == "mapi:0037001F"
    assert node.metadata["msg.property_id"] == 0x0037
    assert node.metadata["msg.property_type"] == 0x001F
    assert node.metadata["msg.property_tag"] == 0x0037001F
    assert node.metadata["msg.property_name"] == "PidTagSubject"
    assert node.metadata["msg.stream_name"] == "__substg1.0_0037001F"
    assert node.metadata["msg.property_stream_name"] == "__properties_version1.0"
    assert isinstance(node.metadata["msg.property_entry_index"], int)
    assert isinstance(node.metadata["msg.property_entry_offset"], int)
    assert len(node.metadata["msg.property_entry_sha256"]) == 64
    assert node.metadata["msg.declared_size"] == len("Alpha".encode("utf-16-le")) + 2
    assert node.metadata["msg.subject_stream_size"] == len("Alpha".encode("utf-16-le"))
    assert len(node.metadata["msg.subject_stream_sha256"]) == 64
    assert isinstance(node.metadata["msg.subject_directory_id"], int)
    assert len(node.metadata["msg.subject_directory_entry_sha256"]) == 64
    assert node.metadata["msg.subject_chain_kind"] == "mini"
    assert isinstance(node.metadata["msg.subject_chain"], list)
    assert isinstance(node.metadata["msg.subject_physical_ranges"], list)
    assert node.metadata["msg.encoding"] == "utf-16-le"
    assert isinstance(first.metadata.custom["msg.cfb_topology_sha256"], str)
    assert len(first.metadata.custom["msg.cfb_topology_sha256"]) == 64


def test_safe_subject_advertises_exact_size_mutation() -> None:
    document = read_msg_ir(BytesIO(make_msg_cfb().data), filename="mail.msg")
    decision = capabilities_for_node(_subject_node(document)).for_operation(
        "update_msg_subject_text"
    )

    assert decision.state is CapabilityState.WRITABLE
    assert decision.reason_code is None
    assert decision.constraints == {
        "identity_markdown": False,
        "existing_owner_only": True,
        "fixed_allocation": True,
        "exact_encoded_length": True,
        "encoding": "utf-16-le",
        "source_preservation": "msg-exact-outside-subject-ranges",
        "property_identity_immutable": True,
        "cfb_topology_immutable": True,
    }


def test_competing_authority_is_read_only() -> None:
    cases = (
        ({"include_store_support": False}, "msg.subject.ansi_read_only"),
        (
            {"subject_flags": PROPATTR_READABLE},
            "msg.subject.property_not_writable",
        ),
        (
            {"include_subject_prefix": True},
            "msg.subject.competing_semantics",
        ),
        (
            {"include_normalized_subject": True},
            "msg.subject.competing_semantics",
        ),
        ({"subject_size_adjust": 2}, "msg.subject.size_mismatch"),
    )

    for options, reason in cases:
        document = read_msg_ir(BytesIO(make_msg_cfb(**options).data), filename="mail.msg")
        node = _subject_node(document)
        decision = capabilities_for_node(node).for_operation("update_msg_subject_text")
        assert decision.state is CapabilityState.READ_ONLY
        assert decision.reason_code == reason


def test_read_time_limits_are_persisted_with_fingerprint() -> None:
    limits = MsgLimits(
        max_source_bytes=1024 * 1024,
        max_difat_sectors=32,
        max_fat_sectors=64,
        max_chain_sectors=128,
        max_directory_entries=256,
        max_minifat_sectors=64,
        max_property_entries=32,
        max_stream_bytes=128 * 1024,
        max_subject_bytes=4096,
        max_total_owned_stream_bytes=256 * 1024,
    )

    document = read_msg_ir(
        BytesIO(make_msg_cfb().data),
        filename="mail.msg",
        limits=limits,
    )

    assert document.metadata.custom["msg.read_limits.v1"] == {
        "max_source_bytes": limits.max_source_bytes,
        "max_difat_sectors": limits.max_difat_sectors,
        "max_fat_sectors": limits.max_fat_sectors,
        "max_chain_sectors": limits.max_chain_sectors,
        "max_directory_entries": limits.max_directory_entries,
        "max_minifat_sectors": limits.max_minifat_sectors,
        "max_property_entries": limits.max_property_entries,
        "max_stream_bytes": limits.max_stream_bytes,
        "max_subject_bytes": limits.max_subject_bytes,
        "max_total_owned_stream_bytes": limits.max_total_owned_stream_bytes,
    }
    fingerprint = document.metadata.custom["msg.read_limits.sha256"]
    assert isinstance(fingerprint, str)
    assert len(fingerprint) == 64
