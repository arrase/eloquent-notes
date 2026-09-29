"""Version consistency checks.

The git tag, the pyproject version and the installed distribution metadata
must never drift apart. Historically they did: v0.2.9 shipped with
pyproject still declaring 0.2.8.
"""

import re
import subprocess
import tomllib
from pathlib import Path

import pytest

import eloquent_notes

REPO_ROOT = Path(__file__).resolve().parent.parent
PYPROJECT = REPO_ROOT / "pyproject.toml"
SEMVER = re.compile(r"^\d+\.\d+\.\d+$")


def _pyproject_version() -> str:
    with open(PYPROJECT, "rb") as f:
        return tomllib.load(f)["project"]["version"]


def _latest_release_tag() -> str | None:
    """Newest v* tag reachable from any local ref, or None if unavailable."""
    result = subprocess.run(
        ["git", "tag", "--list", "v*", "--sort=-v:refname"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return None
    tags = [t for t in result.stdout.split() if SEMVER.match(t[1:])]
    return tags[0] if tags else None


def test_pyproject_version_is_semver():
    assert SEMVER.match(_pyproject_version()), "pyproject version must be MAJOR.MINOR.PATCH"


def test_package_exposes_installed_version():
    assert eloquent_notes.__version__ != "0.0.0+unknown", (
        "package is not installed; version metadata is unavailable"
    )
    assert SEMVER.match(eloquent_notes.__version__)


def test_pyproject_matches_installed_metadata():
    assert _pyproject_version() == eloquent_notes.__version__


def test_latest_tag_matches_pyproject_version():
    """A release must be cut from a bumped pyproject, not before it."""
    tag = _latest_release_tag()
    if tag is None:
        pytest.skip("no version tags available in this checkout")
    assert tag == f"v{_pyproject_version()}", (
        f"latest tag {tag} does not match pyproject v{_pyproject_version()}"
    )
