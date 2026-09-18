from __future__ import annotations

import importlib


def test_h25_symbols_are_public_without_writer_exports() -> None:
    module = importlib.import_module("markitdown.twoways.readers.image")
    readers = importlib.import_module("markitdown.twoways.readers")
    tw = importlib.import_module("markitdown.twoways")

    names = (
        "ImageMetadataSnapshot",
        "ImageDescriptionSnapshot",
        "ImageDerivedLimits",
        "read_image_snapshot_ir",
    )
    for namespace in (module, readers, tw):
        for name in names:
            assert hasattr(namespace, name)

    for name in names:
        assert name in module.__all__
        assert name in readers.__all__
        assert name in tw.__all__

    for forbidden in (
        "patch_image_snapshot",
        "write_image_snapshot",
        "ImageSnapshotWriter",
        "ImageConverterWriter",
    ):
        assert not hasattr(module, forbidden)
        assert not hasattr(readers, forbidden)
        assert not hasattr(tw, forbidden)
