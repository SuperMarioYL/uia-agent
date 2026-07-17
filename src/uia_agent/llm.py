"""Thin shim over Anthropic + OpenAI structured-output APIs.

The LLM only needs to return one `Action` per turn. Both providers expose a
JSON-mode / tool-use surface that makes parsing deterministic; we use that
rather than free-text + regex.

Provider selection: env vars decide.
  - ANTHROPIC_API_KEY present  → Anthropic (default model: claude-sonnet-4-6)
  - OPENAI_API_KEY present     → OpenAI    (default model: gpt-4o-2024-11-20)
  - both present               → Anthropic wins unless UIA_AGENT_PROVIDER overrides
  - neither                    → RuntimeError at first call

Model overrides: UIA_AGENT_MODEL=... pins a specific model id.
"""

from __future__ import annotations

import json
import os
from typing import Any, Protocol

from .actions import Action

# OpenAI's strict structured-output mode requires *every* declared property to
# appear in `required`; the nullable `["string", "null"]` types below let the
# optional fields stay logically optional while satisfying that rule. Anthropic
# tool-use is permissive about this, so a single shared schema works for both.
ACTION_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["kind", "target_id", "text", "reason"],
    "properties": {
        "kind": {
            "type": "string",
            "enum": ["click", "type", "select", "expand", "key", "wait", "done"],
        },
        "target_id": {"type": ["string", "null"]},
        "text": {"type": ["string", "null"]},
        "reason": {"type": "string"},
    },
}


class LLMClient(Protocol):
    """The single method the agent loop calls each step."""

    def next_action(self, *, system: str, user: str) -> Action: ...


class AnthropicClient:
    """Anthropic Messages API with tool-use enforced structured output."""

    def __init__(self, *, model: str | None = None, max_tokens: int = 1024) -> None:
        try:
            from anthropic import Anthropic
        except ImportError as exc:
            raise RuntimeError(
                "anthropic package not installed; reinstall with "
                "`pip install uia-agent` (it is a core dependency) or "
                "`pip install anthropic>=0.40`"
            ) from exc
        self._client = Anthropic()
        self._model = model or os.getenv("UIA_AGENT_MODEL") or "claude-sonnet-4-6"
        self._max_tokens = max_tokens

    def next_action(self, *, system: str, user: str) -> Action:
        response = self._client.messages.create(
            model=self._model,
            max_tokens=self._max_tokens,
            system=system,
            tools=[
                {
                    "name": "emit_action",
                    "description": "Emit one Action against the UIA tree.",
                    "input_schema": ACTION_JSON_SCHEMA,
                }
            ],
            tool_choice={"type": "tool", "name": "emit_action"},
            messages=[{"role": "user", "content": user}],
        )
        for block in getattr(response, "content", []):
            if getattr(block, "type", None) == "tool_use":
                return Action.model_validate(block.input)
        raise RuntimeError("Anthropic response did not include the emit_action tool call")


class OpenAIClient:
    """OpenAI Chat Completions with JSON-schema structured output."""

    def __init__(self, *, model: str | None = None) -> None:
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError(
                "openai package not installed; reinstall with "
                "`pip install uia-agent` (it is a core dependency) or "
                "`pip install openai>=1.50`"
            ) from exc
        self._client = OpenAI()
        self._model = model or os.getenv("UIA_AGENT_MODEL") or "gpt-4o-2024-11-20"

    def next_action(self, *, system: str, user: str) -> Action:
        response = self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "Action",
                    "strict": True,
                    "schema": ACTION_JSON_SCHEMA,
                },
            },
        )
        payload = response.choices[0].message.content or "{}"
        return Action.model_validate(json.loads(payload))


def default_client() -> LLMClient:
    """Pick a provider based on environment; cheap to call once per run."""
    override = (os.getenv("UIA_AGENT_PROVIDER") or "").strip().lower()
    have_anthropic = bool(os.getenv("ANTHROPIC_API_KEY"))
    have_openai = bool(os.getenv("OPENAI_API_KEY"))

    if override == "anthropic":
        if not have_anthropic:
            raise RuntimeError("UIA_AGENT_PROVIDER=anthropic but ANTHROPIC_API_KEY is unset")
        return AnthropicClient()
    if override == "openai":
        if not have_openai:
            raise RuntimeError("UIA_AGENT_PROVIDER=openai but OPENAI_API_KEY is unset")
        return OpenAIClient()

    if have_anthropic:
        return AnthropicClient()
    if have_openai:
        return OpenAIClient()

    raise RuntimeError(
        "no LLM credentials found — set ANTHROPIC_API_KEY or OPENAI_API_KEY"
    )
