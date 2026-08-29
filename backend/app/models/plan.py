from __future__ import annotations

from pydantic import BaseModel, Field


class AnalysisStep(BaseModel):
    step_id: int
    operation: str
    rationale: str
    target_columns: list[str] = Field(default_factory=list)


class AnalysisPlan(BaseModel):
    question: str
    steps: list[AnalysisStep]
