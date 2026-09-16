from markitdown.twoways.formats.csv import (
    CsvIRReader,
    CsvPatchWriter,
    patch_csv,
    read_csv_ir,
)


def test_csv_adapter_public_imports_are_stable() -> None:
    assert CsvIRReader.__name__ == "CsvIRReader"
    assert CsvPatchWriter.__name__ == "CsvPatchWriter"
    assert callable(read_csv_ir)
    assert callable(patch_csv)
