from __future__ import annotations


def test_msg_public_reader_contract_imports() -> None:
    from markitdown.twoways.formats.msg import (
        MsgFormatError,
        MsgIRReader,
        MsgLimits,
        parse_cfb,
        parse_msg,
        read_msg_ir,
    )

    assert MsgFormatError is not None
    assert MsgIRReader is not None
    assert MsgLimits is not None
    assert callable(parse_cfb)
    assert callable(parse_msg)
    assert callable(read_msg_ir)
