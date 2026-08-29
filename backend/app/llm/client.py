"""Thin wrapper over the Gemini API (generativelanguage.googleapis.com).

Originally written against the Anthropic Messages API; ported to Gemini
because the project's only available credential was a Gemini key, not an
Anthropic one (see docs/improvement-changelog.md for the full story). The
`LLMClient.create_message()` signature and `LLMResponse`/`ToolCallRequest`/
`LLMUsage` shapes are unchanged from the Anthropic version on purpose: every
one of the 7 agent modules built against this interface needed zero code
changes for the port, and all ~130 tests that inject a fake client under
`tests/unit/fakes.py` (itself unchanged) still pass, because the fake/real
seam sits at "system + Anthropic-shaped messages/tools/tool_choice in,
Anthropic-shaped content/usage/stop_reason out" -- translation to and from
Gemini's actual wire format happens only inside `_GeminiClient` below, which
only the real (non-injected) path ever exercises.

Verified empirically against the live Gemini API before writing this file
(raw curl, not guessed from training data): system_instruction/contents/
tools/tool_config field names and shapes, that function-call parts must
have their `thoughtSignature` echoed back verbatim when replayed into
history (Gemini 3's requirement, undocumented in stale training data), that
function responses go on a `role: "user"` turn keyed by function `name`
(not by an id Anthropic-style), and that `thinkingConfig: {thinkingLevel:
"LOW"}` is the lowest available setting (there is no full "off").
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

GEMINI_API_BASE_URL = "https://generativelanguage.googleapis.com"

# Verified empirically (live 429 responses) against the free tier: a
# per-minute-per-model quota of 15 requests on gemini-3.5-flash-lite, which
# an 8+ call pipeline run can plausibly burst past on its own. Retrying a
# bounded number of times, honoring the server's own retryDelay, is the
# correct response to a rolling per-minute window.
_MAX_RATE_LIMIT_RETRIES = 4


def _retry_delay_seconds(response: httpx.Response, attempt: int) -> float:
    try:
        data = response.json()
        for detail in data.get("error", {}).get("details", []):
            if str(detail.get("@type", "")).endswith("RetryInfo"):
                delay_str = str(detail.get("retryDelay", ""))
                if delay_str.endswith("s"):
                    return float(delay_str[:-1]) + 0.5  # small buffer over what the server asked for
    except (ValueError, KeyError):
        pass
    return min(2**attempt * 2, 30)

# Per-model $ per million tokens. Left EMPTY rather than filled with guessed
# numbers: ai.google.dev and cloud.google.com's pricing pages are both
# blocked by this environment's network egress policy (confirmed via direct
# curl -- a 403 on the CONNECT, not a timeout). estimate_cost_usd() already
# returns 0.0 for any model not listed here, so cost tracking degrades to
# "unknown" rather than reporting a fabricated dollar amount. Real token
# counts (input_tokens/output_tokens) are unaffected -- only the $
# conversion is. Fill in real per-model rates from
# https://ai.google.dev/gemini-api/docs/pricing once that's reachable.
MODEL_PRICING_PER_MTOK: dict[str, dict[str, float]] = {}


def estimate_cost_usd(model: str, input_tokens: int, output_tokens: int) -> float:
    pricing = MODEL_PRICING_PER_MTOK.get(model)
    if pricing is None:
        return 0.0
    cost = input_tokens / 1_000_000 * pricing["input"] + output_tokens / 1_000_000 * pricing["output"]
    return round(cost, 6)


@dataclass
class LLMUsage:
    input_tokens: int
    output_tokens: int
    cost_usd: float


@dataclass
class ToolCallRequest:
    id: str
    name: str
    input: dict[str, Any]


@dataclass
class LLMResponse:
    text: str
    tool_calls: list[ToolCallRequest]
    stop_reason: str
    usage: LLMUsage
    latency_seconds: float
    raw: Any = field(default=None, repr=False)


# --------------------------------------------------------------------------
# Gemini wire-format translation. Only ever exercised by the real (non-fake)
# path -- see tests/unit/test_gemini_translation.py for dedicated coverage
# of these functions in isolation.
# --------------------------------------------------------------------------


def _block_get(block: Any, key: str, default: Any = None) -> Any:
    """Reads `key` off a block whether it's a plain dict (freshly built by
    agent code, e.g. a tool_result) or a `_GeminiToolUseBlock`/
    `_GeminiTextBlock` instance (replayed from a prior response's
    `raw.content`, which is how analyst.py's multi-turn loop re-sends the
    model's own previous turn)."""
    if isinstance(block, dict):
        return block.get(key, default)
    return getattr(block, key, default)


def _messages_to_gemini_contents(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    contents: list[dict[str, Any]] = []
    tool_call_meta: dict[str, dict[str, Any]] = {}

    for msg in messages:
        role = "model" if msg["role"] == "assistant" else "user"
        content = msg["content"]
        parts: list[dict[str, Any]] = []

        if isinstance(content, str):
            parts.append({"text": content})
        else:
            for block in content:
                btype = _block_get(block, "type")
                signature = _block_get(block, "thought_signature")

                if btype == "text":
                    part: dict[str, Any] = {"text": _block_get(block, "text")}
                    if signature:
                        part["thoughtSignature"] = signature
                    parts.append(part)

                elif btype == "tool_use":
                    block_id = _block_get(block, "id")
                    name = _block_get(block, "name")
                    part = {"functionCall": {"name": name, "args": _block_get(block, "input") or {}}}
                    if signature:
                        part["thoughtSignature"] = signature
                    tool_call_meta[block_id] = {"name": name}
                    parts.append(part)

                elif btype == "tool_result":
                    meta = tool_call_meta.get(_block_get(block, "tool_use_id"), {})
                    payload = _block_get(block, "content")
                    if _block_get(block, "is_error"):
                        # Error content is always a plain message string (see
                        # analyst.py's `str(exc)`), never JSON -- wrap it
                        # directly rather than attempting to parse it first.
                        payload = {"error": payload}
                    elif isinstance(payload, str):
                        try:
                            payload = json.loads(payload)
                        except json.JSONDecodeError:
                            payload = {"result": payload}
                    parts.append({"functionResponse": {"name": meta.get("name", ""), "response": payload}})

        contents.append({"role": role, "parts": parts})

    return contents


def _tool_to_gemini(tool: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": tool["name"],
        "description": tool.get("description", ""),
        "parameters": tool["input_schema"],
    }


def _tool_choice_to_gemini(tool_choice: dict[str, Any]) -> dict[str, Any]:
    config: dict[str, Any] = {"mode": "ANY"}
    name = tool_choice.get("name")
    if name:
        config["allowed_function_names"] = [name]
    return {"function_calling_config": config}


@dataclass
class _GeminiTextBlock:
    text: str
    thought_signature: str | None = None
    type: str = "text"


@dataclass
class _GeminiToolUseBlock:
    id: str
    name: str
    input: dict[str, Any]
    thought_signature: str | None = None
    type: str = "tool_use"


@dataclass
class _GeminiUsage:
    input_tokens: int
    output_tokens: int


@dataclass
class _GeminiMessageResult:
    content: list[Any]
    usage: _GeminiUsage
    stop_reason: str


def _parse_gemini_response(data: dict[str, Any]) -> _GeminiMessageResult:
    candidate = data["candidates"][0]
    parts = candidate.get("content", {}).get("parts") or []

    content_blocks: list[Any] = []
    has_tool_calls = False
    for i, part in enumerate(parts):
        signature = part.get("thoughtSignature")
        if "functionCall" in part:
            fc = part["functionCall"]
            call_id = fc.get("id") or f"call_{i}"
            content_blocks.append(
                _GeminiToolUseBlock(id=call_id, name=fc["name"], input=fc.get("args") or {}, thought_signature=signature)
            )
            has_tool_calls = True
        elif "text" in part:
            content_blocks.append(_GeminiTextBlock(text=part["text"], thought_signature=signature))

    finish_reason = candidate.get("finishReason", "STOP")
    if has_tool_calls:
        stop_reason = "tool_use"
    elif finish_reason == "MAX_TOKENS":
        stop_reason = "max_tokens"
    else:
        stop_reason = "end_turn"

    usage_meta = data.get("usageMetadata", {})
    usage = _GeminiUsage(
        input_tokens=usage_meta.get("promptTokenCount", 0),
        output_tokens=usage_meta.get("candidatesTokenCount", 0),
    )
    return _GeminiMessageResult(content=content_blocks, usage=usage, stop_reason=stop_reason)


class _GeminiMessagesAPI:
    def __init__(self, api_key: str, http_client: httpx.Client):
        self._api_key = api_key
        self._http = http_client

    def create(
        self,
        *,
        model: str,
        max_tokens: int,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        tool_choice: dict[str, Any] | None = None,
    ) -> _GeminiMessageResult:
        body: dict[str, Any] = {
            "contents": _messages_to_gemini_contents(messages),
            "generationConfig": {
                "maxOutputTokens": max_tokens,
                # "LOW" is the lowest thinking level Gemini 3 currently
                # accepts -- there is no value that disables thinking
                # entirely (verified: "OFF" is rejected with a 400).
                "thinkingConfig": {"thinkingLevel": "LOW"},
            },
        }
        if system:
            body["system_instruction"] = {"parts": [{"text": system}]}
        if tools:
            body["tools"] = [{"function_declarations": [_tool_to_gemini(t) for t in tools]}]
        if tool_choice:
            body["tool_config"] = _tool_choice_to_gemini(tool_choice)

        url = f"/v1beta/models/{model}:generateContent"
        last_response = None
        for attempt in range(_MAX_RATE_LIMIT_RETRIES + 1):
            response = self._http.post(url, params={"key": self._api_key}, json=body)
            if response.status_code != 429:
                response.raise_for_status()
                return _parse_gemini_response(response.json())

            # Free-tier per-minute quota (verified empirically: 15 requests/
            # minute/model on gemini-3.5-flash-lite) -- a rolling window, so
            # honoring the server's own retryDelay and trying again is the
            # correct response, not a workaround. Only a per-DAY quota
            # (a different quotaId seen on gemini-3.6-flash's tiny preview
            # allowance) would make retrying pointless -- that case still
            # exhausts its retries here and raises, same as any other 429.
            last_response = response
            if attempt < _MAX_RATE_LIMIT_RETRIES:
                time.sleep(_retry_delay_seconds(response, attempt))

        last_response.raise_for_status()
        raise RuntimeError("unreachable: raise_for_status() always raises for a non-2xx response")


class _GeminiClient:
    def __init__(self, api_key: str):
        self.messages = _GeminiMessagesAPI(
            api_key, httpx.Client(base_url=GEMINI_API_BASE_URL, timeout=120.0)
        )


class LLMClient:
    def __init__(self, api_client: Any = None, model: str | None = None):
        self.model = model or os.environ.get("LLM_MODEL", "gemini-3.5-flash-lite")
        self._api_client = api_client

    def _client(self) -> Any:
        if self._api_client is None:
            api_key = os.environ.get("GEMINI_API_KEY")
            if not api_key:
                raise RuntimeError(
                    "GEMINI_API_KEY environment variable is not set. Get a key from "
                    "https://aistudio.google.com/apikey and set it before calling the LLM."
                )
            self._api_client = _GeminiClient(api_key)
        return self._api_client

    def create_message(
        self,
        *,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        tool_choice: dict[str, Any] | None = None,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        client = self._client()
        kwargs: dict[str, Any] = {
            "model": self.model,
            "max_tokens": max_tokens,
            "system": system,
            "messages": messages,
        }
        if tools:
            kwargs["tools"] = tools
        if tool_choice:
            kwargs["tool_choice"] = tool_choice

        start = time.monotonic()
        response = client.messages.create(**kwargs)
        latency = time.monotonic() - start

        text_parts: list[str] = []
        tool_calls: list[ToolCallRequest] = []
        for block in response.content:
            block_type = getattr(block, "type", None)
            if block_type == "text":
                text_parts.append(block.text)
            elif block_type == "tool_use":
                tool_calls.append(ToolCallRequest(id=block.id, name=block.name, input=block.input))

        usage = LLMUsage(
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            cost_usd=estimate_cost_usd(
                self.model, response.usage.input_tokens, response.usage.output_tokens
            ),
        )

        return LLMResponse(
            text="".join(text_parts),
            tool_calls=tool_calls,
            stop_reason=response.stop_reason,
            usage=usage,
            latency_seconds=latency,
            raw=response,
        )
