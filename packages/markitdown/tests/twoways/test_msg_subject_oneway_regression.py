from __future__ import annotations

from io import BytesIO
from pathlib import Path

import pytest

from markitdown import MarkItDown
from markitdown._stream_info import StreamInfo
from markitdown.converters._outlook_msg_converter import OutlookMsgConverter
from markitdown.twoways.formats.msg import MsgPatchWriter, read_msg_ir
from markitdown.twoways.writers.base import TargetInfo

from ._msg_fixtures import make_msg_cfb


def test_h16_does_not_change_one_way_msg_acceptance() -> None:
    converter = OutlookMsgConverter()
    source = BytesIO(make_msg_cfb().data)
    stream_info = StreamInfo(
        filename="mail.msg",
        extension=".msg",
        mimetype="application/vnd.ms-outlook",
    )

    assert converter.accepts(source, stream_info) is True


def test_native_msg_writer_routes_without_one_way_conversion() -> None:
    source = make_msg_cfb().data
    document = read_msg_ir(BytesIO(source), filename="mail.msg")
    writer = MsgPatchWriter()

    assert writer.accepts(
        document,
        TargetInfo(
            format="msg",
            extension=".msg",
            mimetype="application/vnd.ms-outlook",
        ),
    )


def test_real_msg_fixture_still_converts_through_one_way_path() -> None:
    pytest.importorskip("olefile")
    fixture = Path(__file__).parents[1] / "test_files" / "test_outlook_msg.msg"

    result = MarkItDown().convert(fixture)

    assert "**From:** test.sender@example.com" in result.markdown
    assert "**Subject:** Test Email Message" in result.markdown
    assert "This is the body of the test email message" in result.markdown
