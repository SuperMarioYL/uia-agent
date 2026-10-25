"""Regression tests for the v0.10.0 shipped-artifact + metadata audit fixes.

Fix 1 (fix-demo-workflow-cli-deps): ``.github/workflows/demo.yml`` installed the
CLI with ``pip install --no-deps . typer pydantic``. pip's ``--no-deps`` is a
global flag, so it applied to every requirement on the line and stripped
``pydantic-core`` (pydantic's compiled backend) plus typer's
``annotated-doc``/``click``. ``uia-agent --help`` then died at import, and because
``vhs`` does not fail on a command's exit code the workflow still went green and
committed that traceback into ``assets/demo.gif`` — the headline image embedded in
both READMEs. ``--no-deps`` is now scoped to the project alone (its
``uiautomation``/``pywinauto`` pins are Windows-only and must not resolve on the
Linux runner); the CLI's cross-platform runtime deps install with their own deps.

Fix 2 (fix-pyproject-license-classifier): ``pyproject.toml`` declared the Trove
classifier ``License :: OSI Approved :: MIT License`` while the shipped ``LICENSE``
is Apache-2.0 and the ``license`` field already pointed at that file. The project
relicensed to Apache-2.0 during the v0.4.0-v0.6.0 window; the classifier was
missed, so PyPI/GitHub labelled the package MIT.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

_DEMO_WORKFLOW = ROOT / ".github" / "workflows" / "demo.yml"
_PYPROJECT = ROOT / "pyproject.toml"
_LICENSE = ROOT / "LICENSE"


# --- Fix 1: --no-deps may only ever cover the project itself -----------------


def test_demo_workflow_scopes_no_deps_to_the_project() -> None:
    """No ``pip install`` line in the demo workflow may apply ``--no-deps`` to a
    named distribution — those bring their own transitive deps, and stripping
    them makes the CLI unimportable (the v0.9.0 demo-GIF traceback)."""
    offenders: list[str] = []
    for line in _DEMO_WORKFLOW.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if "pip install" not in stripped or "--no-deps" not in stripped:
            continue
        for token in stripped.split("--no-deps", 1)[1].split():
            if token.startswith("-"):
                continue
            # A path / local directory / built artifact IS the project (or an
            # explicit file we chose to install bare); a bare distribution name
            # is a runtime dependency whose deps must be installed.
            if token in {".", ".."} or "/" in token or token.endswith(
                (".whl", ".tar.gz", ".tgz")
            ):
                continue
            offenders.append(token)
    assert not offenders, (
        "--no-deps in demo.yml would strip the CLI's own dependencies: "
        f"{offenders}"
    )


# --- Fix 2: the declared license classifier must match the shipped LICENSE ---


def test_pyproject_license_classifier_matches_shipped_license() -> None:
    """The Trove license classifier must agree with the shipped LICENSE text."""
    license_text = _LICENSE.read_text(encoding="utf-8")
    classifiers = tomllib.loads(_PYPROJECT.read_text(encoding="utf-8"))["project"]["classifiers"]
    license_classifiers = [c for c in classifiers if c.startswith("License ::")]
    assert license_classifiers, "pyproject declares no License classifier"

    if "Apache License" in license_text and "Version 2.0" in license_text:
        assert "License :: OSI Approved :: Apache Software License" in license_classifiers
        assert not any("MIT License" in c for c in license_classifiers), (
            "pyproject still declares an MIT classifier while LICENSE is Apache-2.0"
        )
