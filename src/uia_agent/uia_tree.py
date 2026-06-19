"""UIA Action Frame — the core primitive.

A pruned, LLM-readable snapshot of the Windows UI Automation tree of a single
focused process. The novelty is treating the UIA tree as a first-class action
space for an LLM loop; the defensible craft is the pruning that keeps the
serialized tree under ~8k tokens on typical Windows apps.
"""

from __future__ import annotations

import hashlib
import json
import time
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    import uiautomation as auto  # noqa: F401


MAX_DEPTH = 12
MAX_NODES = 400
SNAPSHOT_TIMEOUT_S = 1.0

# Roles whose unnamed leaves carry no information for an LLM and should be
# pruned to keep the serialized tree small. A node with children is always
# kept (it may be a structural container).
_NOISE_LEAF_ROLES = frozenset(
    {
        "Pane",
        "Group",
        "Custom",
        "Image",
        "Separator",
        "ToolBar",
        "Thumb",
    }
)


class UIANode(BaseModel):
    """A single node in the pruned UIA tree."""

    id: str = Field(description="Stable hash of (role, name, automation_id, depth_path).")
    role: str = Field(description="UIA control type, e.g. 'Button', 'Edit', 'MenuItem'.")
    name: str | None = Field(default=None, description="Visible label.")
    value: str | None = Field(default=None, description="Current text/value via Value pattern.")
    enabled: bool = True
    bbox: tuple[int, int, int, int] = Field(
        default=(0, 0, 0, 0),
        description="(left, top, right, bottom) screen coords.",
    )
    patterns: list[str] = Field(
        default_factory=list,
        description="UIA control patterns the node exposes, e.g. ['Invoke', 'Value'].",
    )
    children: list[UIANode] = Field(default_factory=list)


UIANode.model_rebuild()


class SnapshotError(RuntimeError):
    """Raised when the UIA tree cannot be captured."""


def _stable_id(
    role: str, name: str | None, automation_id: str | None, depth_path: tuple[int, ...]
) -> str:
    payload = json.dumps(
        {"r": role, "n": name or "", "a": automation_id or "", "p": list(depth_path)},
        ensure_ascii=False,
        sort_keys=True,
    )
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:12]


def _is_offscreen(bbox: tuple[int, int, int, int]) -> bool:
    left, top, right, bottom = bbox
    if right <= left or bottom <= top:
        return True
    # Heuristic: a node positioned far outside any plausible screen is offscreen.
    return right < 0 or bottom < 0 or left > 32_000 or top > 32_000


def _patterns_for(control: Any) -> list[str]:
    """Best-effort enumeration of the UIA control patterns a node exposes."""
    candidates = (
        ("Invoke", "GetInvokePattern"),
        ("Value", "GetValuePattern"),
        ("Toggle", "GetTogglePattern"),
        ("ExpandCollapse", "GetExpandCollapsePattern"),
        ("Selection", "GetSelectionPattern"),
        ("SelectionItem", "GetSelectionItemPattern"),
        ("Text", "GetTextPattern"),
        ("ScrollItem", "GetScrollItemPattern"),
    )
    found: list[str] = []
    for label, accessor in candidates:
        getter = getattr(control, accessor, None)
        if getter is None:
            continue
        try:
            if getter():
                found.append(label)
        except Exception:
            continue
    return found


def _read_value(control: Any) -> str | None:
    getter = getattr(control, "GetValuePattern", None)
    if getter is None:
        return None
    try:
        pattern = getter()
    except Exception:
        return None
    if pattern is None:
        return None
    value = getattr(pattern, "Value", None)
    if isinstance(value, str) and value:
        return value
    return None


def _read_bbox(control: Any) -> tuple[int, int, int, int]:
    rect = getattr(control, "BoundingRectangle", None)
    if rect is None:
        return (0, 0, 0, 0)
    try:
        return (int(rect.left), int(rect.top), int(rect.right), int(rect.bottom))
    except Exception:
        return (0, 0, 0, 0)


def _role_of(control: Any) -> str:
    name = getattr(control, "ControlTypeName", None)
    if isinstance(name, str) and name.endswith("Control"):
        return name[: -len("Control")]
    return name or "Unknown"


def _walk(
    control: Any,
    depth: int,
    depth_path: tuple[int, ...],
    node_budget: list[int],
) -> UIANode | None:
    """Recursive walk that applies the pruning rules.

    Pruning order matters: cheap checks (depth / budget / offscreen / disabled)
    happen before pattern enumeration, which is the expensive call.
    """
    if depth > MAX_DEPTH:
        return None
    if node_budget[0] <= 0:
        return None

    try:
        if not bool(getattr(control, "IsControlElement", True)):
            return None
    except Exception:
        return None

    bbox = _read_bbox(control)
    if _is_offscreen(bbox):
        return None

    role = _role_of(control)
    name_attr = getattr(control, "Name", "") or ""
    name = name_attr.strip() or None
    automation_id = getattr(control, "AutomationId", "") or None

    try:
        enabled = bool(getattr(control, "IsEnabled", True))
    except Exception:
        enabled = True

    children_raw: list[Any] = []
    try:
        children_raw = list(control.GetChildren() or [])
    except Exception:
        children_raw = []

    node_budget[0] -= 1
    pruned_children: list[UIANode] = []
    for idx, child in enumerate(children_raw):
        if node_budget[0] <= 0:
            break
        sub = _walk(child, depth + 1, depth_path + (idx,), node_budget)
        if sub is not None:
            pruned_children.append(sub)

    # Drop noisy leaves (no name, no value, no children, noise role).
    is_leaf = not pruned_children
    if is_leaf and name is None and role in _NOISE_LEAF_ROLES:
        node_budget[0] += 1  # refund the slot we tentatively claimed
        return None

    patterns = _patterns_for(control)
    value = _read_value(control)

    # Drop truly empty leaves: no name, no value, no patterns, no children.
    if is_leaf and name is None and value is None and not patterns:
        node_budget[0] += 1
        return None

    return UIANode(
        id=_stable_id(role, name, automation_id, depth_path),
        role=role,
        name=name,
        value=value,
        enabled=enabled,
        bbox=bbox,
        patterns=patterns,
        children=pruned_children,
    )


def _find_window(app: str) -> Any:
    """Locate the top-level window whose title or process matches ``app``."""
    import uiautomation as auto

    needle = app.strip().lower()
    if not needle:
        raise SnapshotError("empty app target")

    deadline = time.monotonic() + SNAPSHOT_TIMEOUT_S
    while time.monotonic() < deadline:
        try:
            root = auto.GetRootControl()
            for child in root.GetChildren() or []:
                title = (getattr(child, "Name", "") or "").lower()
                class_name = (getattr(child, "ClassName", "") or "").lower()
                if needle in title or needle in class_name:
                    return child
        except Exception:
            pass
        time.sleep(0.05)

    raise SnapshotError(f"no top-level window matched {app!r}")


def snapshot(app: str) -> UIANode:
    """Capture and prune the UIA tree for the top-level window matching ``app``.

    The match is a case-insensitive substring against the window title or
    class name. The caller is responsible for focusing the right process —
    UIA can read background windows but stable LLM loops want foreground.
    """
    window = _find_window(app)
    return snapshot_from(window)


def snapshot_from(control: Any) -> UIANode:
    """Snapshot a specific UIA control (escape hatch for tests + advanced use)."""
    budget = [MAX_NODES]
    node = _walk(control, depth=0, depth_path=(), node_budget=budget)
    if node is None:
        raise SnapshotError("root control was pruned away (offscreen / disabled / empty)")
    return node


def count_nodes(node: UIANode) -> int:
    total = 1
    for child in node.children:
        total += count_nodes(child)
    return total


def to_json(node: UIANode, *, indent: int | None = 2) -> str:
    """Serialize a snapshot to JSON suitable for handing to an LLM."""
    return node.model_dump_json(indent=indent, exclude_none=True)
