"""Regression guard for the OpenAI strict-mode structured-output schema.

OpenAI's `json_schema` with `strict: true` requires that *every* declared
property appear in `required`; otherwise the first call returns a 400
`invalid_schema` and the whole OpenAI provider path is dead. v0.1 only listed
`["kind", "reason"]`, omitting `target_id` and `text`. These tests pin the fix.
"""

from __future__ import annotations

import json

from uia_agent.actions import Action
from uia_agent.llm import ACTION_JSON_SCHEMA, OpenAIClient


def test_strict_schema_lists_every_property_in_required() -> None:
    props = set(ACTION_JSON_SCHEMA["properties"])
    required = set(ACTION_JSON_SCHEMA["required"])
    assert props == required, (
        "OpenAI strict json_schema needs every property in `required`; "
        f"missing from required: {props - required}"
    )


def test_required_is_the_expected_action_field_set() -> None:
    assert set(ACTION_JSON_SCHEMA["required"]) == {"kind", "target_id", "text", "reason"}


def test_optional_fields_are_nullable_so_strict_mode_accepts_them() -> None:
    # target_id and text are logically optional; under strict mode they stay in
    # `required` but must accept null.
    for field in ("target_id", "text"):
        assert ACTION_JSON_SCHEMA["properties"][field]["type"] == ["string", "null"]


def test_schema_round_trips_through_the_action_model() -> None:
    # A payload that satisfies the strict schema (all keys present, optionals
    # null) must validate into an Action.
    payload = {"kind": "done", "target_id": None, "text": None, "reason": "finished"}
    action = Action.model_validate(payload)
    assert action.kind == "done"


def test_openai_client_sends_strict_schema_without_400() -> None:
    """Mock the OpenAI SDK and assert the call ships the corrected strict schema
    and parses the response — i.e. the request that used to 400 now succeeds."""

    captured: dict[str, object] = {}

    class _Message:
        content = json.dumps(
            {"kind": "click", "target_id": "abc123", "text": None, "reason": "press OK"}
        )

    class _Choice:
        message = _Message()

    class _Response:
        choices = [_Choice()]

    class _Completions:
        def create(self, **kwargs: object) -> _Response:
            captured.update(kwargs)
            return _Response()

    class _Chat:
        completions = _Completions()

    class _FakeOpenAI:
        chat = _Chat()

    client = OpenAIClient.__new__(OpenAIClient)
    client._client = _FakeOpenAI()  # type: ignore[attr-defined]
    client._model = "gpt-4o-2024-11-20"  # type: ignore[attr-defined]

    action = client.next_action(system="sys", user="usr")

    assert action.kind == "click"
    assert action.target_id == "abc123"
    rf = captured["response_format"]
    assert isinstance(rf, dict)
    schema = rf["json_schema"]["schema"]  # type: ignore[index]
    assert rf["json_schema"]["strict"] is True  # type: ignore[index]
    assert set(schema["required"]) == set(schema["properties"])  # type: ignore[index]
