"""MCP server adapter (m7).

Mirrors the LangChain adapter contract (tests/test_adapters.py): the core must
stay dependency-free — importing the MCP module (and even reading its
module-level specs) must NOT require the `mcp` SDK. Constructing the server
without the extra installed must fail with a clear, typed error — not an opaque
ImportError.
"""

from __future__ import annotations

import importlib

import pytest

from uia_agent.adapters import UiaToolSpec, dump_tool, run_tool
from uia_agent.adapters.mcp_server import (
    MCP_TOOL_SPECS,
    MCPUnavailable,
    build_server,
)


def test_mcp_specs_expose_run_and_dump_schemas() -> None:
    names = {spec.name for spec in MCP_TOOL_SPECS}
    assert names == {"uia_dump", "uia_run"}
    for spec in MCP_TOOL_SPECS:
        assert isinstance(spec, UiaToolSpec)
        assert spec.args_schema["type"] == "object"
        assert "app" in spec.args_schema["properties"]


def test_mcp_specs_importable_without_extra() -> None:
    # Module-level specs exist even without the mcp extra installed; this is the
    # "imports under [mcp]" smoke check from the milestone, and it holds whether
    # or not the mcp SDK happens to be installed.
    run_spec = next(s for s in MCP_TOOL_SPECS if s.name == "uia_run")
    assert set(run_spec.args_schema["required"]) == {"app", "instruction"}
    assert "max_steps" in run_spec.args_schema["properties"]
    dump_spec = next(s for s in MCP_TOOL_SPECS if s.name == "uia_dump")
    assert set(dump_spec.args_schema["required"]) == {"app"}


def test_mcp_specs_match_framework_neutral_specs() -> None:
    # The MCP surface must stay in lockstep with the framework-neutral specs
    # (the same ones LangChain / AutoGen / CrewAI register), so a tool listed
    # over MCP has the identical schema as every other framework.
    neutral = {s.name: s for s in (dump_tool(), run_tool())}
    for spec in MCP_TOOL_SPECS:
        assert spec.name in neutral
        assert spec.args_schema == neutral[spec.name].args_schema


def _mcp_installed() -> bool:
    return importlib.util.find_spec("mcp") is not None


@pytest.mark.skipif(_mcp_installed(), reason="mcp extra is installed")
def test_building_server_without_extra_raises_clear_error() -> None:
    with pytest.raises(MCPUnavailable, match=r"uia-agent\[mcp\]"):
        build_server()


@pytest.mark.skipif(not _mcp_installed(), reason="mcp extra not installed")
def test_building_server_with_extra_succeeds() -> None:  # pragma: no cover
    server = build_server()
    assert server is not None
