"""The fair baseline: one general-purpose LLM call, no tools, no
verification, no multi-stage structure.

Per the project brief, this is what InsightForge's full agentic workflow is
measured against. It receives exactly the same dataset and question as the
full agent, and its only view of the data is text built by
app.llm.dataset_context.build_dataset_context_text — the identical function
used to construct context for the full agent's planner — so neither system
has an information advantage. The system prompt below is the brief's own
literal wording.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.llm.client import LLMClient, LLMResponse  # noqa: E402
from app.llm.dataset_context import build_dataset_context_text  # noqa: E402
from app.profiling.profiler import build_dataset_profile  # noqa: E402

SYSTEM_PROMPT = (
    "You are a business analyst. Analyze the provided dataset and answer the "
    "user's question. Provide calculations, insights and recommendations."
)


def run_baseline(
    df: pd.DataFrame,
    question: str,
    dataset_name: str = "",
    llm_client: LLMClient | None = None,
    max_tokens: int = 4096,
) -> LLMResponse:
    client = llm_client or LLMClient()
    profile = build_dataset_profile(df, dataset_name=dataset_name)
    context_text = build_dataset_context_text(df, profile)

    user_message = f"{context_text}\n\nQuestion: {question}"
    return client.create_message(
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_message}],
        max_tokens=max_tokens,
    )
