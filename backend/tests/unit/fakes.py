"""Fakes standing in for the Anthropic SDK so LLM-call sites are testable
without network access or an API key. Shapes mirror what
`anthropic.Anthropic().messages.create(...)` returns closely enough for
app.llm.client.LLMClient to parse.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class FakeTextBlock:
    text: str
    type: str = "text"


@dataclass
class FakeToolUseBlock:
    id: str
    name: str
    input: dict[str, Any]
    type: str = "tool_use"


@dataclass
class FakeUsage:
    input_tokens: int
    output_tokens: int


@dataclass
class FakeMessage:
    content: list[Any]
    usage: FakeUsage
    stop_reason: str = "end_turn"


class FakeMessages:
    def __init__(self, responses: list[FakeMessage]):
        self._responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> FakeMessage:
        self.calls.append(kwargs)
        if not self._responses:
            raise AssertionError("FakeMessages.create called more times than responses provided")
        return self._responses.pop(0)


@dataclass
class FakeAnthropicClient:
    messages: FakeMessages

    @classmethod
    def with_responses(cls, responses: list[FakeMessage]) -> "FakeAnthropicClient":
        return cls(messages=FakeMessages(responses))
