from __future__ import annotations

from io import BytesIO

from markitdown._stream_info import StreamInfo
from markitdown.twoways.formats.msg import MsgIRReader

from ._msg_fixtures import make_msg_cfb


def test_msg_reader_adapter_accepts_extension_and_mimetype() -> None:
    reader = MsgIRReader()
    source = BytesIO(make_msg_cfb().data)

    assert reader.accepts(source, StreamInfo(extension=".msg")) is True
    assert (
        reader.accepts(
            source,
            StreamInfo(mimetype="application/vnd.ms-outlook"),
        )
        is True
    )
    assert reader.accepts(source, StreamInfo(extension=".eml")) is False
    assert reader.accepts(source, StreamInfo(mimetype="message/rfc822")) is False


def test_msg_reader_adapter_builds_native_subject_ir() -> None:
    source = make_msg_cfb(subject="Alpha").data
    reader = MsgIRReader()
    stream_info = StreamInfo(
        filename="mail.msg",
        extension=".msg",
        mimetype="application/vnd.ms-outlook",
    )

    document = reader.read(BytesIO(source), stream_info)

    assert document.source is not None
    assert document.source.format == "msg"
    assert document.source.filename == "mail.msg"
    assert document.source.mimetype == "application/vnd.ms-outlook"
    assert [node.semantic_role for node in document.nodes.values()] == [
        "msg-subject-text"
    ]
