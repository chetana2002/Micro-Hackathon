from __future__ import annotations

from pydantic import BaseModel, Field

from app.models.evidence import Evidence


class Recommendation(BaseModel):
    recommendation: str
    supporting_evidence: list[Evidence] = Field(default_factory=list)
    expected_impact: str
    uncertainty: str
    next_investigation: str
