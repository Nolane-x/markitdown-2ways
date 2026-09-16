from markitdown.twoways.formats.json import (
    JsonIRReader,
    JsonPatchWriter,
    patch_json,
    read_json_ir,
)


def test_json_adapter_public_imports_are_stable() -> None:
    assert JsonIRReader.__name__ == "JsonIRReader"
    assert JsonPatchWriter.__name__ == "JsonPatchWriter"
    assert callable(read_json_ir)
    assert callable(patch_json)
