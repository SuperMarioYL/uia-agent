"""Typed action vocabulary that dispatches to real UIA control patterns.

The action set is deliberately small (7 kinds). Each one maps cleanly back to
one or two UIA patterns — this is the contract the LLM sees in `prompts.py`
and the surface the agent loop dispatches through.
"""

from __future__ import annotations

import contextlib
import time
from typing import Any, Literal

from pydantic import BaseModel, Field

from .uia_tree import UIANode, _find_window

ActionKind = Literal["click", "type", "select", "expand", "key", "wait", "done"]


class Action(BaseModel):
    """One step the LLM asked the agent to take."""

    kind: ActionKind
    target_id: str | None = Field(
        default=None,
        description="UIANode.id from the most recent snapshot; required for ui actions.",
    )
    text: str | None = Field(
        default=None,
        description="Payload for `type` and `key` actions; ignored otherwise.",
    )
    reason: str = Field(
        default="",
        description="One-sentence chain-of-thought trace from the LLM.",
    )


class ActionResult(BaseModel):
    """The outcome of dispatching one action."""

    ok: bool
    detail: str = ""
    finished: bool = False


class ActionError(RuntimeError):
    """Raised when an action cannot be dispatched against the live UIA tree."""


def _index_by_id(node: UIANode, out: dict[str, UIANode]) -> None:
    out[node.id] = node
    for child in node.children:
        _index_by_id(child, out)


def index_tree(root: UIANode) -> dict[str, UIANode]:
    """Flatten a snapshot into an id → UIANode lookup table."""
    out: dict[str, UIANode] = {}
    _index_by_id(root, out)
    return out


def _resolve_live_control(node: UIANode, app: str) -> Any:
    """Walk the live UIA tree again and locate the control that matches ``node``.

    The serialized snapshot only carries the stable ID + role + name; to act on
    the control we have to re-walk the live tree and find the same node. We
    match on (role, name, bbox-overlap) — bbox is the tiebreaker when multiple
    controls share a role + name (common with menu items).
    """
    import uiautomation as auto  # noqa: F401  (import for side effect / docstring)

    window = _find_window(app)
    return _find_matching(window, node)


def _find_matching(control: Any, target: UIANode) -> Any:
    """DFS the live tree for a control whose (role, name, bbox) matches ``target``."""
    role_name = getattr(control, "ControlTypeName", "") or ""
    role = role_name[: -len("Control")] if role_name.endswith("Control") else role_name
    name = (getattr(control, "Name", "") or "").strip() or None

    if role == target.role and name == target.name:
        rect = getattr(control, "BoundingRectangle", None)
        if rect is not None:
            try:
                bbox = (int(rect.left), int(rect.top), int(rect.right), int(rect.bottom))
            except Exception:
                bbox = (0, 0, 0, 0)
            if _bbox_overlap(bbox, target.bbox) > 0.5:
                return control

    try:
        children = control.GetChildren() or []
    except Exception:
        children = []
    for child in children:
        hit = _find_matching(child, target)
        if hit is not None:
            return hit
    return None


def _bbox_overlap(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> float:
    """Intersection-over-union for two axis-aligned bounding boxes."""
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    iw, ih = max(0, ix2 - ix1), max(0, iy2 - iy1)
    inter = iw * ih
    if inter == 0:
        return 0.0
    area_a = max(0, ax2 - ax1) * max(0, ay2 - ay1)
    area_b = max(0, bx2 - bx1) * max(0, by2 - by1)
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0


def _require_target(action: Action, index: dict[str, UIANode]) -> UIANode:
    if action.target_id is None:
        raise ActionError(f"action {action.kind!r} requires target_id")
    node = index.get(action.target_id)
    if node is None:
        raise ActionError(f"target_id {action.target_id!r} not in current snapshot")
    if not node.enabled:
        raise ActionError(f"target {action.target_id!r} is disabled")
    return node


def _do_click(control: Any) -> None:
    invoke = getattr(control, "GetInvokePattern", lambda: None)()
    if invoke is not None:
        try:
            invoke.Invoke()
            return
        except Exception:
            pass

    select_item = getattr(control, "GetSelectionItemPattern", lambda: None)()
    if select_item is not None:
        try:
            select_item.Select()
            return
        except Exception:
            pass

    click = getattr(control, "Click", None)
    if click is None:
        raise ActionError("control supports no Invoke / SelectionItem / Click")
    try:
        click(simulateMove=False)
    except TypeError:
        click()


# `uiautomation.SendKeys` treats these characters as the start of a special
# sequence; to send them literally each must be wrapped as `{c}`. Newlines have
# no literal form at all and must be translated to the `{Enter}` token.
_SENDKEYS_META = frozenset("{}()+^%~")


def escape_sendkeys(text: str) -> str:
    """Escape SendKeys metacharacters and translate newlines to ``{Enter}``.

    `uiautomation.SendKeys` interprets ``{ } ( ) + ^ % ~`` as control sequences
    and silently drops/garbles them otherwise; ``\\n`` is not a literal newline
    there either. This makes an arbitrary ``type`` payload (e.g. a multi-line
    haiku with parentheses) round-trip byte-for-byte through the SendKeys
    fallback. Carriage returns are folded so ``\\r\\n`` yields a single
    ``{Enter}``.
    """
    out: list[str] = []
    for ch in text.replace("\r\n", "\n").replace("\r", "\n"):
        if ch == "\n":
            out.append("{Enter}")
        elif ch in _SENDKEYS_META:
            out.append("{" + ch + "}")
        else:
            out.append(ch)
    return "".join(out)


def _do_type(control: Any, text: str) -> None:
    if text is None:
        raise ActionError("type action requires non-empty text")
    value = getattr(control, "GetValuePattern", lambda: None)()
    if value is not None:
        try:
            # The Value pattern writes the literal string directly — no SendKeys
            # grammar involved, so the raw text is correct here.
            value.SetValue(text)
            return
        except Exception:
            pass

    set_focus = getattr(control, "SetFocus", None)
    if set_focus is not None:
        with contextlib.suppress(Exception):
            set_focus()

    import uiautomation as auto

    # The SendKeys fallback runs the text through the SendKeys grammar, so any
    # metacharacters / newlines must be escaped first or the payload corrupts.
    auto.SendKeys(escape_sendkeys(text), waitTime=0.0)


def click_point(x: int, y: int) -> ActionResult:
    """Click a raw screen coordinate (vision-fallback path only).

    The UIA-first path never calls this — it is reserved for the OCR fallback,
    where the only handle on an owner-drawn control is the center of a detected
    text region. Lazily imports ``uiautomation`` so the core stays importable
    without a live Windows session.
    """
    import uiautomation as auto

    auto.Click(int(x), int(y), waitTime=0.0)
    return ActionResult(ok=True, detail=f"clicked screen point ({x}, {y})")


def _do_select(control: Any) -> None:
    pattern = getattr(control, "GetSelectionItemPattern", lambda: None)()
    if pattern is None:
        raise ActionError("control does not expose SelectionItem")
    pattern.Select()


def _do_expand(control: Any) -> None:
    pattern = getattr(control, "GetExpandCollapsePattern", lambda: None)()
    if pattern is None:
        raise ActionError("control does not expose ExpandCollapse")
    state = getattr(pattern, "ExpandCollapseState", 0)
    # 0 = Collapsed, 1 = Expanded — toggle toward expanded.
    if state == 1:
        return
    pattern.Expand()


def _do_key(text: str) -> None:
    if not text:
        raise ActionError("key action requires non-empty text (e.g. '{Enter}', '^s')")
    import uiautomation as auto

    auto.SendKeys(text, waitTime=0.0)


def dispatch(action: Action, snapshot_root: UIANode, app: str) -> ActionResult:
    """Run one action against the live application.

    ``snapshot_root`` is the tree the LLM saw; ``app`` is the same window
    selector the agent used to take the snapshot. We re-resolve the live
    control from the snapshot node so the LLM never has to know about UIA
    handles.
    """
    if action.kind == "done":
        return ActionResult(ok=True, detail=action.reason or "agent reported done", finished=True)

    if action.kind == "wait":
        seconds = 0.5
        if action.text:
            try:
                seconds = max(0.0, min(5.0, float(action.text)))
            except ValueError:
                seconds = 0.5
        time.sleep(seconds)
        return ActionResult(ok=True, detail=f"waited {seconds:.2f}s")

    if action.kind == "key":
        _do_key(action.text or "")
        return ActionResult(ok=True, detail=f"sent keys {action.text!r}")

    target = _require_target(action, index_tree(snapshot_root))
    control = _resolve_live_control(target, app)
    if control is None:
        raise ActionError(
            f"could not re-resolve target {target.id!r} ({target.role}:{target.name!r}) "
            "in live tree"
        )

    if action.kind == "click":
        _do_click(control)
        return ActionResult(ok=True, detail=f"clicked {target.role}:{target.name!r}")
    if action.kind == "type":
        _do_type(control, action.text or "")
        return ActionResult(ok=True, detail=f"typed into {target.role}:{target.name!r}")
    if action.kind == "select":
        _do_select(control)
        return ActionResult(ok=True, detail=f"selected {target.role}:{target.name!r}")
    if action.kind == "expand":
        _do_expand(control)
        return ActionResult(ok=True, detail=f"expanded {target.role}:{target.name!r}")

    raise ActionError(f"unknown action kind {action.kind!r}")
