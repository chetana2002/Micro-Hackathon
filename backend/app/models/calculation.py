"""Typed contract for every deterministic calculation the analysis engine runs.

This is the atomic unit of truth in InsightForge: every Evidence, every
VerificationResult, and every chart traces back to a CalculationResult. The
LLM never fabricates a number that isn't backed by one of these.
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

FilterOp = Literal["==", "!=", ">", ">=", "<", "<=", "in", "not_in"]


class FilterSpec(BaseModel):
    column: str
    op: FilterOp
    value: Any


class CalculationResult(BaseModel):
    operation: str
    input_columns: list[str]
    filters: list[FilterSpec] = Field(default_factory=list)
    parameters: dict[str, Any] = Field(default_factory=dict)
    result: Any
    source_rows: int
    reproducible_expression: str
    warnings: list[str] = Field(default_factory=list)
