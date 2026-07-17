"""MCP server exposing the uia-agent action space (optional `[mcp]` extra).

Mirrors the LangChain wrapper pattern (m4): this module is always importable —
it carries NO top-level ``mcp`` import, so
``from uia_agent.adapters.mcp_server import MCP_TOOL_SPECS`` works even on a plain
``pip install uia-agent``. The ``mcp`` SDK is imported lazily, only when you
actually build the server; without the extra you get a clear
:class:`MCPUnavailable` error instead of an opaque ``ImportError``.

Install the SDK with the optional extra::

    pip install uia-agent[mcp]

Then start the server (exposes ``uia_dump`` + ``uia_run`` over MCP stdio)::

    uia-agent mcp

The tools wrap the same framework-neutral specs as the LangChain / AutoGen /
CrewAI shape in :mod:`uia_agent.adapters`, so the run/dump schema is identical
across every framework surface.
"""

from __future__ import annotations

from typing import Any

from . import UiaToolSpec, dump_tool, run_tool

# Re-exported tool specs so callers can introspect the MCP tool contract
# without constructing an MCP server (and without the extra installed) — the
# same shape LangChain's wrapper exposes as DUMP_TOOL_SPEC / RUN_TOOL_SPEC.
MCP_TOOL_SPECS: tuple[UiaToolSpec, ...] = (dump_tool(), run_tool())


class MCPUnavailable(RuntimeError):
    """Raised when the MCP server is requested but the `mcp` extra is missing."""


def _require_mcp_server() -> Any:
    """Return ``mcp.server.Server`` or raise a clear error.

    The import is lazy so importing :mod:`uia_agent.adapters.mcp_server` never
    requires the ``mcp`` SDK to be installed; only building/running the server
    does.
    """
    try:
        from mcp.server import Server  # type: ignore[import-not-found]
    except ImportError as exc:
        raise MCPUnavailable(
            "the MCP server needs the mcp extra; install with "
            "`pip install uia-agent[mcp]`"
        ) from exc
    return Server


def build_server() -> Any:
    """Construct the MCP ``Server`` exposing ``uia_dump`` + ``uia_run``.

    Requires the ``[mcp]`` extra (raises :class:`MCPUnavailable` otherwise).
    The ``list_tools`` / ``call_tool`` handlers dispatch to the framework-
    neutral :class:`UiaToolSpec` callables, so the MCP surface stays in lockstep
    with the LangChain / AutoGen / CrewAI bindings.
    """
    Server = _require_mcp_server()
    server = Server("uia-agent")
    spec_by_name = {spec.name: spec for spec in MCP_TOOL_SPECS}

    @server.list_tools()
    async def list_tools() -> Any:  # type: ignore[no-untyped-def]
        from mcp.types import Tool  # type: ignore[import-not-found]

        return [
            Tool(
                name=spec.name,
                description=spec.description,
                inputSchema=spec.args_schema,
            )
            for spec in MCP_TOOL_SPECS
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict) -> Any:  # type: ignore[no-untyped-def]
        from mcp.types import TextContent  # type: ignore[import-not-found]

        spec = spec_by_name.get(name)
        if spec is None:
            raise ValueError(f"unknown tool {name!r}")
        result = spec.func(**(arguments or {}))
        return [TextContent(type="text", text=str(result))]

    return server


def run_mcp_server() -> None:
    """Start the MCP stdio server (requires the ``[mcp]`` extra).

    Raises :class:`MCPUnavailable` if the extra is missing. Intended to be the
    body of the ``uia-agent mcp`` CLI subcommand.
    """
    import asyncio

    server = build_server()
    from mcp.server.stdio import stdio_server  # type: ignore[import-not-found]

    async def _main() -> None:
        async with stdio_server() as (read, write):
            await server.run(read, write, server.create_initialization_options())

    asyncio.run(_main())


__all__ = [
    "MCP_TOOL_SPECS",
    "MCPUnavailable",
    "build_server",
    "run_mcp_server",
]
