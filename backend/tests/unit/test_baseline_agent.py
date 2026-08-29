import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "baseline"))

from baseline_agent import SYSTEM_PROMPT, run_baseline  # noqa: E402

from app.llm.client import LLMClient
from tests.unit.fakes import FakeAnthropicClient, FakeMessage, FakeTextBlock, FakeUsage


def _sample_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "date": ["2024-01-15", "2024-02-15", "2024-03-15"],
            "region": ["North", "South", "North"],
            "revenue": [1000, 800, 900],
        }
    )


def test_baseline_uses_the_brief_system_prompt():
    assert SYSTEM_PROMPT == (
        "You are a business analyst. Analyze the provided dataset and answer the "
        "user's question. Provide calculations, insights and recommendations."
    )


def test_baseline_sends_dataset_context_and_question():
    fake = FakeAnthropicClient.with_responses(
        [FakeMessage(content=[FakeTextBlock(text="Analysis text.")], usage=FakeUsage(10, 10))]
    )
    client = LLMClient(api_client=fake, model="gemini-3.6-flash")

    response = run_baseline(
        _sample_df(), "Why did revenue decline?", dataset_name="sales.csv", llm_client=client
    )

    assert response.text == "Analysis text."
    call = fake.messages.calls[0]
    assert call["system"] == SYSTEM_PROMPT
    assert "tools" not in call  # baseline gets no tool access at all

    user_content = call["messages"][0]["content"]
    assert "sales.csv" in user_content
    assert "Rows: 3" in user_content
    assert "region" in user_content
    assert "Why did revenue decline?" in user_content


def test_baseline_context_matches_shared_profiling_code():
    # The dataset-context text embedded in the baseline prompt must come
    # from the exact same profiler used by the full agent's Data Profiler
    # stage — this is the fairness guarantee the brief requires.
    from app.llm.dataset_context import build_dataset_context_text
    from app.profiling.profiler import build_dataset_profile

    df = _sample_df()
    expected_profile = build_dataset_profile(df, dataset_name="sales.csv")
    expected_context = build_dataset_context_text(df, expected_profile)

    fake = FakeAnthropicClient.with_responses(
        [FakeMessage(content=[FakeTextBlock(text="ok")], usage=FakeUsage(1, 1))]
    )
    client = LLMClient(api_client=fake, model="gemini-3.6-flash")
    run_baseline(df, "some question", dataset_name="sales.csv", llm_client=client)

    sent_content = fake.messages.calls[0]["messages"][0]["content"]
    assert expected_context in sent_content
