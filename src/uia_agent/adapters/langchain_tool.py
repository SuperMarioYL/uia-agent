"""LangChain tool wrapper for the uia-agent core (optional `[langchain]` extra).

This module is always importable — it carries NO top-level LangChain import, so
`from uia_agent.adapters.langchain_tool import UiaRunTool` works even on a plain
`pip install uia-agent`. LangChain is imported lazily, only when you actually
build a tool; without the extra you get a clear :class:`LangChainUnavailable`
error instead of an opaque ``ImportError``.

Usage (after `pip install uia-agent[langchain]`)::

    from uia_agent.adapters.langchain_tool import UiaRunTool, UiaDumpTool

    tools = [UiaDumpTool(), UiaRunTool()]
    # ... hand `tools` to any LangChain agent / AgentExecutor.

The tools wrap the same framework-neutral specs as the AutoGen / CrewAI shape
in :mod:`uia_agent.adapters`, so the run/dump schema is identical across
frameworks.
"""

from __future__ import annotations

from typing import Any

from . import UiaToolSpec, dump_tool, run_tool

# Re-exported argument schemas so callers can introspect the tool contract
# without constructing a LangChain object (and without the extra installed).
DUMP_TOOL_SPEC: UiaToolSpec = dump_tool()
RUN_TOOL_SPEC: UiaToolSpec = run_tool()


class LangChainUnavailable(RuntimeError):
    """Raised when a LangChain tool is requested but LangChain isn't installed."""


def _require_structured_tool() -> Any:
    """Return ``langchain_core.tools.StructuredTool`` or raise a clear error."""
    try:
        from langchain_core.tools import StructuredTool
    except ImportError:
        try:
            # Older monolithic LangChain layout.
            from langchain.tools import StructuredTool  # type: ignore[no-redef]
        except ImportError as exc:
            raise LangChainUnavailable(
                "the LangChain wrapper needs the langchain extra; install with "
                "`pip install uia-agent[langchain]`"
            ) from exc
    return StructuredTool


def _build(spec: UiaToolSpec) -> Any:
    """Turn a framework-neutral :class:`UiaToolSpec` into a LangChain tool."""
    structured_tool = _require_structured_tool()
    return structured_tool.from_function(
        func=spec.func,
        name=spec.name,
        description=spec.description,
    )


def UiaDumpTool() -> Any:  # noqa: N802 - factory named like the tool it returns
    """Construct the LangChain `uia_dump` tool (requires the `[langchain]` extra)."""
    return _build(DUMP_TOOL_SPEC)


def UiaRunTool() -> Any:  # noqa: N802 - factory named like the tool it returns
    """Construct the LangChain `uia_run` tool (requires the `[langchain]` extra)."""
    return _build(RUN_TOOL_SPEC)


def make_langchain_tools() -> list[Any]:
    """Build both LangChain tools at once (requires the `[langchain]` extra)."""
    return [UiaDumpTool(), UiaRunTool()]


__all__ = [
    "DUMP_TOOL_SPEC",
    "RUN_TOOL_SPEC",
    "LangChainUnavailable",
    "UiaDumpTool",
    "UiaRunTool",
    "make_langchain_tools",
]
