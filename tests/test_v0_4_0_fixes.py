"""Regression tests for the v0.4.0 source-audit fixes.

Fix 1 (fix-pyproject-urls-wrong-owner): the ``[project.urls]`` in
``pyproject.toml`` must point at the live ``SuperMarioYL/uia-agent`` repo. The
shipped v0.3.0 metadata pointed at ``supermario-leo/uia-agent``, which 404s —
so PyPI's Homepage/Repository/Issues links were dead and a user who hit a
defect could not reach the issue tracker through the package metadata.

Fix 2 (fix-vision-tesseract-binary-crash): the ``[vision]`` extra installs the
``pytesseract`` *binding* but NOT the native Tesseract binary. When that binary
is absent, ``pytesseract.image_to_data`` raises
``TesseractNotFoundError`` (an ``EnvironmentError``). The v0.3.0
``TesseractEngine.regions`` left that call unguarded, so ``--vision`` runs
crashed with an opaque error instead of degrading to the normal LLM step. The
call is now wrapped so the vision path returns ``[]`` (logged, never silent),
the caller's ``fallback_regions`` / ``_vision_fallback_event`` return ``None``,
and ``run()`` falls through to the LLM step.
"""

from __future__ import annotations

import sys
import tomllib
import types
from pathlib import Path

# Use the real exception class the bug is about when the binding is installed;
# fall back to a faithful stand-in (same base class) when it is not.
try:  # pragma: no cover - depends on whether the [vision] extra is installed
    from pytesseract.pytesseract import TesseractNotFoundError
except ImportError:  # pragma: no cover - real pytesseract binding not installed
    class TesseractNotFoundError(EnvironmentError):
        """Stand-in mirroring pytesseract's binary-missing error."""

_PYPROJECT = Path(__file__).resolve().parent.parent / "pyproject.toml"

LIVE_REPO = "https://github.com/SuperMarioYL/uia-agent"
LIVE_ISSUES = "https://github.com/SuperMarioYL/uia-agent/issues"
DEAD_OWNER = "supermario-leo"


# --- Fix 1: pyproject URLs + version point at the live repo -----------------


def test_pyproject_version_is_current() -> None:
    with _PYPROJECT.open("rb") as fh:
        data = tomllib.load(fh)
    # v0.4.0 bumped the stale 0.3.0 metadata; each subsequent release keeps it
    # current — v0.8.0 ships two contract-gap guards (vision click + key SendKeys).
    assert data["project"]["version"] == "0.8.0"


def test_pyproject_urls_resolve_to_live_repo() -> None:
    with _PYPROJECT.open("rb") as fh:
        data = tomllib.load(fh)
    urls = data["project"]["urls"]
    assert urls["Homepage"] == LIVE_REPO
    assert urls["Repository"] == LIVE_REPO
    assert urls["Issues"] == LIVE_ISSUES


def test_pyproject_has_no_dead_owner() -> None:
    # No trace of the 404-ing owner anywhere in the package metadata.
    assert DEAD_OWNER not in _PYPROJECT.read_text()


# --- Fix 2: tesseract binary-missing degrades instead of crashing ------------


def _fake_pytesseract() -> types.ModuleType:
    """A ``pytesseract`` stand-in: the import succeeds (binding present) but the
    native binary is absent, so ``image_to_data`` raises
    ``TesseractNotFoundError``. Injecting it via ``sys.modules`` makes the test
    independent of whether the real binding — or the native Tesseract binary —
    is installed on the host."""
    mod = types.ModuleType("pytesseract")
    inner = types.ModuleType("pytesseract.pytesseract")
    inner.TesseractNotFoundError = TesseractNotFoundError
    mod.pytesseract = inner

    class _Output:
        DICT = "dict"

    mod.Output = _Output

    def _image_to_data(*_args, **_kwargs):
        # Real pytesseract raises TesseractNotFoundError() with no message when
        # the native binary is missing (see pytesseract.pytesseract); mirror
        # that exactly so the test reproduces the genuine failure mode.
        raise TesseractNotFoundError()

    mod.image_to_data = _image_to_data
    return mod


def test_tesseract_binary_missing_regions_returns_empty(monkeypatch) -> None:
    """``image_to_data`` raising the binary-missing error must degrade to ``[]``
    (and NOT raise) so the caller's vision fallback returns ``None`` and the
    run loop falls through to the LLM step."""
    monkeypatch.setitem(sys.modules, "pytesseract", _fake_pytesseract())

    from uia_agent.vision import TesseractEngine

    result = TesseractEngine().regions(image=object())
    assert result == []


def test_vision_binary_missing_degrades_to_llm_step(monkeypatch) -> None:
    """End-to-end regression for the reported crash: a ``--vision`` run on a dead
    tree, with the Tesseract binary absent, must NOT crash. It must fall through
    to the LLM step (no OCR coordinate click) and emit the LLM's ``done`` action
    — instead of the v0.3.0 opaque CLI crash."""
    monkeypatch.setitem(sys.modules, "pytesseract", _fake_pytesseract())

    import uia_agent.actions as actions_mod
    from uia_agent import agent
    from uia_agent.uia_tree import UIANode
    from uia_agent.vision import tree_has_actionable_nodes

    clicked: list[tuple[int, int]] = []

    def _fake_click_point(x: int, y: int) -> actions_mod.ActionResult:
        clicked.append((x, y))
        return actions_mod.ActionResult(ok=True, detail=f"clicked ({x}, {y})")

    monkeypatch.setattr(agent, "click_point", _fake_click_point)

    dead_tree = UIANode(
        id="root",
        role="Window",
        name="Legacy",
        bbox=(0, 0, 800, 600),
        children=[
            UIANode(
                id="canvas",
                role="Pane",
                name="render surface",
                enabled=True,
                bbox=(0, 0, 800, 600),
                patterns=[],
            )
        ],
    )
    assert tree_has_actionable_nodes(dead_tree) is False

    class _DoneLLM:
        def __init__(self) -> None:
            self.calls = 0

        def next_action(self, *, system: str, user: str):
            from uia_agent.actions import Action

            self.calls += 1
            return Action(kind="done", reason="OCR unavailable; giving up")

    llm = _DoneLLM()

    events = list(
        agent.run(
            "Legacy",
            "click submit",
            max_steps=3,
            llm=llm,
            snapshotter=lambda _app: dead_tree,
            settle_seconds=0.0,
            vision=True,
            ocr=None,  # default TesseractEngine -> consults the fake pytesseract
            screenshotter=lambda _app: object(),
        )
    )

    assert clicked == [], "no OCR coordinate click when the binary is missing"
    assert llm.calls >= 1, "run must fall through to the LLM step on OCR failure"
    assert events[-1].action.kind == "done"
