"""OCR + bbox vision fallback (m5).

Proves the contract:
  - on a synthetic zero-actionable-node tree, the agent loop enters the OCR
    path and emits a coordinate-targeted click;
  - on a normal UIA-rich tree, vision is never consulted.

The OCR engine and the click dispatch are stubbed so the test needs no
Tesseract binary and no live Windows session.
"""

from __future__ import annotations

import uia_agent.actions as actions_mod
from uia_agent import agent
from uia_agent.uia_tree import UIANode
from uia_agent.vision import TextRegion, tree_has_actionable_nodes


class _StubOCR:
    """OCR engine that returns fixed regions regardless of the image."""

    def __init__(self, regions: list[TextRegion]) -> None:
        self._regions = regions
        self.calls = 0

    def regions(self, image: object) -> list[TextRegion]:
        self.calls += 1
        return self._regions


def _actionable_tree() -> UIANode:
    return UIANode(
        id="root",
        role="Window",
        name="App",
        bbox=(0, 0, 800, 600),
        children=[
            UIANode(
                id="ok",
                role="Button",
                name="OK",
                enabled=True,
                bbox=(10, 10, 110, 40),
                patterns=["Invoke"],
            )
        ],
    )


def _dead_tree() -> UIANode:
    # An owner-drawn pane: present, but exposes no actionable patterns.
    return UIANode(
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


def test_tree_has_actionable_nodes_detects_both_cases() -> None:
    assert tree_has_actionable_nodes(_actionable_tree()) is True
    assert tree_has_actionable_nodes(_dead_tree()) is False


def test_text_region_center_is_bbox_midpoint() -> None:
    region = TextRegion(text="Save", bbox=(100, 200, 200, 240), confidence=0.9)
    assert region.center == (150, 220)


def test_dead_tree_triggers_ocr_and_emits_coordinate_click(monkeypatch) -> None:
    clicked: list[tuple[int, int]] = []

    def _fake_click_point(x: int, y: int) -> actions_mod.ActionResult:
        clicked.append((x, y))
        return actions_mod.ActionResult(ok=True, detail=f"clicked ({x}, {y})")

    # Patch the symbol the agent module imported.
    monkeypatch.setattr(agent, "click_point", _fake_click_point)

    ocr = _StubOCR(
        [
            TextRegion(text="Login", bbox=(0, 0, 100, 40), confidence=0.5),
            TextRegion(text="Submit", bbox=(200, 300, 400, 360), confidence=0.95),
        ]
    )

    class _LLMShouldNotBeCalled:
        def next_action(self, *, system: str, user: str):  # pragma: no cover
            raise AssertionError("LLM must not be called on the vision-fallback path")

    # Take just the first emitted event: the fallback click is not `done`, so
    # the loop would otherwise run to the step budget. The contract under test
    # is "the first step on a dead tree is an OCR coordinate-click".
    gen = agent.run(
        "Legacy",
        "click submit",
        max_steps=5,
        llm=_LLMShouldNotBeCalled(),
        snapshotter=lambda _app: _dead_tree(),
        settle_seconds=0.0,
        vision=True,
        ocr=ocr,
        screenshotter=lambda _app: object(),  # stub image, never inspected
    )
    ev = next(gen)
    gen.close()

    assert ocr.calls == 1, "OCR must be consulted exactly once for the dead step"
    assert ev.action.kind == "click"
    assert ev.error is None
    # Highest-confidence region wins → "Submit" center (300, 330).
    assert clicked == [(300, 330)]


def test_actionable_tree_never_consults_vision() -> None:
    """A UIA-rich step must take the normal LLM path; OCR is never touched."""

    ocr = _StubOCR([TextRegion(text="anything", bbox=(0, 0, 10, 10), confidence=1.0)])

    class _DoneLLM:
        def next_action(self, *, system: str, user: str):
            from uia_agent.actions import Action

            return Action(kind="done", reason="all set")

    events = list(
        agent.run(
            "App",
            "do nothing",
            max_steps=1,
            llm=_DoneLLM(),
            snapshotter=lambda _app: _actionable_tree(),
            settle_seconds=0.0,
            vision=True,
            ocr=ocr,
        )
    )

    assert ocr.calls == 0, "vision must not be consulted when the tree is actionable"
    assert events[-1].action.kind == "done"


def test_vision_disabled_means_normal_path_even_on_dead_tree() -> None:
    """Without the flag, a dead tree still goes to the LLM (UIA-first default)."""

    ocr = _StubOCR([TextRegion(text="x", bbox=(0, 0, 10, 10), confidence=1.0)])

    class _DoneLLM:
        def next_action(self, *, system: str, user: str):
            from uia_agent.actions import Action

            return Action(kind="done", reason="give up gracefully")

    events = list(
        agent.run(
            "Legacy",
            "noop",
            max_steps=1,
            llm=_DoneLLM(),
            snapshotter=lambda _app: _dead_tree(),
            settle_seconds=0.0,
            vision=False,
            ocr=ocr,
        )
    )

    assert ocr.calls == 0
    assert events[-1].action.kind == "done"
