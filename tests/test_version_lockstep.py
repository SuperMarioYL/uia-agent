"""No future version bump can land half-done.

__version__ (src/uia_agent/__init__.py), pyproject.toml, web/site.json
meta.content_version and the CHANGELOG.md head must all agree — the portfolio's
most-repeated post-ship defect class is version drift (one surface bumped, the
others stale). Pure file reads, so it runs on the Linux no-deps CI leg too.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from uia_agent import __version__

ROOT = Path(__file__).resolve().parents[1]

LIVE_OWNER = "SuperMarioYL"
DEAD_OWNER = "supermario-leo"


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


# --- CHANGELOG.md: the head entry is a version surface too -------------------
#
# v0.9.0 bumped the heading but not its link reference, and the 0.1.0/0.2.0/0.3.0
# references still named the pre-rename owner (HTTP 404) — drift this file's
# docstring promised could not happen, because it never read CHANGELOG.md.


def _changelog_text() -> str:
    return (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")


def _changelog_headings(text: str) -> list[str]:
    return re.findall(r"^##\s*\[(\d+\.\d+\.\d+)\]", text, re.M)


def test_changelog_head_version_matches_package() -> None:
    headings = _changelog_headings(_changelog_text())
    assert headings, "no `## [x.y.z]` version heading in CHANGELOG.md"
    assert _norm(headings[0]) == _norm(__version__)


def test_every_changelog_heading_has_a_link_reference() -> None:
    text = _changelog_text()
    refs = set(re.findall(r"^\[(\d+\.\d+\.\d+)\]:", text, re.M))
    missing = [h for h in _changelog_headings(text) if h not in refs]
    assert not missing, f"CHANGELOG headings with no link reference: {missing}"


def test_changelog_link_references_use_the_live_owner() -> None:
    text = _changelog_text()
    urls = re.findall(r"^\[\d+\.\d+\.\d+\]:\s*(\S+)", text, re.M)
    assert urls, "no changelog link references found"
    # The entry prose may (and does) name the old owner when explaining this very
    # fix; the invariant is that every *link reference* resolves against the live
    # repo, since those are the URLs a reader actually clicks.
    dead = [u for u in urls if DEAD_OWNER in u]
    assert not dead, f"CHANGELOG link references still name the 404-ing owner: {dead}"
    for url in urls:
        assert url.startswith(f"https://github.com/{LIVE_OWNER}/uia-agent/"), url
