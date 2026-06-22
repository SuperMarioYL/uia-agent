"""Framework adapter layer (m4).

The core must stay dependency-free: importing the adapters (and even the
LangChain wrapper module) must NOT require LangChain. Constructing a LangChain
tool without the extra installed must fail with a clear, typed error — not an
opaque ImportError.
"""

from __future__ import annotations

import importlib

import pytest

from uia_agent.adapters import UiaToolSpec, dump_tool, run_tool
from uia_agent.adapters.langchain_tool import (
    RUN_TOOL_SPEC,
    LangChainUnavailable,
    UiaRunTool,
    make_langchain_tools,
)


def test_specs_expose_run_and_dump_schemas() -> None:
    run_spec = run_tool()
    dump_spec = dump_tool()
    assert isinstance(run_spec, UiaToolSpec)
    assert run_spec.name == "uia_run"
    assert dump_spec.name == "uia_dump"
    # The run schema carries the full argument contract.
    assert set(run_spec.args_schema["required"]) == {"app", "instruction"}
    assert "max_steps" in run_spec.args_schema["properties"]


def test_run_tool_spec_importable_without_langchain() -> None:
    # The module-level spec exists even without the extra; this is the
    # "imports under [langchain]" smoke check from the milestone, and it holds
    # regardless of whether LangChain happens to be installed.
    assert RUN_TOOL_SPEC.name == "uia_run"
    assert set(RUN_TOOL_SPEC.args_schema["required"]) == {"app", "instruction"}


def _langchain_installed() -> bool:
    return importlib.util.find_spec("langchain_core") is not None or (
        importlib.util.find_spec("langchain") is not None
    )


@pytest.mark.skipif(_langchain_installed(), reason="langchain extra is installed")
def test_building_tool_without_extra_raises_clear_error() -> None:
    with pytest.raises(LangChainUnavailable, match=r"uia-agent\[langchain\]"):
        UiaRunTool()
    with pytest.raises(LangChainUnavailable):
        make_langchain_tools()


@pytest.mark.skipif(not _langchain_installed(), reason="langchain extra not installed")
def test_building_tool_with_extra_exposes_run_schema() -> None:  # pragma: no cover
    tool = UiaRunTool()
    assert tool.name == "uia_run"
