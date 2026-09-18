from __future__ import annotations

from io import BytesIO

import pytest

from markitdown.twoways.formats.msg import patch_msg, read_msg_ir
from markitdown.twoways.ir.edits import EditOperation

from ._msg_fixtures import PROPERTIES_STREAM, SUBJECT_STREAM, make_msg_cfb


def _subject_node(document):
    return next(
        node
        for node in document.nodes.values()
        if node.semantic_role == "msg-subject-text"
    )


def _candidate(source: bytes, value: str = "Bravo") -> bytes:
    document = read_msg_ir(BytesIO(source), filename="mail.msg")
    node = _subject_node(document)
    output = BytesIO()
    edit = EditOperation(
        operation_id="subject",
        type="update_msg_subject_text",
        target_node_id=node.node_id,
        payload={
            "property_tag": 0x0037001F,
            "old_value": node.payload.text,
            "value": value,
        },
    )
    patch_msg(document, BytesIO(source), output, edits=(edit,))
    return output.getvalue()


def test_olefile_confirms_subject_and_non_subject_stream_preservation() -> None:
    olefile = pytest.importorskip("olefile")
    source = make_msg_cfb(subject="Alpha").data
    candidate = _candidate(source)

    before = olefile.OleFileIO(BytesIO(source))
    after = olefile.OleFileIO(BytesIO(candidate))
    try:
        before_paths = before.listdir(streams=True, storages=False)
        after_paths = after.listdir(streams=True, storages=False)
        assert after_paths == before_paths

        assert (
            before.openstream(PROPERTIES_STREAM).read()
            == after.openstream(PROPERTIES_STREAM).read()
        )
        assert after.openstream(SUBJECT_STREAM).read() == "Bravo".encode("utf-16-le")

        for path in before_paths:
            if path == [SUBJECT_STREAM]:
                continue
            assert before.openstream(path).read() == after.openstream(path).read()
    finally:
        before.close()
        after.close()


def test_subject_physical_change_is_exactly_the_requested_utf16_bytes() -> None:
    fixture = make_msg_cfb(subject="Alpha")
    candidate = _candidate(fixture.data)
    document = read_msg_ir(BytesIO(fixture.data), filename="mail.msg")
    node = _subject_node(document)
    ranges = node.metadata["msg.subject_physical_ranges"]

    changed = bytearray()
    for item in ranges:
        start = item["start"]
        end = start + item["length"]
        changed.extend(candidate[start:end])

    assert bytes(changed) == "Bravo".encode("utf-16-le")
    assert len(candidate) == len(fixture.data)
