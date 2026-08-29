"""Shared dataset-context text builder.

This is the fairness anchor for the baseline-vs-agent comparison: the
baseline agent's only view of the data is the text this function produces,
built from the same DatasetProfile the full agent's Data Profiler stage
computes. Neither system gets hand-tuned or extra context.
"""
from __future__ import annotations

import pandas as pd

from app.models.profile import DatasetProfile

DEFAULT_MAX_SAMPLE_ROWS = 20


def build_dataset_context_text(
    df: pd.DataFrame, profile: DatasetProfile, max_sample_rows: int = DEFAULT_MAX_SAMPLE_ROWS
) -> str:
    lines = [
        f"Dataset: {profile.dataset_name or '(unnamed)'}",
        f"Rows: {profile.row_count}, Columns: {profile.column_count}",
        "",
        "Columns:",
    ]
    for col in profile.column_profiles:
        lines.append(
            f"  - {col.name} (dtype: {col.dtype}, semantic type: {col.semantic_type}, "
            f"missing: {col.missing_count}, unique values: {col.unique_count})"
        )

    if profile.warnings:
        lines.append("")
        lines.append("Data quality warnings (from automated profiling, not the model):")
        for w in profile.warnings:
            lines.append(f"  - {w}")

    sample_n = min(max_sample_rows, len(df))
    lines.append("")
    lines.append(f"Sample rows (first {sample_n} of {profile.row_count}):")
    lines.append(df.head(max_sample_rows).to_csv(index=False))

    return "\n".join(lines)
