"""No future version bump can land half-done.

__version__ (src/uia_agent/__init__.py), pyproject.toml and web/site.json
meta.content_version must all agree — the portfolio's most-repeated post-ship
defect class is version drift (one surface bumped, the others stale). Pure
file reads, so it runs on the Linux no-deps CI leg too.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from uia_agent import __version__

ROOT = Path(__file__).resolve().parents[1]


def _norm(version: str) -> str:
    return version.strip().lstrip("v")


def test_pyproject_version_matches_package() -> None:
    match = re.search(
        r'^version\s*=\s*"([^"]+)"',
        (ROOT / "pyproject.toml").read_text(encoding="utf-8"),
        re.M,
    )
    assert match, "no version field in pyproject.toml"
    assert _norm(match.group(1)) == _norm(__version__)


def test_site_json_content_version_matches_package() -> None:
    site = ROOT / "web" / "site.json"
    if not site.exists():
        pytest.skip("no web/site.json in this checkout")
    # site.json contains UTF-8 Chinese copy — an unencoded read_text() decodes
    # with the Windows locale codepage (cp1252) and blows up on the runner.
    data = json.loads(site.read_text(encoding="utf-8"))
    # site.json carries the version twice (meta.content_version and a
    # top-level content_version); both must agree with the package.
    meta = data.get("meta") or {}
    assert _norm(str(meta.get("content_version", ""))) == _norm(__version__)
    assert _norm(str(data.get("content_version", ""))) == _norm(__version__)
