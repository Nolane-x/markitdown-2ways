from __future__ import annotations

import importlib


def test_h26_symbols_are_public_without_writer_exports() -> None:
    module = importlib.import_module("markitdown.twoways.readers.outlook_msg")
    readers = importlib.import_module("markitdown.twoways.readers")
    tw = importlib.import_module("markitdown.twoways")

    names = (
        "OutlookMsgConverterSnapshot",
        "OutlookMsgDerivedLimits",
        "read_outlook_msg_snapshot_ir",
    )
    for namespace in (module, readers, tw):
        for name in names:
            assert hasattr(namespace, name)
            assert name in namespace.__all__

    for forbidden in (
        "patch_outlook_msg_snapshot",
        "write_outlook_msg_snapshot",
        "OutlookMsgSnapshotWriter",
    ):
        assert not hasattr(module, forbidden)
        assert not hasattr(readers, forbidden)
        assert not hasattr(tw, forbidden)
