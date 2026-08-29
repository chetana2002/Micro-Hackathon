from pathlib import Path

import pandas as pd

from app.llm.client import LLMClient
from app.orchestrator import run_full_pipeline
from tests.unit.fakes import FakeAnthropicClient, FakeMessage, FakeTextBlock, FakeToolUseBlock, FakeUsage

DATASETS_DIR = Path(__file__).resolve().parent.parent.parent.parent / "datasets"


def test_full_eight_stage_pipeline_on_real_dataset_with_scripted_llm():
    df = pd.read_csv(DATASETS_DIR / "01_sales_decline" / "data.csv")

    fake = FakeAnthropicClient.with_responses(
        [
            # 1. Planner: forced tool call producing one plan step.
            FakeMessage(
                content=[
                    FakeToolUseBlock(
                        id="plan_1",
                        name="submit_analysis_plan",
                        input={
                            "steps": [
                                {
                                    "step_id": 1,
                                    "operation": "compare_periods",
                                    "rationale": "Compare Q1 vs Q2 2024 revenue.",
                                    "target_columns": ["date", "revenue"],
                                }
                            ]
                        },
                    )
                ],
                usage=FakeUsage(500, 100),
                stop_reason="tool_use",
            ),
            # 2. Analyst turn 1: calls compare_periods.
            FakeMessage(
                content=[
                    FakeToolUseBlock(
                        id="tu_1",
                        name="compare_periods",
                        input={
                            "date_column": "date",
                            "value_column": "revenue",
                            "period_a": ["2024-01-01", "2024-03-31"],
                            "period_b": ["2024-04-01", "2024-06-30"],
                        },
                    )
                ],
                usage=FakeUsage(300, 60),
                stop_reason="tool_use",
            ),
            # 3. Analyst turn 2: final summary, no more tool calls.
            FakeMessage(
                content=[FakeTextBlock(text="Revenue declined from Q1 to Q2 2024.")],
                usage=FakeUsage(200, 50),
                stop_reason="end_turn",
            ),
            # 4. Evidence Builder: binds one claim to calculation index 0.
            FakeMessage(
                content=[
                    FakeToolUseBlock(
                        id="ev_1",
                        name="submit_evidence",
                        input={
                            "evidence_items": [
                                {
                                    "claim": "Total revenue declined from Q1 2024 to Q2 2024.",
                                    "calculation_index": 0,
                                    "confidence": 0.9,
                                }
                            ]
                        },
                    )
                ],
                usage=FakeUsage(200, 50),
                stop_reason="tool_use",
            ),
            # 5. Verification: non-causal claim, LLM verdict VERIFIED.
            FakeMessage(
                content=[
                    FakeToolUseBlock(
                        id="ver_1",
                        name="submit_verification",
                        input={"status": "VERIFIED", "confidence": 0.9, "issues": []},
                    )
                ],
                usage=FakeUsage(150, 40),
                stop_reason="tool_use",
            ),
            # 6. Insight Synthesizer.
            FakeMessage(
                content=[
                    FakeToolUseBlock(
                        id="ins_1",
                        name="submit_insights",
                        input={
                            "insights": [
                                {
                                    "verification_index": 0,
                                    "title": "Q2 2024 revenue decline",
                                    "finding": "Total revenue fell from Q1 to Q2 2024.",
                                    "business_significance": "A material quarter-over-quarter decline.",
                                    "limitations": [],
                                }
                            ]
                        },
                    )
                ],
                usage=FakeUsage(150, 40),
                stop_reason="tool_use",
            ),
            # 7. Recommendation Engine.
            FakeMessage(
                content=[
                    FakeToolUseBlock(
                        id="rec_1",
                        name="submit_recommendations",
                        input={
                            "recommendations": [
                                {
                                    "insight_indices": [0],
                                    "recommendation": "Investigate regional contribution to the Q2 decline.",
                                    "expected_impact": "Could identify where to focus recovery efforts.",
                                    "uncertainty": "Root cause is not established by this data alone.",
                                    "next_investigation": "Break revenue down by region for Q1 vs Q2.",
                                }
                            ]
                        },
                    )
                ],
                usage=FakeUsage(150, 40),
                stop_reason="tool_use",
            ),
            # 8. Report Generator: plain-text executive summary.
            FakeMessage(
                content=[FakeTextBlock(text="Revenue declined from Q1 to Q2 2024; the cause requires further investigation.")],
                usage=FakeUsage(200, 60),
                stop_reason="end_turn",
            ),
        ]
    )
    client = LLMClient(api_client=fake, model="gemini-3.6-flash")

    run = run_full_pipeline(df, "Why did revenue decline in Q2 2024?", client, dataset_name="01_sales_decline/data.csv")

    assert run.profile.row_count == len(df)
    assert run.plan.steps[0].operation == "compare_periods"
    assert len(run.analyst_run.calculation_results) == 1
    assert run.analyst_run.calculation_results[0].result["pct_change"] < 0

    assert len(run.verification_results) == 1
    assert run.verification_results[0].status == "VERIFIED"

    report = run.report
    assert report is not None
    assert report.executive_summary.startswith("Revenue declined")
    assert len(report.key_findings) == 1
    assert len(report.recommendations) == 1
    assert report.recommendations[0].uncertainty == "Root cause is not established by this data alone."
    assert len(report.evidence) == 1
    assert report.open_questions == []  # nothing UNSUPPORTED/CONTRADICTED in this run
