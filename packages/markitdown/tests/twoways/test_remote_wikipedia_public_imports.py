from __future__ import annotations

import importlib


def test_h18_remote_reader_symbols_are_public_without_writer_exports() -> None:
    readers = importlib.import_module("markitdown.twoways.readers")
    tw = importlib.import_module("markitdown.twoways")

    for module in (readers, tw):
        assert hasattr(module, "RemoteDerivedLimits")
        assert hasattr(module, "read_wikipedia_snapshot_ir")
        assert "RemoteDerivedLimits" in module.__all__
        assert "read_wikipedia_snapshot_ir" in module.__all__

    for forbidden in (
        "patch_wikipedia",
        "write_remote",
        "RemoteWriter",
        "WikipediaWriter",
    ):
        assert not hasattr(readers, forbidden)
        assert not hasattr(tw, forbidden)
