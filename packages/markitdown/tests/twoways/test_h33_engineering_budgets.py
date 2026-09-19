from __future__ import annotations

import json
from pathlib import Path
import re

import markitdown.twoways as tw


_REPO_ROOT = Path(__file__).resolve().parents[4]
_BUDGET_PATH = _REPO_ROOT / "docs" / "twoways-v1-engineering-budgets.json"
_CONTRACT_PATH = _REPO_ROOT / "docs" / "twoways-v1-contract.json"
_PYPROJECT_PATH = _REPO_ROOT / "packages" / "markitdown" / "pyproject.toml"
_TWOWAYS_SRC = _REPO_ROOT / "packages" / "markitdown" / "src" / "markitdown" / "twoways"


def _load(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _production_python_files() -> list[Path]:
    return sorted(path for path in _TWOWAYS_SRC.rglob("*.py") if path.is_file())


def _core_dependencies() -> list[str]:
    text = _PYPROJECT_PATH.read_text(encoding="utf-8")
    block = text.split("dependencies = [", 1)[1].split("]", 1)[0]
    return sorted(re.findall(r'^\s*"([^"]+)"', block, flags=re.MULTILINE))


def test_h33_production_size_stays_inside_v1_budget() -> None:
    budget = _load(_BUDGET_PATH)
    ceilings = budget["ceilings"]
    assert isinstance(ceilings, dict)

    files = _production_python_files()
    sizes = [path.stat().st_size for path in files]

    assert len(files) <= ceilings["production_python_files"]
    assert sum(sizes) <= ceilings["production_source_bytes"]
    assert max(sizes, default=0) <= ceilings["largest_production_file_bytes"]


def test_h33_budget_is_tied_to_a_recorded_baseline() -> None:
    budget = _load(_BUDGET_PATH)
    baseline = budget["baseline"]
    ceilings = budget["ceilings"]
    assert isinstance(baseline, dict)
    assert isinstance(ceilings, dict)

    assert baseline["production_python_files"] == 200
    assert baseline["production_source_bytes"] == 1547539
    assert baseline["largest_production_file_bytes"] == 37389
    assert baseline["production_python_files"] <= ceilings["production_python_files"]
    assert baseline["production_source_bytes"] <= ceilings["production_source_bytes"]
    assert (
        baseline["largest_production_file_bytes"]
        <= ceilings["largest_production_file_bytes"]
    )


def test_h33_v1_surface_cardinality_stays_bounded() -> None:
    budget = _load(_BUDGET_PATH)
    contract = _load(_CONTRACT_PATH)
    ceilings = budget["ceilings"]
    assert isinstance(ceilings, dict)

    assert len(tw.__all__) == ceilings["public_root_symbols"]
    assert len(contract["native_support"]) == ceilings["native_support_rows"]
    assert len(contract["derived_support"]) == ceilings["derived_support_rows"]


def test_h33_core_dependency_budget_prevents_silent_bloat() -> None:
    budget = _load(_BUDGET_PATH)
    expected = budget["core_dependencies"]
    assert isinstance(expected, list)

    assert _core_dependencies() == expected


def test_h33_required_ci_uses_deterministic_budgets() -> None:
    budget = _load(_BUDGET_PATH)
    policy = budget["policy"]
    assert isinstance(policy, dict)

    assert policy["timing_thresholds"] == "forbidden-in-required-ci"
    assert policy["new-core-dependency"] == "requires-intentional-budget-update"
    assert policy["budget-growth"] == "requires-design-record-and-regression-court"
