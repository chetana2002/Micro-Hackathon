"""Typed contracts for the Data Profiler stage.

Every field here is populated by deterministic pandas code in
`app.profiling.profiler` — never by an LLM. This is the boundary the spec
calls out explicitly: "Do NOT allow the LLM to invent dataset statistics."
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

SemanticType = Literal[
    "numeric", "categorical", "date", "boolean", "identifier", "text", "unknown"
]


class ColumnProfile(BaseModel):
    name: str
    dtype: str
    semantic_type: SemanticType
    missing_count: int
    missing_pct: float
    unique_count: int
    sample_values: list[str] = Field(default_factory=list)


class DatasetProfile(BaseModel):
    dataset_name: str
    row_count: int
    column_count: int
    columns: list[str]
    data_types: dict[str, str]
    missing_values: dict[str, int]
    duplicate_count: int
    date_columns: list[str]
    numeric_columns: list[str]
    categorical_columns: list[str]
    warnings: list[str]
    column_profiles: list[ColumnProfile]
