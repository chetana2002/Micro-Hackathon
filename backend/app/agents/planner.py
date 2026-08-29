"""Analysis Planner agent.

Takes a DatasetProfile + user question and produces a typed AnalysisPlan.
The LLM is forced (via tool_choice) to respond through a single
`submit_analysis_plan` tool whose schema enumerates only operations that
actually exist in the deterministic tool registry (Phase 3) — so an
invalid or hallucinated operation name is rejected here as a validation
error, before the Data Analyst stage ever tries to execute it.
"""
from __future__ import annotations

from app.llm.client import LLMClient
from app.models.plan import AnalysisPlan, AnalysisStep
from app.models.profile import DatasetProfile
from app.tools.registry import TOOL_REGISTRY

SYSTEM_PROMPT = (
    "You are a business data analysis planner. Given a dataset profile and a "
    "business question, propose an ordered list of analysis steps using only "
    "the available analysis operations. Each step must state which columns it "
    "targets and why it helps answer the question. Do not invent operations "
    "outside the provided list. If the question implies a causal claim (e.g. "
    "asks 'why'), include a step that checks whether the data actually "
    "supports a causal conclusion, not just a descriptive one."
)

PLAN_TOOL = {
    "name": "submit_analysis_plan",
    "description": "Submit the ordered list of analysis steps to execute against the dataset.",
    "input_schema": {
        "type": "object",
        "properties": {
            "steps": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "step_id": {"type": "integer"},
                        "operation": {"type": "string", "enum": sorted(TOOL_REGISTRY.keys())},
                        "rationale": {"type": "string"},
                        "target_columns": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["step_id", "operation", "rationale", "target_columns"],
                },
            }
        },
        "required": ["steps"],
    },
}


def _build_user_message(profile: DatasetProfile, question: str) -> str:
    return f"Dataset profile:\n{profile.model_dump_json(indent=2)}\n\nBusiness question: {question}"


def build_analysis_plan(profile: DatasetProfile, question: str, llm_client: LLMClient) -> AnalysisPlan:
    response = llm_client.create_message(
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": _build_user_message(profile, question)}],
        tools=[PLAN_TOOL],
        tool_choice={"type": "tool", "name": "submit_analysis_plan"},
        max_tokens=2048,
    )

    if not response.tool_calls:
        raise ValueError("Planner did not return a structured plan via submit_analysis_plan")

    raw_steps = response.tool_calls[0].input.get("steps", [])
    steps: list[AnalysisStep] = []
    for raw in raw_steps:
        if raw["operation"] not in TOOL_REGISTRY:
            raise ValueError(f"Planner proposed unknown operation '{raw['operation']}'")
        steps.append(AnalysisStep(**raw))

    if not steps:
        raise ValueError("Planner returned an empty plan")

    return AnalysisPlan(question=question, steps=steps)
