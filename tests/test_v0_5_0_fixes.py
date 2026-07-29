"""Regression tests for the v0.5.0 source-audit fixes.

Three independent fixes, each with a test that fails on the v0.4.0 code and
passes once the corresponding fix is applied (the evaluator revert-verifies
each fix in isolation).

Fix 1 (fix-offscreen-negative-coordinates): ``_is_offscreen`` treated any
negative ``right``/``bottom`` edge as offscreen. Windows places monitors
left-of/above the primary display at negative virtual-screen coordinates, so
every control on such a monitor was pruned — including the root window, which
crashes ``snapshot_from`` with ``SnapshotError("root control was pruned
away")``. The fix prunes only boxes lying *entirely* outside the virtual screen
(symmetric ``-32_000`` lower bound mirroring the existing ``+32_000`` upper
bound), so legitimate negative-coord windows are kept.

Fix 2 (fix-adapter-budget-trace-lost): ``_run_impl`` (the body of both the
LangChain ``UiaRunTool`` and the MCP ``uia_run`` tool) did not catch
``AgentBudgetExceeded``. Unlike the CLI (which exits 3 with the partial trace
already streamed), the exception propagated to the framework caller and the
buffered ``lines`` (the whole partial trace) was discarded — a >25-step task
surfaced as an opaque tool error with zero output. The fix wraps the loop in
``try/except AgentBudgetExceeded`` and returns the joined partial trace plus a
``[budget]`` marker, mirroring the CLI.

Fix 3 (fix-openai-null-content-opaque-crash): the OpenAI path did
``payload = response.choices[0].message.content or "{}"`` then
``Action.model_validate(json.loads(payload))``. Under strict json_schema mode
OpenAI returns ``message.content = null`` with ``finish_reason =
"content_filter"``; the ``or "{}"`` fallback turned that into ``{}``, which
failed pydantic validation (required ``kind`` missing) and propagated as an
opaque ``ValidationError`` — asymmetric with the Anthropic path's clear
``RuntimeError`` guard. The fix guards before parsing, raising a clear
``RuntimeError`` mirroring the Anthropic guard.
"""

from __future__ import annotations

import pytest

# --- Fix 1: negative virtual-screen coordinates are not offscreen ------------


class _Rect:
    """Stand-in for uiautomation's BoundingRectangle."""

    def __init__(self, left: int, top: int, right: int, bottom: int) -> None:
        self.left, self.top, self.right, self.bottom = left, top, right, bottom


class _Pattern:
    """Truthy sentinel that a UIA control pattern is present."""

    def __bool__(self) -> bool:  # pragma: no cover - trivial
        return True


class _FakeControl:
    """Minimal uiautomation.Control stand-in sufficient for ``_walk()``.

    Mirrors the fake in ``tests/test_uia_tree.py`` so the offscreen regression
    exercises the real walk path (the actual crash) rather than only the
    predicate.
    """

    def __init__(
        self,
        *,
        role: str,
        name: str = "",
        automation_id: str = "",
        enabled: bool = True,
        bbox: tuple[int, int, int, int] = (10, 10, 100, 50),
        children: list[_FakeControl] | None = None,
        is_control_element: bool = True,
        value: str | None = None,
        patterns: tuple[str, ...] = (),
    ) -> None:
        self.ControlTypeName = f"{role}Control"
        self.Name = name
        self.AutomationId = automation_id
        self.IsEnabled = enabled
        self.IsControlElement = is_control_element
        self.BoundingRectangle = _Rect(*bbox)
        self._children = children or []
        self._value = value
        self._patterns = set(patterns)

    def GetChildren(self) -> list[_FakeControl]:
        return self._children

    def GetInvokePattern(self) -> _Pattern | None:
        return _Pattern() if "Invoke" in self._patterns else None

    def GetValuePattern(self) -> _Pattern | None:
        return _Pattern() if "Value" in self._patterns else None

    def GetTogglePattern(self) -> _Pattern | None:
        return _Pattern() if "Toggle" in self._patterns else None

    def GetExpandCollapsePattern(self) -> _Pattern | None:
        return _Pattern() if "ExpandCollapse" in self._patterns else None

    def GetSelectionPattern(self) -> _Pattern | None:
        return _Pattern() if "Selection" in self._patterns else None

    def GetSelectionItemPattern(self) -> _Pattern | None:
        return _Pattern() if "SelectionItem" in self._patterns else None

    def GetTextPattern(self) -> _Pattern | None:
        return _Pattern() if "Text" in self._patterns else None

    def GetScrollItemPattern(self) -> _Pattern | None:
        return _Pattern() if "ScrollItem" in self._patterns else None


def _button(name: str, **kw: object) -> _FakeControl:
    return _FakeControl(role="Button", name=name, patterns=("Invoke",), **kw)  # type: ignore[arg-type]


def test_left_of_primary_monitor_window_is_not_pruned() -> None:
    """A window living on a monitor left-of the primary display occupies
    negative virtual-screen coordinates (its right edge sits at the boundary
    with, or entirely left of, the primary). These are valid on Windows
    multi-monitor desktops and must NOT be pruned — the v0.4.0 heuristic pruned
    them all as offscreen, crashing ``snapshot_from`` with ``SnapshotError``.
    """
    from uia_agent.uia_tree import SnapshotError, _is_offscreen, snapshot_from

    # Predicate level: a left-of-primary box must not be offscreen.
    assert _is_offscreen((-1920, 0, -100, 1080)) is False  # left-of-primary
    assert _is_offscreen((-100, -800, 800, 0)) is False  # above-primary
    # A box ENTIRELY beyond the virtual screen is still genuinely offscreen.
    assert _is_offscreen((-32_500, 0, -32_400, 100)) is True

    # End-to-end level: the root window itself lives on the left-of-primary
    # monitor; under v0.4.0 the root was pruned and snapshot_from raised.
    root = _FakeControl(
        role="Window",
        name="Legacy",
        bbox=(-1920, 0, -100, 1080),
        children=[_button("OK", bbox=(-1500, 100, -1400, 140))],
    )
    snap = snapshot_from(root)
    assert snap.name == "Legacy"
    assert snap.bbox == (-1920, 0, -100, 1080)
    assert [c.name for c in snap.children] == ["OK"]
    # Negative-coord children survive the walk too.
    assert snap.children[0].bbox == (-1500, 100, -1400, 140)

    # And a root lying entirely beyond the virtual screen still raises — the
    # fix did not neuter genuine offscreen pruning.
    dead_root = _FakeControl(role="Window", name="Ghost", bbox=(-32_500, 0, -32_400, 100))
    with pytest.raises(SnapshotError):
        snapshot_from(dead_root)


# --- Fix 2: _run_impl returns the partial trace on AgentBudgetExceeded -------


def test_run_impl_returns_partial_trace_on_budget_exceeded(monkeypatch) -> None:
    """``_run_impl`` (the body of the LangChain ``UiaRunTool`` and the MCP
    ``uia_run`` tool) must catch ``AgentBudgetExceeded`` and return the buffered
    partial trace plus a ``[budget]`` marker — mirroring the CLI's
    exit-3-with-partial-trace behavior. v0.4.0 propagated the exception and
    discarded the whole ``lines`` buffer, so a >max_steps task surfaced as an
    opaque tool error with zero output.
    """
    from uia_agent.actions import Action, ActionResult
    from uia_agent.adapters import _run_impl
    from uia_agent.agent import AgentBudgetExceeded, StepEvent

    def _fake_run(app: str, instruction: str, *, max_steps: int = 25) -> StepEvent:
        # Mirror agent.py: a generator that yields step events and then raises
        # AgentBudgetExceeded after the loop when no `done` is emitted.
        yield StepEvent(
            index=1,
            action=Action(kind="click", target_id="a", text=None, reason="r1"),
            result=ActionResult(ok=True, detail="clicked a"),
            error=None,
        )
        yield StepEvent(
            index=2,
            action=Action(kind="type", target_id="b", text="hi", reason="r2"),
            result=ActionResult(ok=True, detail="typed b"),
            error=None,
        )
        raise AgentBudgetExceeded(
            f"step budget {max_steps} exhausted before agent emitted `done`"
        )

    # _run_impl does `from ..agent import run` at call time, so patching the
    # module attribute routes the tool to the fake generator.
    monkeypatch.setattr("uia_agent.agent.run", _fake_run)

    out = _run_impl("Legacy", "do thing", max_steps=2)

    # The buffered partial trace (both steps) is returned, not discarded.
    assert "step 01" in out
    assert "click" in out
    assert "step 02" in out
    assert "type" in out
    # The budget marker is appended, mirroring the CLI's "[budget] <msg>" line.
    assert "[budget]" in out
    assert "exhausted" in out


# --- Fix 3: OpenAI null content raises a clear RuntimeError ------------------


def test_openai_null_content_raises_clear_runtime_error() -> None:
    """Under strict json_schema mode OpenAI returns ``message.content = null``
    with ``finish_reason = "content_filter"`` when a call is filtered. The v0.4.0
    ``content or "{}"`` fallback turned that into ``{}``, which failed pydantic
    validation (required ``kind`` missing) and propagated as an opaque
    ``ValidationError`` through ``run`` to the CLI's generic ``[error]`` exit —
    asymmetric with the Anthropic path's clear ``RuntimeError`` guard. The OpenAI
    path must now raise a clear, actionable ``RuntimeError``, not a pydantic
    crash.
    """
    from pydantic import ValidationError

    from uia_agent.llm import OpenAIClient

    class _Message:
        content = None  # OpenAI returns null under content_filter

    class _Choice:
        message = _Message()
        finish_reason = "content_filter"

    class _Response:
        choices = [_Choice()]

    class _Completions:
        def create(self, **_kwargs: object) -> _Response:
            return _Response()

    class _Chat:
        completions = _Completions()

    class _FakeOpenAI:
        chat = _Chat()

    client = OpenAIClient.__new__(OpenAIClient)
    client._client = _FakeOpenAI()  # type: ignore[attr-defined]
    client._model = "gpt-4o-2024-11-20"  # type: ignore[attr-defined]

    with pytest.raises(RuntimeError) as exc_info:
        client.next_action(system="sys", user="usr")

    # Must NOT be the opaque pydantic ValidationError the v0.4.0 path raised.
    assert not isinstance(exc_info.value, ValidationError)
    # The message must be actionable (point at refusal/content_filter).
    msg = str(exc_info.value)
    assert "no structured output" in msg
    assert "content_filter" in msg
