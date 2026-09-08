from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys


def _clean_import_probe(statement: str) -> str:
    env = os.environ.copy()
    src = str(Path(__file__).parents[2] / "src")
    env["PYTHONPATH"] = src
    code = (
        "import sys\n"
        + statement
        + "\nprint(int('pptx' in sys.modules), int('lxml' in sys.modules))\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )
    return result.stdout.strip()


def test_root_two_way_import_does_not_load_pptx_dependencies():
    assert _clean_import_probe("import markitdown.twoways") == "0 0"


def test_pptx_format_import_is_also_lazy():
    assert _clean_import_probe("import markitdown.twoways.formats.pptx") == "0 0"


def test_pptx_options_are_frozen_and_have_safe_defaults():
    from markitdown.twoways.formats.pptx import PptxPatchOptions, PptxReadOptions

    read = PptxReadOptions()
    patch = PptxPatchOptions()

    assert read.include_notes is True
    assert read.include_resources is True
    assert read.preserve_unknown_native is True
    assert patch.strict is True
    assert patch.verify_output is True
    assert patch.preserve_zip_metadata is True
    assert read.limits.max_members == patch.limits.max_members


def test_pptx_public_surface_is_format_scoped():
    import markitdown.twoways.formats.pptx as pptx_api

    assert set(pptx_api.__all__) == {
        "PptxIRReader",
        "PptxPatchOptions",
        "PptxPatchWriter",
        "PptxReadOptions",
        "patch_pptx",
        "read_pptx_ir",
    }


def test_pptx_operation_reports_typed_missing_dependency(monkeypatch):
    from io import BytesIO

    import pytest

    from markitdown.twoways import MissingOptionalDependencyError
    from markitdown.twoways.formats.pptx import read_pptx_ir

    from ._pptx_fixtures import make_pptx_bytes

    source = make_pptx_bytes()
    monkeypatch.setitem(sys.modules, "pptx", None)
    with pytest.raises(MissingOptionalDependencyError) as exc:
        read_pptx_ir(BytesIO(source))
    assert exc.value.code == "two_way.missing_optional_dependency"
    assert exc.value.details["feature"] == "pptx"
