import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "evaluation"))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "baseline"))

from run_evaluation import _load_cases, _run_one, _summarize  # noqa: E402

from app.llm.client import LLMClient
from tests.unit.fakes import FakeAnthropicClient, FakeMessage, FakeTextBlock, FakeToolUseBlock, FakeUsage


def _judge_response():
    return FakeMessage(
        content=[
            FakeToolUseBlock(
                id="judge_1",
                name="submit_judge_scores",
                input={
                    "evidence_grounding": 0.9,
                    "unsupported_claims_rate": 0.1,
                    "recommendation_grounding": 0.8,
                    "business_usefulness": 0.9,
                    "rationale": "Well grounded overall.",
                },
            )
        ],
        usage=FakeUsage(150, 50),
        stop_reason="tool_use",
    )


def test_load_cases_finds_all_ten_datasets():
    cases = _load_cases(None)
    assert len(cases) == 10
    assert all("question" in c and "expected_findings" in c for c in cases)


def test_load_cases_filters_by_name():
    cases = _load_cases(["01_sales_decline"])
    assert len(cases) == 1
    assert cases[0]["_dataset_dir"] == "01_sales_decline"


def test_run_one_baseline_success_path():
    case = _load_cases(["05_marketing_roi"])[0]
    fake = FakeAnthropicClient.with_responses(
        [
            FakeMessage(
                content=[FakeTextBlock(text="Email has the best ROI at roughly 5.5x spend.")],
                usage=FakeUsage(500, 200),
            ),
            _judge_response(),
        ]
    )
    client = LLMClient(api_client=fake, model="gemini-3.6-flash")

    result = _run_one(case, "baseline", client)

    assert result["error"] is None
    assert result["system"] == "baseline"
    assert result["score"]["total_score"] > 0
    assert result["usage"]["input_tokens"] == 500


def test_run_one_records_error_instead_of_raising():
    case = {"_dataset_dir": "does_not_exist", "question": "Why?", "expected_findings": [], "known_traps": []}
    fake = FakeAnthropicClient.with_responses([])
    client = LLMClient(api_client=fake, model="gemini-3.6-flash")

    result = _run_one(case, "baseline", client)

    assert result["error"] is not None
    assert result["score"] is None
    assert result["output_text"] is None


def test_summarize_averages_scores_and_counts_failures():
    results = [
        {"score": {"total_score": 80.0, "numerical_correctness": 30, "key_findings": 20, "evidence_grounding": 15, "unsupported_claims": 10, "recommendation_grounding": 3, "business_usefulness": 2}},
        {"score": {"total_score": 60.0, "numerical_correctness": 20, "key_findings": 15, "evidence_grounding": 10, "unsupported_claims": 10, "recommendation_grounding": 3, "business_usefulness": 2}},
        {"score": None},
    ]

    summary = _summarize(results)

    assert summary["total_score"] == 70.0
    assert summary["cases_scored"] == 2
    assert summary["cases_failed"] == 1


def test_summarize_handles_all_failures():
    summary = _summarize([{"score": None}, {"score": None}])
    assert summary["mean_total_score"] is None
    assert summary["cases_failed"] == 2
