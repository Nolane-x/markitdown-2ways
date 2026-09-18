from __future__ import annotations

from dataclasses import replace
from io import BytesIO

import pytest

from markitdown.twoways._errors import PatchPreconditionError, UnsupportedEditError
from markitdown.twoways.capabilities import (
    CAPABILITY_METADATA_KEY,
    CapabilityDecision,
    CapabilityState,
    encode_capabilities,
)
from markitdown.twoways.formats.msg import MsgLimits, patch_msg, read_msg_ir
from markitdown.twoways.ir.edits import EditOperation

from ._msg_fixtures import PROPATTR_READABLE, make_msg_cfb


def _subject_node(document):
    return next(
        node
        for node in document.nodes.values()
        if node.semantic_role == "msg-subject-text"
    )


def _edit(document, *, node_id: str | None = None) -> EditOperation:
    node = document.nodes[node_id] if node_id is not None else _subject_node(document)
    return EditOperation(
        operation_id="edit-subject",
        type="update_msg_subject_text",
        target_node_id=node.node_id,
        payload={
            "property_tag": 0x0037001F,
            "old_value": node.payload.text,
            "value": "Bravo",
        },
    )


def _force_writable(document):
    node = _subject_node(document)
    writable = encode_capabilities(
        (
            CapabilityDecision(
                operation="update_msg_subject_text",
                state=CapabilityState.WRITABLE,
            ),
        )
    )
    forged_node = replace(
        node,
        metadata={**node.metadata, CAPABILITY_METADATA_KEY: writable},
    )
    return replace(
        document,
        nodes={**document.nodes, node.node_id: forged_node},
    )


@pytest.mark.parametrize(
    ("options", "message"),
    (
        ({"include_store_support": False}, "Unicode|authority|read-only"),
        ({"unicode_ok": False}, "Unicode|authority|read-only"),
        ({"subject_flags": PROPATTR_READABLE}, "writable|read-only"),
        ({"include_ansi_subject": True}, "Unicode|authority|read-only"),
        ({"include_subject_prefix": True}, "competing|semantic"),
        ({"include_normalized_subject": True}, "competing|semantic"),
        ({"subject_size_adjust": 2}, "size|read-only"),
    ),
)
def test_forged_writable_cannot_bypass_fresh_subject_authority(
    options: dict[str, object],
    message: str,
) -> None:
    source = make_msg_cfb(subject="Alpha", **options).data
    document = _force_writable(read_msg_ir(BytesIO(source), filename="mail.msg"))
    output = BytesIO()

    with pytest.raises(UnsupportedEditError, match=message):
        patch_msg(
            document,
            BytesIO(source),
            output,
            edits=(_edit(document),),
        )

    assert output.getvalue() == b""


@pytest.mark.parametrize(
    ("metadata_key", "forged_value"),
    (
        ("msg.property_tag", 0x0037001E),
        ("msg.property_entry_offset", 0),
        ("msg.property_entry_sha256", "0" * 64),
        ("msg.subject_directory_id", 0),
        ("msg.subject_directory_entry_sha256", "1" * 64),
        ("msg.subject_chain_kind", "fat"),
        ("msg.subject_chain", [999]),
        ("msg.subject_physical_ranges", [{"start": 0, "length": 10}]),
        ("msg.subject_stream_sha256", "2" * 64),
        ("msg.cfb_topology_sha256", "3" * 64),
    ),
)
def test_forged_native_evidence_fails_without_output(
    metadata_key: str,
    forged_value: object,
) -> None:
    source = make_msg_cfb(subject="Alpha").data
    document = read_msg_ir(BytesIO(source), filename="mail.msg")
    node = _subject_node(document)
    forged_node = replace(
        node,
        metadata={**node.metadata, metadata_key: forged_value},
    )
    forged = replace(
        document,
        nodes={**document.nodes, node.node_id: forged_node},
    )
    output = BytesIO()

    with pytest.raises(PatchPreconditionError, match="stale|forged|locator|binding|owner"):
        patch_msg(
            forged,
            BytesIO(source),
            output,
            edits=(_edit(forged, node_id=node.node_id),),
        )

    assert output.getvalue() == b""


def test_forged_payload_text_fails_without_output() -> None:
    source = make_msg_cfb(subject="Alpha").data
    document = read_msg_ir(BytesIO(source), filename="mail.msg")
    node = _subject_node(document)
    forged_node = replace(node, payload=replace(node.payload, text="Omega"))
    forged = replace(
        document,
        nodes={**document.nodes, node.node_id: forged_node},
    )
    output = BytesIO()

    with pytest.raises(PatchPreconditionError, match="stale|semantic|owner"):
        patch_msg(
            forged,
            BytesIO(source),
            output,
            edits=(_edit(forged, node_id=node.node_id),),
        )

    assert output.getvalue() == b""


def test_forged_locator_object_id_fails_without_output() -> None:
    source = make_msg_cfb(subject="Alpha").data
    document = read_msg_ir(BytesIO(source), filename="mail.msg")
    node = _subject_node(document)
    assert node.native_locator is not None
    forged_node = replace(
        node,
        native_locator=replace(node.native_locator, object_id="mapi:0037001E"),
    )
    forged = replace(
        document,
        nodes={**document.nodes, node.node_id: forged_node},
    )
    output = BytesIO()

    with pytest.raises(PatchPreconditionError, match="locator|binding|stale"):
        patch_msg(
            forged,
            BytesIO(source),
            output,
            edits=(_edit(forged, node_id=node.node_id),),
        )

    assert output.getvalue() == b""


def test_forged_persisted_read_limits_fail_without_output() -> None:
    source = make_msg_cfb(subject="Alpha").data
    limits = MsgLimits(
        max_source_bytes=len(source),
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
        BytesIO(source),
        filename="mail.msg",
        limits=limits,
    )
    custom = dict(document.metadata.custom)
    forged_limits = dict(custom["msg.read_limits.v1"])
    forged_limits["max_chain_sectors"] = 999
    custom["msg.read_limits.v1"] = forged_limits
    forged = replace(
        document,
        metadata=replace(document.metadata, custom=custom),
    )
    output = BytesIO()

    with pytest.raises(PatchPreconditionError, match="read.*limit|stale|forged"):
        patch_msg(
            forged,
            BytesIO(source),
            output,
            edits=(_edit(forged),),
        )

    assert output.getvalue() == b""


def test_caller_cannot_widen_read_time_source_budget() -> None:
    source = make_msg_cfb(subject="Alpha").data
    read_limits = MsgLimits(max_source_bytes=len(source))
    document = read_msg_ir(
        BytesIO(source),
        filename="mail.msg",
        limits=read_limits,
    )
    output = BytesIO()
    requested = MsgLimits(max_source_bytes=len(source) * 2)

    patch_msg(
        document,
        BytesIO(source),
        output,
        edits=(_edit(document),),
        limits=requested,
    )

    assert len(output.getvalue()) == len(source)


def test_tighter_caller_source_budget_fails_without_output() -> None:
    source = make_msg_cfb(subject="Alpha").data
    document = read_msg_ir(BytesIO(source), filename="mail.msg")
    output = BytesIO()
    tighter = MsgLimits(max_source_bytes=len(source) - 1)

    with pytest.raises(PatchPreconditionError, match="structure|limit|source"):
        patch_msg(
            document,
            BytesIO(source),
            output,
            edits=(_edit(document),),
            limits=tighter,
        )

    assert output.getvalue() == b""
