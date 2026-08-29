from __future__ import annotations

from pydantic import BaseModel, Field

from app.models.chart import ChartSpec
from app.models.evidence import Evidence
from app.models.insight import Insight
from app.models.profile import DatasetProfile
from app.models.recommendation import Recommendation


class Report(BaseModel):
    question: str
    executive_summary: str
    dataset_overview: DatasetProfile
    data_quality_warnings: list[str] = Field(default_factory=list)
    key_findings: list[Insight] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    charts: list[ChartSpec] = Field(default_factory=list)
    recommendations: list[Recommendation] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
