from __future__ import annotations


def test_mp3_public_reader_contract_imports() -> None:
    from markitdown.twoways.formats.mp3 import (
        Mp3FormatError,
        Mp3IRReader,
        Mp3Limits,
        parse_mp3,
        read_mp3_ir,
    )

    assert Mp3FormatError is not None
    assert Mp3IRReader is not None
    assert Mp3Limits is not None
    assert callable(parse_mp3)
    assert callable(read_mp3_ir)
