import json

import pandas as pd

from app.agents.analyst import MAX_TURNS, run_data_analyst
from app.llm.client import LLMClient
from app.models.plan import AnalysisPlan, AnalysisStep
from app.tools.registry import TOOL_REGISTRY
from app.tools.schemas import TOOL_SCHEMA_NAMES
from tests.unit.fakes import FakeAnthropicClient, FakeMessage, FakeTextBlock, FakeToolUseBlock, FakeUsage


def _df():
    return pd.DataFrame(
        {
            "region": ["North", "South", "North"],
            "revenue": [1000, 800, 900],
        }
    )


def _plan():
    return AnalysisPlan(
        question="How much revenue did North generate?",
        steps=[
            AnalysisStep(
                step_id=1, operation="calculate_sum", rationale="Total North revenue.", target_columns=["revenue"]
            )
        ],
    )


def test_tool_schema_names_match_registry():
    assert TOOL_SCHEMA_NAMES == set(TOOL_REGISTRY.keys())


def test_single_tool_call_then_final_summary():
    fake = FakeAnthropicClient.with_responses(
        [
            FakeMessage(
                content=[
                    FakeToolUseBlock(
                        id="tu_1",
                        name="calculate_sum",
                        input={"column": "revenue", "filters": [{"column": "region", "op": "==", "value": "North"}]},
                    )
                ],
                usage=FakeUsage(300, 50),
                stop_reason="tool_use",
            ),
            FakeMessage(
                content=[FakeTextBlock(text="North generated 1900 in revenue.")],
                usage=FakeUsage(400, 80),
                stop_reason="end_turn",
            ),
        ]
    )
    client = LLMClient(api_client=fake, model="gemini-3.6-flash")

    run = run_data_analyst(_df(), _plan(), client)

    assert run.turns == 2
    assert run.final_text == "North generated 1900 in revenue."
    assert len(run.calculation_results) == 1
    assert run.calculation_results[0].result == 1900.0
    assert not run.hit_max_turns

    # The second call's messages must include a tool_result referencing the
    # exact tool_use_id issued in the first response.
    second_call = fake.messages.calls[1]
    tool_result_message = second_call["messages"][-1]
    assert tool_result_message["role"] == "user"
    assert tool_result_message["content"][0]["tool_use_id"] == "tu_1"
    payload = json.loads(tool_result_message["content"][0]["content"])
    assert payload["result"] == 1900.0


def test_parallel_tool_calls_in_one_turn():
    fake = FakeAnthropicClient.with_responses(
        [
            FakeMessage(
                content=[
                    FakeToolUseBlock(id="tu_1", name="calculate_sum", input={"column": "revenue"}),
                    FakeToolUseBlock(id="tu_2", name="calculate_average", input={"column": "revenue"}),
                ],
                usage=FakeUsage(300, 50),
                stop_reason="tool_use",
            ),
            FakeMessage(content=[FakeTextBlock(text="done")], usage=FakeUsage(100, 20), stop_reason="end_turn"),
        ]
    )
    client = LLMClient(api_client=fake, model="gemini-3.6-flash")

    run = run_data_analyst(_df(), _plan(), client)

    assert len(run.calculation_results) == 2
    second_call = fake.messages.calls[1]
    tool_result_message = second_call["messages"][-1]
    assert len(tool_result_message["content"]) == 2  # both results in a single user message


def test_unknown_tool_name_surfaces_as_error_result_not_a_crash():
    fake = FakeAnthropicClient.with_responses(
        [
            FakeMessage(
                content=[FakeToolUseBlock(id="tu_1", name="run_arbitrary_python", input={})],
                usage=FakeUsage(10, 10),
                stop_reason="tool_use",
            ),
            FakeMessage(content=[FakeTextBlock(text="ok")], usage=FakeUsage(10, 10), stop_reason="end_turn"),
        ]
    )
    client = LLMClient(api_client=fake, model="gemini-3.6-flash")

    run = run_data_analyst(_df(), _plan(), client)

    assert run.calculation_results == []
    second_call = fake.messages.calls[1]
    tool_result = second_call["messages"][-1]["content"][0]
    assert tool_result["is_error"] is True
    assert "unknown tool" in tool_result["content"]


def test_hits_max_turns_without_infinite_looping():
    responses = [
        FakeMessage(
            content=[FakeToolUseBlock(id=f"tu_{i}", name="calculate_sum", input={"column": "revenue"})],
            usage=FakeUsage(10, 10),
            stop_reason="tool_use",
        )
        for i in range(MAX_TURNS)
    ]
    fake = FakeAnthropicClient.with_responses(responses)
    client = LLMClient(api_client=fake, model="gemini-3.6-flash")

    run = run_data_analyst(_df(), _plan(), client)

    assert run.turns == MAX_TURNS
    assert run.hit_max_turns is True
    assert len(fake.messages.calls) == MAX_TURNS
