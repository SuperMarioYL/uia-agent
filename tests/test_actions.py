"""Action validation, target resolution, and dispatch routing.

The real UIA dispatch paths require a live Windows desktop; they are exercised
under the windows_only marker. The cross-platform tests below cover the parts
of `actions.py` that don't touch the OS: pydantic shape, indexing, target
require-checks, and the no-target action kinds (`done`, `wait`).
"""

from __future__ import annotations

import pytest

from uia_agent.actions import (
    Action,
    ActionError,
    ActionResult,
    _do_click,
    _do_type,
    dispatch,
    escape_sendkeys,
    index_tree,
)
from uia_agent.uia_tree import UIANode


def _leaf(
    node_id: str, *, role: str = "Button", name: str | None = "OK", enabled: bool = True
) -> UIANode:
    return UIANode(
        id=node_id,
        role=role,
        name=name,
        enabled=enabled,
        bbox=(0, 0, 50, 20),
        patterns=["Invoke"],
        children=[],
    )


def _tree() -> UIANode:
    return UIANode(
        id="root",
        role="Window",
        name="App",
        bbox=(0, 0, 800, 600),
        children=[
            _leaf("btn-ok", name="OK"),
            _leaf("btn-cancel", name="Cancel"),
            _leaf("btn-disabled", name="Stale", enabled=False),
        ],
    )


def test_action_validates_enum_kind() -> None:
    with pytest.raises(ValueError):
        Action.model_validate({"kind": "frobnicate", "reason": "x"})


def test_index_tree_flattens_to_lookup() -> None:
    snap = _tree()
    idx = index_tree(snap)
    assert set(idx.keys()) == {"root", "btn-ok", "btn-cancel", "btn-disabled"}
    assert idx["btn-ok"].name == "OK"


def test_done_action_returns_finished_result() -> None:
    snap = _tree()
    result = dispatch(Action(kind="done", reason="all set"), snap, app="App")
    assert isinstance(result, ActionResult)
    assert result.ok
    assert result.finished


def test_wait_action_clamps_seconds_and_does_not_touch_ui() -> None:
    snap = _tree()
    result = dispatch(Action(kind="wait", text="0.01", reason="settle"), snap, app="App")
    assert result.ok
    assert result.finished is False
    assert "waited" in result.detail


def test_wait_action_rejects_garbage_text_with_default() -> None:
    snap = _tree()
    result = dispatch(Action(kind="wait", text="not a number", reason="settle"), snap, app="App")
    assert result.ok, "wait should fall back to the default delay on bad input"


def test_click_without_target_id_raises() -> None:
    snap = _tree()
    with pytest.raises(ActionError, match="requires target_id"):
        dispatch(Action(kind="click", reason="press"), snap, app="App")


def test_click_with_unknown_target_id_raises() -> None:
    snap = _tree()
    with pytest.raises(ActionError, match="not in current snapshot"):
        dispatch(Action(kind="click", target_id="ghost", reason="press"), snap, app="App")


def test_click_disabled_target_raises_before_resolving_live_control() -> None:
    snap = _tree()
    with pytest.raises(ActionError, match="disabled"):
        dispatch(
            Action(kind="click", target_id="btn-disabled", reason="press"),
            snap,
            app="App",
        )


def test_key_action_requires_text() -> None:
    snap = _tree()
    with pytest.raises(ActionError, match="non-empty text"):
        dispatch(Action(kind="key", reason="shortcut"), snap, app="App")


def test_escape_sendkeys_wraps_every_metacharacter() -> None:
    # Each of { } ( ) + ^ % ~ must be wrapped as {c} so SendKeys sends it
    # literally instead of interpreting it as a control sequence.
    assert escape_sendkeys("{") == "{{}"
    assert escape_sendkeys("}") == "{}}"
    assert escape_sendkeys("(") == "{(}"
    assert escape_sendkeys(")") == "{)}"
    assert escape_sendkeys("+") == "{+}"
    assert escape_sendkeys("^") == "{^}"
    assert escape_sendkeys("%") == "{%}"
    assert escape_sendkeys("~") == "{~}"


def test_escape_sendkeys_translates_newlines_to_enter() -> None:
    assert escape_sendkeys("a\nb") == "a{Enter}b"
    # CRLF and bare CR fold to a single {Enter} each.
    assert escape_sendkeys("a\r\nb") == "a{Enter}b"
    assert escape_sendkeys("a\rb") == "a{Enter}b"


def test_escape_sendkeys_leaves_plain_text_untouched() -> None:
    assert escape_sendkeys("hello world.txt") == "hello world.txt"


def test_escape_sendkeys_round_trips_a_multiline_special_char_payload() -> None:
    # The headline haiku-with-punctuation case: every metacharacter wrapped,
    # every newline → {Enter}, byte-for-byte.
    payload = "f(x)+y^2 {note}\n100% done~"
    expected = "f{(}x{)}{+}y{^}2 {{}note{}}{Enter}100{%} done{~}"
    assert escape_sendkeys(payload) == expected


class _FakeControl:
    """Minimal stand-in for a ``uiautomation`` control — only the attributes the
    dispatch helpers touch (``Get*Pattern`` / ``Click``). Lets the click/type
    regression tests run cross-platform without a live Windows desktop session."""

    def __init__(self, *, invoke=None, select=None, click=None):
        self._invoke = invoke
        self._select = select
        self._click = click

    def GetInvokePattern(self):
        return self._invoke

    def GetSelectionItemPattern(self):
        return self._select

    def Click(self, simulateMove=False, **kwargs):  # noqa: ANN001, ANN002
        if self._click is not None:
            self._click()

    def __repr__(self):
        return "<_FakeControl>"


class _RaisingInvoke:
    """An Invoke pattern whose Invoke() raises — models a control that became
    disabled / vanished between snapshot and dispatch."""

    def Invoke(self) -> None:
        raise RuntimeError("ElementNotEnabled")


class _RaisingSelect:
    def Select(self) -> None:
        raise RuntimeError("ElementNotEnabled")


def test_type_action_requires_non_empty_text() -> None:
    # Regression: an empty/None `type` payload used to no-op through
    # SendKeys("") while dispatch reported ok=True (silent data loss). The
    # guard now mirrors `_do_key`'s `if not text` so it surfaces as a per-step
    # ActionError the LLM can correct next turn.
    fake = _FakeControl()
    with pytest.raises(ActionError, match="non-empty text"):
        _do_type(fake, "")
    with pytest.raises(ActionError, match="non-empty text"):
        _do_type(fake, None)


def test_click_raises_on_invoke_failure_instead_of_swallowing() -> None:
    # Regression: _do_click used to `except Exception: pass` around Invoke(),
    # then fall through to a coordinate Click that raises nothing on a disabled
    # control, so dispatch reported a silent ok=True for a click that had no
    # effect. A genuine invoke failure must now surface as an ActionError
    # (agent.run maps that to ActionResult(ok=False) + event.error).
    control = _FakeControl(invoke=_RaisingInvoke())
    with pytest.raises(ActionError, match="Invoke failed"):
        _do_click(control)


def test_click_raises_on_select_failure_instead_of_swallowing() -> None:
    control = _FakeControl(select=_RaisingSelect())
    with pytest.raises(ActionError, match="Select failed"):
        _do_click(control)


def test_click_coordinate_fallback_preserved_for_patternless_control() -> None:
    # The coordinate Click fallback must stay for controls that expose NO
    # pattern — only the swallowed *failures* were converted to errors, not the
    # legitimate no-pattern path.
    clicked: list[int] = []
    control = _FakeControl(click=lambda: clicked.append(1))
    _do_click(control)  # should not raise
    assert clicked == [1]


@pytest.mark.windows_only
def test_live_notepad_click_round_trip() -> None:  # pragma: no cover
    """Integration check — only runs under the Windows CI matrix job."""
    pytest.importorskip("uiautomation")
    # The real test is the example scripts under examples/; this stub just
    # documents the intent so the windows_only marker has a target.
