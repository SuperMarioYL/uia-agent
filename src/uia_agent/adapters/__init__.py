"""Framework adapter layer (optional extras).

These adapters expose the `uia-agent` core (`dump` + `run`) as tools for
existing agent frameworks — LangChain first, with an AutoGen/CrewAI-compatible
shape sharing the same thin interface. The *core* package stays dependency-free:
every framework import in this package is lazy, so importing
:mod:`uia_agent.adapters` never drags LangChain (or any other framework) into a
plain `pip install uia-agent`.

Install the framework you want as an extra::

    pip install uia-agent[langchain]

Then::

    from uia_agent.adapters.langchain_tool import UiaRunTool, UiaDumpTool

The shared, framework-agnostic surface below (:class:`UiaToolSpec`,
:func:`dump_tool`, :func:`run_tool`) is what AutoGen / CrewAI bindings register
— a name, a description, a JSON-schema for the arguments, and a plain callable.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from ..uia_tree import count_nodes, snapshot, to_json

# JSON-schema for each tool's arguments — framework-neutral, reused by the
# LangChain wrapper and any AutoGen/CrewAI binding.
_DUMP_ARGS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["app"],
    "properties": {
        "app": {
            "type": "string",
            "description": "Window title or class-name substring (case-insensitive).",
        }
    },
}

_RUN_ARGS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["app", "instruction"],
    "properties": {
        "app": {
            "type": "string",
            "description": "Window title or class-name substring (case-insensitive).",
        },
        "instruction": {
            "type": "string",
            "description": "Natural-language goal for the agent to drive the app toward.",
        },
        "max_steps": {
            "type": "integer",
            "description": "Hard cap on the observe→act loop (default 25).",
        },
    },
}


@dataclass(frozen=True)
class UiaToolSpec:
    """A framework-agnostic tool definition.

    AutoGen and CrewAI both accept (name, description, schema, callable)-shaped
    tools; this dataclass is the shared shape their bindings register, and the
    LangChain wrapper is built from the same spec.
    """

    name: str
    description: str
    args_schema: dict[str, Any] = field(default_factory=dict)
    func: Callable[..., str] = field(default=lambda **_: "")


def _dump_impl(app: str) -> str:
    """Snapshot ``app`` and return its pruned UIA tree as JSON text."""
    tree = snapshot(app)
    return to_json(tree, indent=None)


def _run_impl(app: str, instruction: str, max_steps: int = 25) -> str:
    """Drive ``app`` toward ``instruction`` and return a newline-joined trace.

    Imported lazily so the adapter package stays importable without a live
    Windows session — :mod:`uia_agent.agent` only needs uiautomation at call
    time, not import time.
    """
    from ..agent import run

    lines: list[str] = []
    for event in run(app, instruction, max_steps=max_steps):
        action = event.action
        status = event.error or (event.result.detail if event.result else "")
        mark = "ERR" if event.error else "OK"
        lines.append(f"step {event.index:02d} {action.kind:<6} [{mark}] {status}")
    return "\n".join(lines) if lines else "(no steps executed)"


def dump_tool() -> UiaToolSpec:
    """The framework-neutral spec for the `dump` tool."""
    return UiaToolSpec(
        name="uia_dump",
        description=(
            "Snapshot a focused Windows app's UIA accessibility tree and return "
            "it as pruned JSON. Useful for inspecting available controls before "
            "driving the app."
        ),
        args_schema=_DUMP_ARGS_SCHEMA,
        func=_dump_impl,
    )


def run_tool() -> UiaToolSpec:
    """The framework-neutral spec for the `run` tool."""
    return UiaToolSpec(
        name="uia_run",
        description=(
            "Drive a focused Windows app toward a natural-language goal by "
            "observing its UIA tree and dispatching real clicks/keystrokes. "
            "Returns a step-by-step trace."
        ),
        args_schema=_RUN_ARGS_SCHEMA,
        func=_run_impl,
    )


__all__ = [
    "UiaToolSpec",
    "dump_tool",
    "run_tool",
    "count_nodes",  # re-export so adapters can summarize without a second import
]
