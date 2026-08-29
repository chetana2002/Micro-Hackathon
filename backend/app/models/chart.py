from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class ChartSpec(BaseModel):
    chart_type: Literal["line", "bar"]
    title: str
    x_label: str
    y_label: str
    series: list[dict]
