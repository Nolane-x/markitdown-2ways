from __future__ import annotations

from pathlib import Path
import re

from markitdown.__about__ import __version__


_REPO_ROOT = Path(__file__).resolve().parents[4]
_README = _REPO_ROOT / 'README.md'
_PACKAGE = _REPO_ROOT / 'packages' / 'markitdown' / 'pyproject.toml'
_NOTES = _REPO_ROOT / 'docs' / 'releases' / '2ways-v1.0.0.md'
_WORKFLOW = _REPO_ROOT / '.github' / 'workflows' / 'release-v1.yml'


def test_v1_release_version_is_exact() -> None:
    assert __version__ == '1.0.0'


def test_v1_release_metadata_targets_this_fork() -> None:
    pyproject = _PACKAGE.read_text(encoding='utf-8')
    assert "Development Status :: 5 - Production/Stable" in pyproject
    assert 'https://github.com/Nolane-x/markitdown-2ways' in pyproject
    assert 'round-trip' in pyproject
    assert 'document-ir' in pyproject


def test_v1_readme_is_a_2ways_landing_page() -> None:
    readme = _README.read_text(encoding='utf-8')
    assert readme.startswith('# MarkItDown 2Ways')
    assert 'native document -> DocumentIR -> Markdown / typed edits -> native document' in readme
    assert 'H31 — Adversarial capability hardening' in readme
    assert 'H32 — v1 compatibility corpus' in readme
    assert 'H33 — deterministic engineering budgets' in readme
    assert 'microsoft/markitdown' in readme


def test_v1_release_notes_and_workflow_are_bound_to_one_tag() -> None:
    notes = _NOTES.read_text(encoding='utf-8')
    workflow = _WORKFLOW.read_text(encoding='utf-8')
    assert notes.startswith('# MarkItDown 2Ways v1.0.0')
    assert workflow.count('gh release create 2ways-v1.0.0') == 1
    assert '--target' in workflow
    assert 'dist/*' in workflow


def test_v1_core_dependency_count_did_not_expand_during_release() -> None:
    pyproject = _PACKAGE.read_text(encoding='utf-8')
    block = pyproject.split('dependencies = [', 1)[1].split(']', 1)[0]
    dependencies = re.findall(r'^\s*"([^"]+)"', block, flags=re.MULTILINE)
    assert len(dependencies) == 6
