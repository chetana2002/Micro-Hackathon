from __future__ import annotations

from pydantic import BaseModel, Field

from app.models.evidence import Evidence


class Insight(BaseModel):
    title: str
    finding: str
    evidence: list[Evidence] = Field(default_factory=list)
    business_significance: str
    confidence: float
    limitations: list[str] = Field(default_factory=list)
