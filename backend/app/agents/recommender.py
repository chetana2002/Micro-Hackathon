"""Recommendation Engine.

Recommendations are generated only from Insights already synthesized from
verified claims — there is no path for a recommendation to reference
evidence that was never bound to a verified insight. `supporting_evidence`
is gathered from the referenced insight(s) by this code, not restated by
the model.
"""
from __future__ import annotations

from app.llm.client import LLMClient
from app.models.insight import Insight
from app.models.recommendation import Recommendation

SYSTEM_PROMPT = (
    "You are writing business recommendations for an analytics report. You "
    "will be given a numbered list of already-synthesized insights. For each "
    "recommendation worth making, submit it via submit_recommendations, "
    "referencing the insight_indices it is grounded in. Every recommendation "
    "must state an explicit uncertainty and a concrete next_investigation — "
    "do not present a recommendation as risk-free, and do not recommend "
    "action based on a correlation as though it were a proven cause."
)

RECOMMENDATION_TOOL = {
    "name": "submit_recommendations",
    "description": "Submit business recommendations grounded in the given insights.",
    "input_schema": {
        "type": "object",
        "properties": {
            "recommendations": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "insight_indices": {"type": "array", "items": {"type": "integer"}},
                        "recommendation": {"type": "string"},
                        "expected_impact": {"type": "string"},
                        "uncertainty": {"type": "string"},
                        "next_investigation": {"type": "string"},
                    },
                    "required": [
                        "insight_indices", "recommendation", "expected_impact",
                        "uncertainty", "next_investigation",
                    ],
                },
            }
        },
        "required": ["recommendations"],
    },
}


def _format_insights(insights: list[Insight]) -> str:
    lines = []
    for i, ins in enumerate(insights):
        lines.append(f"[{i}] title={ins.title!r} finding={ins.finding!r} confidence={ins.confidence}")
    return "\n".join(lines)


def build_recommendations(insights: list[Insight], question: str, llm_client: LLMClient) -> list[Recommendation]:
    if not insights:
        return []

    user_message = f"Business question: {question}\n\nInsights (0-indexed):\n{_format_insights(insights)}"
    response = llm_client.create_message(
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_message}],
        tools=[RECOMMENDATION_TOOL],
        tool_choice={"type": "tool", "name": "submit_recommendations"},
        max_tokens=2048,
    )

    if not response.tool_calls:
        raise ValueError("Recommendation Engine did not return structured recommendations via submit_recommendations")

    raw_items = response.tool_calls[0].input.get("recommendations", [])
    recommendations: list[Recommendation] = []
    for item in raw_items:
        indices = item["insight_indices"]
        for idx in indices:
            if not (0 <= idx < len(insights)):
                raise ValueError(f"Recommendation references invalid insight_index {idx}")
        supporting_evidence = [e for idx in indices for e in insights[idx].evidence]
        recommendations.append(
            Recommendation(
                recommendation=item["recommendation"],
                supporting_evidence=supporting_evidence,
                expected_impact=item["expected_impact"],
                uncertainty=item["uncertainty"],
                next_investigation=item["next_investigation"],
            )
        )
    return recommendations
