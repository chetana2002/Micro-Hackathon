"""Report Generator.

Assembles the final business report. The LLM contributes only the
executive summary's prose; every structural section — dataset overview,
data quality warnings, key findings, evidence, charts, recommendations,
limitations, and open questions — is assembled by this code directly from
the typed objects produced by earlier stages. Charts come from
app.charts.chart_builder acting on CalculationResult data, never invented
by the model.
"""
from __future__ import annotations

from app.llm.client import LLMClient
from app.charts.chart_builder import build_chart
from app.models.calculation import CalculationResult
from app.models.evidence import Evidence
from app.models.insight import Insight
from app.models.profile import DatasetProfile
from app.models.recommendation import Recommendation
from app.models.report import Report
from app.models.verification import VerificationResult

SYSTEM_PROMPT = (
    "You are writing the executive summary for a business analytics report. "
    "You will be given the business question, the key findings, and the "
    "recommendations, all already verified. Write 2-4 sentences a busy "
    "executive could read in isolation. State only what the findings "
    "actually support — if the findings are descriptive rather than causal, "
    "the summary must not claim a cause. Respond with plain text only, no "
    "headings or bullet points."
)


def _open_questions(verification_results: list[VerificationResult]) -> list[str]:
    return [
        f"{vr.claim} (status: {vr.status}; "
        f"{'; '.join(vr.issues) if vr.issues else 'insufficient evidence'})"
        for vr in verification_results
        if vr.status in ("UNSUPPORTED", "CONTRADICTED")
    ]


def _limitations(insights: list[Insight]) -> list[str]:
    seen: list[str] = []
    for ins in insights:
        for lim in ins.limitations:
            if lim not in seen:
                seen.append(lim)
    return seen


def _dedup_evidence(insights: list[Insight]) -> list[Evidence]:
    seen_ids: set[str] = set()
    result: list[Evidence] = []
    for ins in insights:
        for e in ins.evidence:
            if e.evidence_id not in seen_ids:
                seen_ids.add(e.evidence_id)
                result.append(e)
    return result


def build_report(
    question: str,
    profile: DatasetProfile,
    calculation_results: list[CalculationResult],
    insights: list[Insight],
    recommendations: list[Recommendation],
    verification_results: list[VerificationResult],
    llm_client: LLMClient,
) -> Report:
    charts = [c for c in (build_chart(calc) for calc in calculation_results) if c is not None]

    findings_text = "\n".join(f"- {i.title}: {i.finding}" for i in insights) or "(no verified findings)"
    recs_text = "\n".join(f"- {r.recommendation}" for r in recommendations) or "(no recommendations)"
    user_message = (
        f"Business question: {question}\n\nKey findings:\n{findings_text}\n\nRecommendations:\n{recs_text}"
    )
    response = llm_client.create_message(
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_message}],
        max_tokens=512,
    )

    return Report(
        question=question,
        executive_summary=response.text,
        dataset_overview=profile,
        data_quality_warnings=profile.warnings,
        key_findings=insights,
        evidence=_dedup_evidence(insights),
        charts=charts,
        recommendations=recommendations,
        limitations=_limitations(insights),
        open_questions=_open_questions(verification_results),
    )
