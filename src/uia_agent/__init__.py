"""uia-agent — drive Windows thick-client apps via the UIA accessibility tree."""

from __future__ import annotations

from .actions import Action, ActionError, ActionResult, dispatch
from .agent import AgentBudgetExceeded, StepEvent, StepRecord, run
from .llm import LLMClient, default_client
from .uia_tree import (
    MAX_DEPTH,
    MAX_NODES,
    SnapshotError,
    UIANode,
    count_nodes,
    snapshot,
    snapshot_from,
    to_json,
)

__version__ = "0.1.0"

__all__ = [
    "Action",
    "ActionError",
    "ActionResult",
    "AgentBudgetExceeded",
    "LLMClient",
    "MAX_DEPTH",
    "MAX_NODES",
    "SnapshotError",
    "StepEvent",
    "StepRecord",
    "UIANode",
    "__version__",
    "count_nodes",
    "default_client",
    "dispatch",
    "run",
    "snapshot",
    "snapshot_from",
    "to_json",
]
