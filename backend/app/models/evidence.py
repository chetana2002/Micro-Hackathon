from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.models.calculation import FilterSpec


class Evidence(BaseModel):
    evidence_id: str
    claim: str
    source_operation: str
    source_columns: list[str]
    filters: list[FilterSpec] = Field(default_factory=list)
    calculation: str
    result: Any
    confidence: float
