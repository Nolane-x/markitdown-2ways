from markitdown.twoways.formats.text import (
    TextIRReader,
    TextPatchWriter,
    TextRepresentation,
    decode_text_source,
    encode_text_source,
    normalize_newlines,
    patch_text,
    read_text_ir,
)


def test_text_adapter_public_imports_are_stable() -> None:
    assert TextIRReader.__name__ == "TextIRReader"
    assert TextPatchWriter.__name__ == "TextPatchWriter"
    assert TextRepresentation.__name__ == "TextRepresentation"
    assert callable(decode_text_source)
    assert callable(encode_text_source)
    assert callable(normalize_newlines)
    assert callable(read_text_ir)
    assert callable(patch_text)
