"""Regression tests for the OpenAI-wire adapter (waku/loop/models.py).

Two live bugs are pinned here, both surfaced with the default provider=openai
model gpt-5.6 (a reasoning model):

  1. Function tools over chat.completions require reasoning_effort='none', or
     gpt-5.x returns HTTP 400. So tool turns must carry that key.
  2. The max_tokens key-name fallback must fire ONLY when the endpoint rejects
     max_completion_tokens — a blanket except masked the real error above,
     re-surfacing it as a confusing "max_tokens not supported" message.

No network/API key needed: we test kwarg construction and the fallback branch
with a stubbed chat.completions.create.
"""

import pytest

from waku.loop.models import OpenAICompatClient

TOOLS = [{"name": "create_event", "description": "Create a calendar event",
          "input_schema": {"type": "object",
                           "properties": {"title": {"type": "string"}},
                           "required": ["title"]}}]


@pytest.fixture
def client():
    # constructing the client does not touch the network
    return OpenAICompatClient(api_key="sk-test", base_url=None)


def test_tool_turn_disables_reasoning_and_uses_completion_tokens(client):
    kwargs = client._to_openai(
        model="gpt-5.6", messages=[{"role": "user", "content": "hi"}],
        max_tokens=256, tools=TOOLS)
    assert kwargs["reasoning_effort"] == "none"
    assert kwargs["max_completion_tokens"] == 256
    assert "max_tokens" not in kwargs


def test_non_tool_turn_keeps_reasoning_on(client):
    kwargs = client._to_openai(
        model="gpt-5.6", messages=[{"role": "user", "content": "hi"}],
        max_tokens=256)
    assert "reasoning_effort" not in kwargs  # non-tool turns may still reason


def test_fallback_reraises_unrelated_errors(client):
    """A failure NOT about max_completion_tokens must surface, not be masked
    by a retry with max_tokens."""
    real = RuntimeError("reasoning_effort not supported with function tools")

    def always_fail(**_):
        raise real

    client._client.chat.completions.create = always_fail
    with pytest.raises(RuntimeError, match="reasoning_effort"):
        client._call({"model": "gpt-5.6", "max_completion_tokens": 16})


def test_fallback_swaps_key_only_on_completion_tokens_error(client):
    """When the endpoint rejects max_completion_tokens, retry with max_tokens."""
    calls = []

    def create(**kwargs):
        calls.append(kwargs)
        if "max_completion_tokens" in kwargs:
            raise RuntimeError("Unknown parameter: 'max_completion_tokens'.")
        return "ok"

    client._client.chat.completions.create = create
    result = client._call({"model": "old-model", "max_completion_tokens": 16})
    assert result == "ok"
    assert calls[0]["max_completion_tokens"] == 16          # first try
    assert calls[1]["max_tokens"] == 16                     # retry with old key
    assert "max_completion_tokens" not in calls[1]
