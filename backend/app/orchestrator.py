"""Chains all eight pipeline stages together: Data Profiler -> Analysis
Planner -> Data Analyst -> Evidence Builder -> Verification Agent ->
Insight Synthesizer -> Recommendation Engine -> Report Generator.

This module is the single place that owns stage ordering, so the
LLM/deterministic-code split documented in docs/architecture.md is visible
in one read-through rather than scattered across call sites. The optional
`on_stage` callback lets a caller (the FastAPI layer, Phase 9) persist each
stage's output as it completes, which is what powers progress polling.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

import pandas as pd

from app.agents.analyst import AnalystRun, run_data_analyst
from app.agents.evidence_builder import build_evidence
from app.agents.planner import build_analysis_plan
from app.agents.recommender import build_recommendations
from app.agents.report_generator import build_report
from app.agents.synthesizer import build_insights
from app.agents.verifier import verify_claim
from app.llm.client import LLMClient
from app.models.plan import AnalysisPlan
from app.models.profile import DatasetProfile
from app.models.report import Report
from app.models.verification import VerificationResult
from app.profiling.profiler import build_dataset_profile

OnStage = Callable[[str, Any], None]


@dataclass
class PipelineRun:
    profile: DatasetProfile
    plan: AnalysisPlan
    analyst_run: AnalystRun
    verification_results: list[VerificationResult] = field(default_factory=list)
    report: Report | None = None


def run_full_pipeline(
    df: pd.DataFrame,
    question: str,
    llm_client: LLMClient,
    dataset_name: str = "",
    on_stage: OnStage | None = None,
) -> PipelineRun:
    def emit(stage_name: str, payload: Any) -> None:
        if on_stage is not None:
            on_stage(stage_name, payload)

    profile = build_dataset_profile(df, dataset_name=dataset_name)
    emit("profile", profile)

    plan = build_analysis_plan(profile, question, llm_client)
    emit("plan", plan)

    analyst_run = run_data_analyst(df, plan, llm_client)
    emit("analyst", analyst_run.calculation_results)

    evidence_items = build_evidence(analyst_run.calculation_results, question, llm_client)
    emit("evidence", [item.evidence for item in evidence_items])

    verification_results = [
        verify_claim(df, item.evidence, item.calculation, llm_client, dataset_warnings=profile.warnings)
        for item in evidence_items
    ]
    emit("verification", verification_results)

    insights = build_insights(verification_results, question, llm_client)
    emit("insights", insights)

    recommendations = build_recommendations(insights, question, llm_client)
    emit("recommendations", recommendations)

    report = build_report(
        question,
        profile,
        analyst_run.calculation_results,
        insights,
        recommendations,
        verification_results,
        llm_client,
    )
    emit("report", report)

    return PipelineRun(
        profile=profile,
        plan=plan,
        analyst_run=analyst_run,
        verification_results=verification_results,
        report=report,
    )
