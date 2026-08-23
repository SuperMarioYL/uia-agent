"""Regression tests for the v0.7.0 source-audit fixes.

Four independent fixes, each with a test that fails on the v0.6.0 code and
passes once the corresponding fix is applied (the evaluator revert-verifies
each fix in isolation).

Fix 1 (fix-select-expand-unguarded-pattern): ``_do_select`` (actions.py:238)
called ``pattern.Select()`` unguarded and ``_do_expand`` (actions.py:249)
called ``pattern.Expand()`` unguarded. A genuine pattern failure (control
disabled/vanished between snapshot and dispatch) raised a raw exception that
propagated past ``agent.run``'s ``ActionError``-only catch (agent.py:188) and
aborted the whole multi-step run — asymmetric with ``_do_click``'s Invoke /
SelectionItem handling. The fix wraps both calls in ``try/except`` raising a
recoverable ``ActionError``.

Fix 2 (fix-vision-screenshot-crash): ``fallback_regions`` (vision.py:185)
called ``shoot(app)`` unguarded. ``_default_screenshotter`` raises
``VisionUnavailable`` when the uiautomation build exposes no screenshot helper
or there is no live Windows session, and that exception propagated uncaught
through ``_vision_fallback_event`` and ``run``, aborting the whole run —
contradicting the v0.4.0 contract that a vision-step failure must degrade to
the LLM step. The fix wraps ``shoot(app)`` so a screenshot failure returns
``[]`` and the run falls through to the LLM step (symmetric with the
``TesseractEngine.regions`` guard).

Fix 3 (fix-vision-ocr-coordinate-offset): ``_default_screenshotter`` captured
only the window's ``BoundingRectangle``, so pytesseract returned
window-relative coordinates, but ``click_point`` passed the center straight
to ``auto.Click`` (actions.py:230) which expects screen-absolute coordinates.
For any window not at screen origin the vision fallback silently clicked an
offset point reported as ``ok=True``. The fix threads the window's
``(rect.left, rect.top)`` screen offset from the screenshotter through
``fallback_regions`` and adds it to each OCR region's bbox so click
coordinates are screen-absolute.

Fix 4 (fix-adapter-partial-trace-non-budget): ``_run_impl``
(adapters/__init__.py:103) only caught ``AgentBudgetExceeded``. Any other
run-aborting exception (``SnapshotError`` from agent.py:146, the LLM refusal
``RuntimeError`` from llm.py:129) propagated and discarded the whole buffered
``lines`` trace — asymmetric with the CLI, which streams each step live before
its generic ``[error]`` exit. The fix broadens the ``except`` to catch any
run-aborting error, append a trailing ``[error]`` line, and return the joined
partial trace (mirroring the v0.5.0 budget path).
"""

from __future__ import annotations

import pytest

import uia_agent.actions as actions_mod
from uia_agent import agent
from uia_agent.uia_tree import UIANode

# === Fix 1: select/expand pattern failure -> recoverable ActionError ========


class _RaisingSelectPattern:
    """A SelectionItem pattern whose Select() raises — models a control that
    became disabled / vanished between snapshot and dispatch."""

    def Select(self) -> None:
        raise RuntimeError("ElementNotEnabled")


class _RaisingExpandPattern:
    """An ExpandCollapse pattern whose Expand() raises; state is Collapsed (0)
    so _do_expand does not short-circuit and actually calls Expand()."""

    ExpandCollapseState = 0

    def Expand(self) -> None:
        raise RuntimeError("ElementNotAvailable")


class _FakeSelectControl:
    """Minimal stand-in exposing a SelectionItem pattern that fails on Select."""

    def GetSelectionItemPattern(self) -> _RaisingSelectPattern:
        return _RaisingSelectPattern()

    def __repr__(self) -> str:
        return "<_FakeSelectControl>"


class _FakeExpandControl:
    """Minimal stand-in exposing an ExpandCollapse pattern that fails on Expand."""

    def GetExpandCollapsePattern(self) -> _RaisingExpandPattern:
        return _RaisingExpandPattern()

    def __repr__(self) -> str:
        return "<_FakeExpandControl>"


def test_do_select_failure_raises_action_error_not_raw_exception() -> None:
    """``_do_select`` must surface a Select() failure as a recoverable
    ``ActionError`` (which agent.run catches at agent.py:188), not a raw
    ``RuntimeError`` that propagates past the ActionError-only catch and aborts
    the whole run. v0.6.0 left ``pattern.Select()`` unguarded."""
    from uia_agent.actions import ActionError, _do_select

    with pytest.raises(ActionError, match="Select failed") as exc_info:
        _do_select(_FakeSelectControl())
    # The underlying cause is chained so genuine bugs surface in the run log.
    assert isinstance(exc_info.value.__cause__, RuntimeError)


def test_do_expand_failure_raises_action_error_not_raw_exception() -> None:
    """``_do_expand`` must surface an Expand() failure as a recoverable
    ``ActionError``, mirroring _do_select / _do_click. v0.6.0 left
    ``pattern.Expand()`` unguarded."""
    from uia_agent.actions import ActionError, _do_expand

    with pytest.raises(ActionError, match="Expand failed") as exc_info:
        _do_expand(_FakeExpandControl())
    assert isinstance(exc_info.value.__cause__, RuntimeError)


def _select_tree() -> UIANode:
    return UIANode(
        id="root",
        role="Window",
        name="App",
        bbox=(0, 0, 800, 600),
        children=[
            UIANode(
                id="item",
                role="ListItem",
                name="Choice",
                enabled=True,
                bbox=(10, 10, 110, 40),
                patterns=["SelectionItem"],
            )
        ],
    )


def test_select_pattern_failure_does_not_abort_run(monkeypatch) -> None:
    """End-to-end: a select action whose SelectionItem.Select() fails mid-run
    must NOT abort the whole run. ``agent.run`` catches the ``ActionError``,
    yields a per-step event with ``error`` set (so the LLM can correct next
    turn), and continues to the next step — instead of v0.6.0's raw-exception
    run-abort (CLI exit 1 / framework opaque error)."""
    from uia_agent.actions import Action

    # _resolve_live_control re-walks the live UIA tree (Windows-only); patch it
    # to return the failing-pattern control so dispatch reaches _do_select.
    monkeypatch.setattr(
        actions_mod, "_resolve_live_control", lambda _node, _app: _FakeSelectControl()
    )

    class _LLM:
        """Step 1: emit the select that fails. Step 2: emit done."""

        def __init__(self) -> None:
            self.calls = 0

        def next_action(self, *, system: str, user: str) -> Action:
            self.calls += 1
            if self.calls == 1:
                return Action(kind="select", target_id="item", reason="pick Choice")
            return Action(kind="done", reason="recovered")

    llm = _LLM()
    events = list(
        agent.run(
            "App",
            "pick Choice",
            max_steps=3,
            llm=llm,
            snapshotter=lambda _app: _select_tree(),
            settle_seconds=0.0,
        )
    )

    # The select failure surfaces as a per-step error event, not a run-abort.
    assert len(events) == 2
    select_ev, done_ev = events
    assert select_ev.action.kind == "select"
    assert select_ev.error is not None
    assert "Select failed" in select_ev.error
    assert select_ev.result is None  # ActionError path: result not recorded
    # The run continued past the failed step and the LLM emitted done.
    assert done_ev.action.kind == "done"
    assert llm.calls == 2


# === Fix 2: vision screenshot failure degrades to the LLM step =============


def test_fallback_regions_screenshot_failure_returns_empty(monkeypatch) -> None:
    """``fallback_regions`` must catch a screenshot failure and return ``[]``,
    so ``_vision_fallback_event`` returns ``None`` and the run falls through to
    the LLM step — not the v0.6.0 uncaught crash."""
    from uia_agent.vision import VisionUnavailable, fallback_regions

    def _raising_screenshotter(_app: str) -> object:
        raise VisionUnavailable("uiautomation build exposes no screenshot helper")

    regions = fallback_regions("Legacy", screenshotter=_raising_screenshotter)
    assert regions == []


def test_vision_screenshot_failure_degrades_to_llm_step(monkeypatch) -> None:
    """End-to-end regression for the reported crash: a ``--vision`` run on a
    dead tree, with the screenshotter raising, must NOT crash. It must fall
    through to the LLM step (no OCR coordinate click) and emit the LLM's
    ``done`` action — instead of the v0.6.0 opaque run crash."""
    from uia_agent.actions import Action
    from uia_agent.vision import VisionUnavailable, tree_has_actionable_nodes

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

        def next_action(self, *, system: str, user: str) -> Action:
            self.calls += 1
            return Action(kind="done", reason="screenshot unavailable; giving up")

    llm = _DoneLLM()

    def _raising_screenshotter(_app: str) -> object:
        raise VisionUnavailable("no live Windows session")

    events = list(
        agent.run(
            "Legacy",
            "click submit",
            max_steps=3,
            llm=llm,
            snapshotter=lambda _app: dead_tree,
            settle_seconds=0.0,
            vision=True,
            ocr=None,
            screenshotter=_raising_screenshotter,
        )
    )

    assert clicked == [], "no OCR coordinate click when the screenshot fails"
    assert llm.calls >= 1, "run must fall through to the LLM step on screenshot failure"
    assert events[-1].action.kind == "done"


# === Fix 3: window screen offset added to OCR click coordinates =============


def test_fallback_regions_applies_window_screen_offset() -> None:
    """A screenshotter returning an ``(image, offset)`` pair — the default path
    crops to the window, so OCR coords are window-relative — must have its
    offset added to each OCR region's bbox so click coordinates are
    screen-absolute. v0.6.0 passed window-relative coords straight to
    ``auto.Click``."""
    from uia_agent.vision import TextRegion, fallback_regions

    class _StubOCR:
        def regions(self, image: object) -> list[TextRegion]:
            return [TextRegion(text="Save", bbox=(10, 20, 30, 40), confidence=0.9)]

    # Window offset (100, 200): every bbox coordinate shifts by that delta.
    regions = fallback_regions(
        "Legacy",
        ocr=_StubOCR(),
        screenshotter=lambda _app: (object(), (100, 200)),
    )
    assert len(regions) == 1
    assert regions[0].bbox == (110, 220, 130, 240)
    # center is now screen-absolute: (20, 30) + (100, 200) == (120, 230)
    assert regions[0].center == (120, 230)


def test_fallback_regions_bare_image_keeps_zero_offset() -> None:
    """A stub screenshotter returning a bare image (the test convention) keeps
    offset (0, 0) — regions are unchanged. Guards against regressing the
    existing stub-screenshotter tests."""
    from uia_agent.vision import TextRegion, fallback_regions

    class _StubOCR:
        def regions(self, image: object) -> list[TextRegion]:
            return [TextRegion(text="X", bbox=(10, 20, 30, 40), confidence=0.9)]

    regions = fallback_regions(
        "Legacy",
        ocr=_StubOCR(),
        screenshotter=lambda _app: object(),
    )
    assert regions[0].bbox == (10, 20, 30, 40)
    assert regions[0].center == (20, 30)


def test_vision_ocr_click_includes_window_screen_offset(monkeypatch) -> None:
    """End-to-end: a vision-fallback OCR click on a window not at screen
    origin lands on the OCR region center PLUS the window's
    ``(rect.left, rect.top)`` screen offset — not the v0.6.0 silently-offset
    click. The screenshotter returns ``(image, (left, top))``; the stub OCR
    returns a region whose window-relative center is (20, 30); with the window
    at screen (100, 200) the click must land at (120, 230)."""
    from uia_agent.actions import Action
    from uia_agent.vision import TextRegion, tree_has_actionable_nodes

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

    class _StubOCR:
        def __init__(self) -> None:
            self.calls = 0

        def regions(self, image: object) -> list[TextRegion]:
            self.calls += 1
            # Window-relative bbox (10,20,30,40) -> center (20, 30).
            return [TextRegion(text="Save", bbox=(10, 20, 30, 40), confidence=0.9)]

    class _LLMShouldNotBeCalled:
        def next_action(self, *, system: str, user: str) -> Action:  # pragma: no cover
            raise AssertionError("LLM must not be called on the vision-fallback step")

    ocr = _StubOCR()
    gen = agent.run(
        "Legacy",
        "click save",
        max_steps=5,
        llm=_LLMShouldNotBeCalled(),
        snapshotter=lambda _app: dead_tree,
        settle_seconds=0.0,
        vision=True,
        ocr=ocr,
        # Window lives at screen (100, 200); default screenshotter would thread
        # this offset from the live BoundingRectangle. Injected here directly.
        screenshotter=lambda _app: (object(), (100, 200)),
    )
    ev = next(gen)
    gen.close()

    assert ocr.calls == 1
    assert ev.action.kind == "click"
    assert ev.error is None
    # OCR region center (20, 30) + window offset (100, 200) == (120, 230).
    assert clicked == [(120, 230)], f"expected offset-corrected click, got {clicked}"


# === Fix 4: partial trace preserved on any run-aborting error ===============


def test_run_impl_returns_partial_trace_on_non_budget_abort(monkeypatch) -> None:
    """``_run_impl`` (the body of the LangChain ``UiaRunTool`` and the MCP
    ``uia_run`` tool) must catch ANY run-aborting exception — not just
    ``AgentBudgetExceeded`` — and return the buffered partial trace plus a
    trailing ``[error]`` line, mirroring the CLI's live-stream-then-``[error]``
    behavior. v0.5.0 preserved the trace only for budget exhaustion; a
    ``SnapshotError`` (window vanishes mid-run) discarded the whole ``lines``
    buffer as an opaque tool error with zero output."""
    from uia_agent.actions import Action, ActionResult
    from uia_agent.adapters import _run_impl
    from uia_agent.agent import StepEvent
    from uia_agent.uia_tree import SnapshotError

    def _fake_run(app: str, instruction: str, *, max_steps: int = 25):
        # Yield one good step, then a non-budget run-aborting error mid-run.
        yield StepEvent(
            index=1,
            action=Action(kind="click", target_id="a", text=None, reason="r1"),
            result=ActionResult(ok=True, detail="clicked a"),
            error=None,
        )
        raise SnapshotError("window vanished mid-run")

    # _run_impl does `from ..agent import run` at call time, so patching the
    # module attribute routes the tool to the fake generator.
    monkeypatch.setattr("uia_agent.agent.run", _fake_run)

    out = _run_impl("Legacy", "do thing", max_steps=3)

    # The buffered partial trace (the one good step) is returned, not discarded.
    assert "step 01" in out
    assert "click" in out
    # A trailing [error] line mirrors the CLI's generic [error] exit.
    assert "[error]" in out
    assert "window vanished mid-run" in out
    # And it is a returned string, not a raised exception (no opaque tool error).
    assert isinstance(out, str)
