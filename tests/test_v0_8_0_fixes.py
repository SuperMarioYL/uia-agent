"""Regression tests for the v0.8.0 source-audit fixes.

Two independent fixes, each with a test that fails on the v0.7.0 code and passes
once the corresponding fix is applied (the evaluator revert-verifies each fix
in isolation).

Fix 1 (fix-vision-click-crash): ``_vision_fallback_event`` (agent.py:109) called
``click_point(x, y)`` unguarded. The v0.7.0 fix hardened the vision screenshot
step (vision.py:221) and the OCR step (vision.py:117-125) so any failure degrades
to the LLM step (the v0.4.0 contract), but the click that consumes the OCR region
was the last unguarded vision step — ``click_point`` (actions.py:220-231) calls
``auto.Click`` with no try/except, so a click failure raised a raw exception that
propagated uncaught through ``run``'s vision branch and aborted the whole run.
The fix wraps the ``click_point`` call in ``_vision_fallback_event`` so a click
failure returns ``None`` and the run falls through to the LLM step, symmetric
with the screenshot/OCR guards.

Fix 2 (fix-key-sendkeys-unguarded): ``_do_key`` (actions.py:269) called
``auto.SendKeys(text, waitTime=0.0)`` unguarded — the only dispatch helper whose
native call was not wrapped after the v0.7.0 fix. Unlike ``_do_type`` (whose
SendKeys input is escaped by ``escape_sendkeys`` to well-formed grammar),
``_do_key`` passes the LLM's raw text straight to SendKeys, so a malformed key
sequence or any uiautomation runtime error raised a raw exception that propagated
past ``run``'s ``ActionError``-only catch and aborted the whole run — asymmetric
with ``_do_click``/``_do_select``/``_do_expand``. The fix wraps the SendKeys call
raising a recoverable ``ActionError``, mirroring the v0.7.0 pattern.
"""

from __future__ import annotations

import sys
import types

import pytest

from uia_agent import agent
from uia_agent.uia_tree import UIANode

# === Fix 1: vision click failure degrades to the LLM step ==================


def _dead_tree() -> UIANode:
    """An owner-drawn pane: present, but exposes no actionable patterns — the
    only case where the vision fallback is consulted."""
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


class _StubOCR:
    """OCR engine returning one fixed region regardless of the image."""

    def regions(self, image: object):  # noqa: ANN001
        from uia_agent.vision import TextRegion

        return [TextRegion(text="Save", bbox=(10, 20, 30, 40), confidence=0.9)]


def test_vision_fallback_returns_none_when_click_fails(monkeypatch) -> None:
    """``_vision_fallback_event`` must catch a ``click_point`` failure and return
    ``None`` (so ``run`` falls through to the LLM step), not let the raw
    exception propagate and abort the run. v0.7.0 called ``click_point``
    unguarded — a raising click surfaces as an uncaught exception here."""
    from uia_agent.actions import ActionResult

    def _raising_click_point(x: int, y: int) -> ActionResult:
        raise RuntimeError("Click failed: offscreen coordinate")

    monkeypatch.setattr(agent, "click_point", _raising_click_point)

    clicked: list[tuple[int, int]] = []
    event = agent._vision_fallback_event(
        "Legacy",
        1,
        ocr=_StubOCR(),
        screenshotter=lambda _app: object(),  # bare stub image, never inspected
        clicked_points=clicked,
    )
    assert event is None, "a click failure must degrade to None, not raise"
    # The failed coordinate is recorded as seen before the click, so it is not
    # retried on the next dead step (a click that fails on a coordinate will
    # fail again on retry).
    assert clicked == [(20, 30)]


def test_vision_click_failure_degrades_to_llm_step(monkeypatch) -> None:
    """End-to-end: a ``--vision`` run whose OCR click fails (``click_point``
    raises) must NOT abort the whole run. ``_vision_fallback_event`` catches the
    click failure and returns ``None`` so ``run`` falls through to the LLM step
    (symmetric with the screenshot/OCR guards), instead of v0.7.0's uncaught
    ``click_point`` exception aborting the run (CLI exit 1)."""
    from uia_agent.actions import Action
    from uia_agent.vision import tree_has_actionable_nodes

    def _raising_click_point(x: int, y: int):
        raise RuntimeError("Click failed: offscreen coordinate")

    monkeypatch.setattr(agent, "click_point", _raising_click_point)

    dead_tree = _dead_tree()
    assert tree_has_actionable_nodes(dead_tree) is False

    class _DoneLLM:
        """Called once — on the step the vision click failed and the loop fell
        through to the LLM."""

        def __init__(self) -> None:
            self.calls = 0

        def next_action(self, *, system: str, user: str) -> Action:
            self.calls += 1
            return Action(kind="done", reason="click failed; giving up")

    llm = _DoneLLM()
    events = list(
        agent.run(
            "Legacy",
            "click save",
            max_steps=3,
            llm=llm,
            snapshotter=lambda _app: dead_tree,
            settle_seconds=0.0,
            vision=True,
            ocr=_StubOCR(),
            screenshotter=lambda _app: object(),  # stub image, never inspected
        )
    )

    assert llm.calls >= 1, "run must fall through to the LLM step on click failure"
    assert events[-1].action.kind == "done"


# === Fix 2: SendKeys failure in the key action -> recoverable ActionError ====


class _RaisingSendKeys:
    """A fake ``uiautomation`` module whose ``SendKeys`` raises — models a
    malformed key sequence (unbalanced brace / unknown key name) or any
    uiautomation runtime error. Built as a ``types.ModuleType`` and injected
    via ``sys.modules`` so ``_do_key``'s lazy ``import uiautomation as auto``
    picks it up without a live Windows session (mirrors ``_fake_pytesseract``
    in test_v0_4_0_fixes.py)."""

    @staticmethod
    def build() -> types.ModuleType:
        mod = types.ModuleType("uiautomation")

        def _sendkeys(text: str, waitTime: float = 0.0) -> None:  # noqa: ANN001
            raise RuntimeError("unknown key name")

        mod.SendKeys = _sendkeys
        return mod


def test_do_key_sendkeys_failure_raises_action_error(monkeypatch) -> None:
    """``_do_key`` must convert an ``auto.SendKeys`` failure (malformed key
    sequence / runtime error) to a recoverable ``ActionError`` (which
    ``agent.run`` catches at agent.py:188), not a raw ``RuntimeError`` that
    propagates past the ``ActionError``-only catch and aborts the whole run.
    v0.7.0 left ``auto.SendKeys`` unguarded."""
    from uia_agent.actions import ActionError, _do_key

    monkeypatch.setitem(sys.modules, "uiautomation", _RaisingSendKeys.build())

    with pytest.raises(ActionError, match="SendKeys failed") as exc_info:
        _do_key("{Entr}")
    # The underlying cause is chained so genuine bugs surface in the run log.
    assert isinstance(exc_info.value.__cause__, RuntimeError)


def _minimal_tree() -> UIANode:
    """A small valid snapshot; the ``key`` action needs no target so the tree
    content is irrelevant beyond being serializable for the LLM turn."""
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


def test_key_sendkeys_failure_does_not_abort_run(monkeypatch) -> None:
    """End-to-end: a ``key`` action whose ``SendKeys`` fails mid-run must NOT
    abort the whole run. ``agent.run`` catches the ``ActionError`` ``_do_key``
    now raises, yields a per-step event with ``error`` set (so the LLM can
    correct next turn), and continues to the next step — instead of v0.7.0's
    raw-exception run-abort (CLI exit 1)."""
    from uia_agent.actions import Action

    monkeypatch.setitem(sys.modules, "uiautomation", _RaisingSendKeys.build())

    class _LLM:
        """Step 1: emit the key that fails. Step 2: emit done."""

        def __init__(self) -> None:
            self.calls = 0

        def next_action(self, *, system: str, user: str) -> Action:
            self.calls += 1
            if self.calls == 1:
                return Action(kind="key", text="{Entr}", reason="try shortcut")
            return Action(kind="done", reason="recovered")

    llm = _LLM()
    events = list(
        agent.run(
            "App",
            "do thing",
            max_steps=3,
            llm=llm,
            snapshotter=lambda _app: _minimal_tree(),
            settle_seconds=0.0,
        )
    )

    # The key failure surfaces as a per-step error event, not a run-abort.
    assert len(events) == 2
    key_ev, done_ev = events
    assert key_ev.action.kind == "key"
    assert key_ev.error is not None
    assert "SendKeys failed" in key_ev.error
    assert key_ev.result is None  # ActionError path: result not recorded
    # The run continued past the failed step and the LLM emitted done.
    assert done_ev.action.kind == "done"
    assert llm.calls == 2
