"""Pruning rules + stable-id behavior of the UIA snapshot.

These tests do NOT touch the live Windows UIA API — they exercise the pure
walking + pruning logic through a fake control tree. That keeps the suite
green on macOS / Linux CI; the windows_only-marked integration tests run on
windows-latest jobs.
"""

from __future__ import annotations

from typing import Any

import pytest

from uia_agent.uia_tree import (
    MAX_DEPTH,
    MAX_NODES,
    UIANode,
    _stable_id,
    count_nodes,
    snapshot_from,
    to_json,
)


class FakeControl:
    """Minimal stand-in for a uiautomation Control sufficient for _walk()."""

    def __init__(
        self,
        *,
        role: str,
        name: str = "",
        automation_id: str = "",
        enabled: bool = True,
        bbox: tuple[int, int, int, int] = (10, 10, 100, 50),
        children: list["FakeControl"] | None = None,
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

    def GetChildren(self) -> list["FakeControl"]:
        return self._children

    def GetInvokePattern(self) -> object | None:
        return _Pattern() if "Invoke" in self._patterns else None

    def GetValuePattern(self) -> object | None:
        return _ValuePattern(self._value) if "Value" in self._patterns else None

    def GetTogglePattern(self) -> object | None:
        return _Pattern() if "Toggle" in self._patterns else None

    def GetExpandCollapsePattern(self) -> object | None:
        return _Pattern() if "ExpandCollapse" in self._patterns else None

    def GetSelectionPattern(self) -> object | None:
        return _Pattern() if "Selection" in self._patterns else None

    def GetSelectionItemPattern(self) -> object | None:
        return _Pattern() if "SelectionItem" in self._patterns else None

    def GetTextPattern(self) -> object | None:
        return _Pattern() if "Text" in self._patterns else None

    def GetScrollItemPattern(self) -> object | None:
        return _Pattern() if "ScrollItem" in self._patterns else None


class _Rect:
    def __init__(self, left: int, top: int, right: int, bottom: int) -> None:
        self.left = left
        self.top = top
        self.right = right
        self.bottom = bottom


class _Pattern:  # noqa: D401 — truthy sentinel
    """Truthy sentinel that the pattern exists."""

    def __bool__(self) -> bool:  # pragma: no cover - trivial
        return True


class _ValuePattern(_Pattern):
    def __init__(self, value: str | None) -> None:
        self.Value = value


def _btn(name: str, **kw: Any) -> FakeControl:
    return FakeControl(role="Button", name=name, patterns=("Invoke",), **kw)


def test_stable_id_is_deterministic_and_path_sensitive() -> None:
    a = _stable_id("Button", "OK", "okBtn", (0, 1, 2))
    b = _stable_id("Button", "OK", "okBtn", (0, 1, 2))
    c = _stable_id("Button", "OK", "okBtn", (0, 1, 3))
    assert a == b
    assert a != c, "depth_path must change the id so siblings don't collide"


def test_snapshot_returns_uianode_with_pruned_children() -> None:
    root = FakeControl(
        role="Window",
        name="Notepad",
        children=[
            _btn("File"),
            _btn("Edit"),
            FakeControl(role="Pane", name="", children=[]),  # noisy empty leaf → pruned
        ],
    )
    snap = snapshot_from(root)
    assert isinstance(snap, UIANode)
    assert snap.role == "Window"
    names = [c.name for c in snap.children]
    assert names == ["File", "Edit"], "unnamed noise leaf should be pruned"


def test_offscreen_nodes_are_dropped() -> None:
    root = FakeControl(
        role="Window",
        name="App",
        children=[
            _btn("Visible", bbox=(0, 0, 100, 40)),
            _btn("Offscreen", bbox=(-500, -500, -400, -400)),
            _btn("ZeroArea", bbox=(50, 50, 50, 50)),
        ],
    )
    snap = snapshot_from(root)
    names = [c.name for c in snap.children]
    assert names == ["Visible"]


def test_node_budget_caps_total_count() -> None:
    deep_children = [_btn(f"b{i}") for i in range(MAX_NODES + 50)]
    root = FakeControl(role="Window", name="Wide", children=deep_children)
    snap = snapshot_from(root)
    assert count_nodes(snap) <= MAX_NODES


def test_depth_cap_truncates_pathologically_deep_tree() -> None:
    leaf = _btn("leaf")
    current: FakeControl = leaf
    for i in range(MAX_DEPTH + 5):
        current = FakeControl(
            role="Group",
            name=f"wrap-{i}",
            children=[current],
        )
    snap = snapshot_from(current)
    # Walk down counting visible levels.
    depth = 0
    node: UIANode | None = snap
    while node is not None and node.children:
        depth += 1
        node = node.children[0]
    assert depth <= MAX_DEPTH + 1


def test_to_json_is_valid_and_excludes_none() -> None:
    import json as _json

    root = FakeControl(
        role="Window",
        name="App",
        children=[_btn("OK", patterns=("Invoke",))],
    )
    snap = snapshot_from(root)
    blob = to_json(snap)
    parsed = _json.loads(blob)
    assert parsed["role"] == "Window"
    assert "value" not in parsed, "exclude_none should drop null fields"
    assert parsed["children"][0]["patterns"] == ["Invoke"]


def test_value_pattern_value_is_captured() -> None:
    edit = FakeControl(
        role="Edit",
        name="filename",
        patterns=("Value",),
        value="poem.txt",
    )
    root = FakeControl(role="Window", name="Save As", children=[edit])
    snap = snapshot_from(root)
    assert snap.children[0].value == "poem.txt"
    assert "Value" in snap.children[0].patterns


@pytest.mark.windows_only
def test_live_notepad_snapshot_under_token_budget() -> None:  # pragma: no cover
    """Integration test — only runs in the Windows CI matrix job."""
    pytest.importorskip("uiautomation")
    from uia_agent.uia_tree import snapshot

    snap = snapshot("Notepad")
    assert count_nodes(snap) <= MAX_NODES
    assert len(to_json(snap)) < 32_000  # ~8k tokens at 4 chars/token
