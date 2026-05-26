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
    dispatch,
    index_tree,
)
from uia_agent.uia_tree import UIANode


def _leaf(node_id: str, *, role: str = "Button", name: str | None = "OK", enabled: bool = True) -> UIANode:
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


@pytest.mark.windows_only
def test_live_notepad_click_round_trip() -> None:  # pragma: no cover
    """Integration check — only runs under the Windows CI matrix job."""
    pytest.importorskip("uiautomation")
    # The real test is the example scripts under examples/; this stub just
    # documents the intent so the windows_only marker has a target.
