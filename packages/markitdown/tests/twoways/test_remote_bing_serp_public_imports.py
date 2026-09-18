from __future__ import annotations

import importlib


def test_h19_bing_reader_symbol_is_public_without_writer_exports() -> None:
    remote = importlib.import_module("markitdown.twoways.readers.remote")
    readers = importlib.import_module("markitdown.twoways.readers")
    tw = importlib.import_module("markitdown.twoways")

    for module in (remote, readers, tw):
        assert hasattr(module, "read_bing_serp_snapshot_ir")
        assert "read_bing_serp_snapshot_ir" in module.__all__

    for forbidden in (
        "patch_bing",
        "write_bing",
        "write_remote",
        "BingWriter",
        "RemoteWriter",
    ):
        assert not hasattr(remote, forbidden)
        assert not hasattr(readers, forbidden)
        assert not hasattr(tw, forbidden)
