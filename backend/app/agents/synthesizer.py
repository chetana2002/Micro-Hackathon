"""Insight Synthesizer.

Only verification results with status VERIFIED or PARTIALLY_VERIFIED ever
reach the LLM here — UNSUPPORTED and CONTRADICTED claims are filtered out
by this code before the prompt is even built, so the synthesizer has no
opportunity to narrate a claim that failed verification. Each Insight's
`evidence` field is bound to the Evidence object from the referenced
VerificationResult, not re-described by the model.
"""
from __future__ import annotations

from app.llm.client import LLMClient
from app.models.insight import Insight
from app.models.verification import VerificationResult

SYSTEM_PROMPT = (
    "You are writing business insights for an analytics report. You will be "
    "given a numbered list of already-verified claims (each has a status of "
    "VERIFIED or PARTIALLY_VERIFIED — you do not need to re-judge them). For "
    "each claim worth surfacing to a business reader, submit an insight via "
    "submit_insights, referencing the verification_index it is built from. "
    "Write a specific, concrete finding and business_significance — avoid "
    "generic statements like 'sales should be improved'. If the underlying "
    "claim was only PARTIALLY_VERIFIED or carries known issues, say so "
    "explicitly in limitations rather than presenting it as fully settled."
)

INSIGHT_TOOL = {
    "name": "submit_insights",
    "description": "Submit one business insight per referenced verification result.",
    "input_schema": {
        "type": "object",
        "properties": {
            "insights": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "verification_index": {"type": "integer"},
                        "title": {"type": "string"},
                        "finding": {"type": "string"},
                        "business_significance": {"type": "string"},
                        "limitations": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": [
                        "verification_index", "title", "finding", "business_significance", "limitations",
                    ],
                },
            }
        },
        "required": ["insights"],
    },
}


def _format_verifications(results: list[VerificationResult]) -> str:
    lines = []
    for i, r in enumerate(results):
        lines.append(f"[{i}] status={r.status} confidence={r.confidence} claim={r.claim!r} issues={r.issues}")
    return "\n".join(lines)


def build_insights(
    verification_results: list[VerificationResult], question: str, llm_client: LLMClient
) -> list[Insight]:
    qualified = [r for r in verification_results if r.status in ("VERIFIED", "PARTIALLY_VERIFIED")]
    if not qualified:
        return []

    user_message = (
        f"Business question: {question}\n\n"
        f"Verified claims (0-indexed, already filtered to VERIFIED/PARTIALLY_VERIFIED):\n"
        f"{_format_verifications(qualified)}"
    )
    response = llm_client.create_message(
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_message}],
        tools=[INSIGHT_TOOL],
        tool_choice={"type": "tool", "name": "submit_insights"},
        max_tokens=2048,
    )

    if not response.tool_calls:
        raise ValueError("Insight Synthesizer did not return structured insights via submit_insights")

    raw_items = response.tool_calls[0].input.get("insights", [])
    insights: list[Insight] = []
    for item in raw_items:
        idx = item["verification_index"]
        if not (0 <= idx < len(qualified)):
            raise ValueError(f"Insight references invalid verification_index {idx}")
        vr = qualified[idx]
        limitations = list(item["limitations"])
        if vr.status == "PARTIALLY_VERIFIED":
            limitations.append(
                f"Underlying claim was only partially verified: {'; '.join(vr.issues) or 'see verification issues'}"
            )
        insights.append(
            Insight(
                title=item["title"],
                finding=item["finding"],
                evidence=[vr.evidence],
                business_significance=item["business_significance"],
                confidence=vr.confidence,
                limitations=limitations,
            )
        )
    return insights
