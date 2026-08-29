from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from app.models.evidence import Evidence

VerificationStatus = Literal["VERIFIED", "PARTIALLY_VERIFIED", "UNSUPPORTED", "CONTRADICTED"]


class VerificationResult(BaseModel):
    claim: str
    status: VerificationStatus
    evidence: Evidence
    confidence: float
    issues: list[str] = Field(default_factory=list)
    corrected_value: Any | None = None
