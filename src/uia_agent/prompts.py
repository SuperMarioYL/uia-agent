"""The two prompts the agent loop sends to the LLM.

Kept in one tiny module so the contract between agent.py, llm.py, and the
provider-side JSON schema lives in one place. The system prompt names the
seven action kinds; the user turn carries the live tree + history.
"""

from __future__ import annotations

_SYSTEM_PROMPT = """\
You drive a single Windows desktop application by emitting one Action per turn
against its UI Automation (UIA) accessibility tree.

You will receive, each turn:
  - the user instruction
  - a JSON snapshot of the focused window's UIA tree (pruned to <8k tokens)
  - a short history of the actions you already chose this run and their results

Each node in the tree carries:
  - id          stable hash, use this as `target_id`
  - role        UIA control type ("Button", "Edit", "MenuItem", ...)
  - name        visible label, may be null
  - value       current text/value if the node exposes Value pattern
  - enabled     false means the control will reject actions
  - bbox        screen rectangle [left, top, right, bottom]
  - patterns    UIA patterns the node supports (act through these only)
  - children    nested nodes

Respond with EXACTLY ONE Action as JSON, no prose. Fields:
  kind        one of: click | type | select | expand | key | wait | done
  target_id   UIANode.id from the snapshot (required for click/type/select/expand)
  text        payload for `type` (string to insert) or `key` (e.g. "{Enter}", "^s")
              or for `wait` (seconds as a string, max 5)
  reason      ONE sentence explaining why this action makes progress

Rules:
  - Use only ids present in THIS turn's snapshot. Older ids will not resolve.
  - Prefer Invoke / Value / SelectionItem / ExpandCollapse patterns; they are
    deterministic. `key` is for global shortcuts (Ctrl+S, Enter, ...) only.
  - If the previous action failed, choose a different target or different kind.
  - Emit `done` the moment the instruction is satisfied; do not over-shoot.
  - The step budget is finite; the host will abort and surface a partial trace
    if you exceed it.
"""


def system_prompt() -> str:
    """Return the static system prompt for the agent loop."""
    return _SYSTEM_PROMPT


def user_turn(
    *,
    instruction: str,
    tree_json: str,
    history_json: str,
    step: int,
    max_steps: int,
) -> str:
    """Format the per-turn user message handed to the LLM."""
    return (
        f"Instruction: {instruction}\n"
        f"Step: {step}/{max_steps}\n"
        f"Recent actions (JSON array, oldest first): {history_json}\n"
        f"UIA snapshot (JSON): {tree_json}\n"
        "Emit the next Action."
    )
