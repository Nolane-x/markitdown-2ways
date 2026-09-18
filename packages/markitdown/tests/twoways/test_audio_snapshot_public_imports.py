from __future__ import annotations

import importlib


def test_h24_symbols_are_public_without_writer_exports() -> None:
    module = importlib.import_module("markitdown.twoways.readers.audio")
    readers = importlib.import_module("markitdown.twoways.readers")
    tw = importlib.import_module("markitdown.twoways")

    for namespace in (module, readers, tw):
        assert hasattr(namespace, "AudioConverterSnapshot")
        assert hasattr(namespace, "AudioDerivedLimits")
        assert hasattr(namespace, "read_audio_snapshot_ir")

    assert "AudioConverterSnapshot" in module.__all__
    assert "AudioDerivedLimits" in module.__all__
    assert "read_audio_snapshot_ir" in module.__all__

    for namespace in (readers, tw):
        assert "AudioConverterSnapshot" in namespace.__all__
        assert "AudioDerivedLimits" in namespace.__all__
        assert "read_audio_snapshot_ir" in namespace.__all__

    for forbidden in (
        "patch_audio_snapshot",
        "write_audio_snapshot",
        "AudioSnapshotWriter",
        "AudioConverterWriter",
    ):
        assert not hasattr(module, forbidden)
        assert not hasattr(readers, forbidden)
        assert not hasattr(tw, forbidden)
