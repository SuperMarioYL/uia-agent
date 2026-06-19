"""The observe → think → act loop.

A plain Python while-loop, no framework. Each step:

1. Snapshot the focused app's UIA tree.
2. Serialize it + the running history to JSON for the LLM.
3. Ask the LLM for one `Action` (structured output, no soft-parse).
4. Dispatch the action.
5. Repeat until `done` or the step budget is exhausted.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass

from pydantic import BaseModel

from .actions import Action, ActionError, ActionResult, dispatch
from .llm import LLMClient, default_client
from .prompts import system_prompt, user_turn
from .uia_tree import UIANode, snapshot, to_json

MAX_STEPS_DEFAULT = 25
SETTLE_SECONDS = 0.4


class StepRecord(BaseModel):
    """One iteration of the loop, suitable for serializing to the LLM next turn."""

    index: int
    action: Action
    result: ActionResult


@dataclass
class StepEvent:
    """Emitted to the CLI stream so the user sees what is happening."""

    index: int
    action: Action
    result: ActionResult | None
    error: str | None


class AgentBudgetExceeded(RuntimeError):
    """Raised when the step budget runs out before the LLM emits `done`."""


def run(
    app: str,
    instruction: str,
    *,
    max_steps: int = MAX_STEPS_DEFAULT,
    llm: LLMClient | None = None,
    snapshotter: Callable[[str], UIANode] = snapshot,
    settle_seconds: float = SETTLE_SECONDS,
) -> Iterator[StepEvent]:
    """Drive ``app`` toward ``instruction``, yielding one StepEvent per step.

    The function is a generator so the CLI can stream progress live. It
    exhausts on either an emitted `done` action or a raised exception; the
    caller decides whether to bail or keep going on per-step errors.
    """
    client = llm or default_client()
    history: list[StepRecord] = []

    for step in range(1, max_steps + 1):
        tree = snapshotter(app)
        tree_json = to_json(tree, indent=None)
        history_json = _history_json(history)

        action = client.next_action(
            system=system_prompt(),
            user=user_turn(
                instruction=instruction,
                tree_json=tree_json,
                history_json=history_json,
                step=step,
                max_steps=max_steps,
            ),
        )

        try:
            result = dispatch(action, tree, app)
        except ActionError as exc:
            err = str(exc)
            history.append(
                StepRecord(
                    index=step,
                    action=action,
                    result=ActionResult(ok=False, detail=err),
                )
            )
            yield StepEvent(index=step, action=action, result=None, error=err)
            continue

        history.append(StepRecord(index=step, action=action, result=result))
        yield StepEvent(index=step, action=action, result=result, error=None)

        if result.finished:
            return

        if settle_seconds > 0:
            time.sleep(settle_seconds)

    raise AgentBudgetExceeded(
        f"step budget {max_steps} exhausted before agent emitted `done`"
    )


def _history_json(history: list[StepRecord]) -> str:
    """Serialize recent steps as JSON for the LLM's next prompt.

    We cap the history we feed back to ~6 steps to keep tokens bounded; the
    LLM has the full intent in the system prompt and only needs short-term
    context to avoid repeating itself.
    """
    tail = history[-6:]
    return "[" + ",".join(rec.model_dump_json(exclude_none=True) for rec in tail) + "]"
