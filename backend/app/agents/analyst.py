"""Data Analyst agent.

Executes an AnalysisPlan by running a Claude tool-use loop against the full
deterministic tool registry (Phase 3). The model chooses which registered
tool to call and with what arguments; this code is the only thing that
ever touches the DataFrame. Every tool call becomes a CalculationResult,
and every one of those — not just the model's final summary text — is
returned to later stages (Evidence Builder, Verification). There is no
code path here that executes model-generated code.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from app.llm.client import LLMClient
from app.models.calculation import CalculationResult, FilterSpec
from app.models.plan import AnalysisPlan
from app.tools.registry import TOOL_REGISTRY
from app.tools.schemas import TOOL_SCHEMAS

SYSTEM_PROMPT = (
    "You are a data analyst executing a pre-approved analysis plan. For each "
    "step, call the most appropriate tool from those provided. You may call "
    "multiple tools across turns. When you have enough results to address "
    "every step, stop calling tools and summarize what you found in plain "
    "text, referencing only the tool results you were given — never invent "
    "a number that did not come from a tool result."
)

MAX_TURNS = 8


@dataclass
class AnalystRun:
    calculation_results: list[CalculationResult] = field(default_factory=list)
    final_text: str = ""
    turns: int = 0
    hit_max_turns: bool = False


def _execute_tool(df: pd.DataFrame, name: str, raw_input: dict[str, Any]) -> CalculationResult:
    if name not in TOOL_REGISTRY:
        raise ValueError(f"Model requested unknown tool '{name}'")
    fn = TOOL_REGISTRY[name]
    kwargs = dict(raw_input)
    if kwargs.get("filters") is not None:
        kwargs["filters"] = [FilterSpec(**f) for f in kwargs["filters"]]
    if name == "calculate_percentage_change":
        return fn(**kwargs)
    return fn(df, **kwargs)


def run_data_analyst(df: pd.DataFrame, plan: AnalysisPlan, llm_client: LLMClient) -> AnalystRun:
    messages: list[dict[str, Any]] = [
        {
            "role": "user",
            "content": (
                "Analysis plan (already approved, execute it faithfully):\n"
                f"{plan.model_dump_json(indent=2)}\n\n"
                "Execute it using the available tools."
            ),
        }
    ]
    run = AnalystRun()

    for _ in range(MAX_TURNS):
        run.turns += 1
        response = llm_client.create_message(
            system=SYSTEM_PROMPT, messages=messages, tools=TOOL_SCHEMAS, max_tokens=4096
        )

        if response.stop_reason != "tool_use" or not response.tool_calls:
            run.final_text = response.text
            return run

        # Echo the model's own content blocks back verbatim as the assistant
        # turn (mirrors the documented tool-use replay pattern) so any text the
        # model produced alongside its tool calls is preserved in history.
        messages.append({"role": "assistant", "content": response.raw.content})

        tool_result_blocks = []
        for tc in response.tool_calls:
            try:
                result = _execute_tool(df, tc.name, tc.input)
                run.calculation_results.append(result)
                tool_result_blocks.append(
                    {"type": "tool_result", "tool_use_id": tc.id, "content": result.model_dump_json()}
                )
            except Exception as exc:  # noqa: BLE001 - surfaced to the model, not swallowed
                tool_result_blocks.append(
                    {"type": "tool_result", "tool_use_id": tc.id, "content": str(exc), "is_error": True}
                )
        messages.append({"role": "user", "content": tool_result_blocks})

    run.hit_max_turns = True
    run.final_text = "(Data Analyst reached the maximum number of tool-use turns without a final summary.)"
    return run
