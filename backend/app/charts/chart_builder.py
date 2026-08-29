"""Deterministic chart-spec construction from CalculationResult data.

The LLM never sees or invents chart data — every ChartSpec here is built
directly from a CalculationResult's `result` field, which was itself
produced by the Phase 3 tool registry. Operations that don't have a
natural series shape (calculate_sum/average/correlation/distribution)
return None rather than a fabricated chart.
"""
from __future__ import annotations

from app.models.calculation import CalculationResult
from app.models.chart import ChartSpec


def build_chart(calc: CalculationResult, title: str | None = None) -> ChartSpec | None:
    op = calc.operation

    if op == "trend":
        data = [{"x": k, "y": v} for k, v in calc.result["series"].items()]
        return ChartSpec(
            chart_type="line",
            title=title or f"Trend: {calc.input_columns[1]} over {calc.input_columns[0]}",
            x_label=calc.input_columns[0],
            y_label=calc.input_columns[1],
            series=[{"name": calc.input_columns[1], "data": data}],
        )

    if op == "group_by":
        data = [{"x": k, "y": v} for k, v in calc.result.items()]
        return ChartSpec(
            chart_type="bar",
            title=title or f"{calc.input_columns[1]} by {calc.input_columns[0]}",
            x_label=calc.input_columns[0],
            y_label=calc.input_columns[1],
            series=[{"name": calc.input_columns[1], "data": data}],
        )

    if op == "segment_analysis":
        data = [{"x": k, "y": v["value"]} for k, v in calc.result.items()]
        return ChartSpec(
            chart_type="bar",
            title=title or f"{calc.input_columns[1]} by {calc.input_columns[0]} segment",
            x_label=calc.input_columns[0],
            y_label=calc.input_columns[1],
            series=[{"name": calc.input_columns[1], "data": data}],
        )

    if op in ("top_n", "bottom_n"):
        data = [{"x": item["group"], "y": item["value"]} for item in calc.result]
        label = "Top" if op == "top_n" else "Bottom"
        return ChartSpec(
            chart_type="bar",
            title=title or f"{label} {calc.input_columns[0]} by {calc.input_columns[1]}",
            x_label=calc.input_columns[0],
            y_label=calc.input_columns[1],
            series=[{"name": calc.input_columns[1], "data": data}],
        )

    if op == "compare_periods":
        data = [
            {"x": "Period A", "y": calc.result["period_a_value"]},
            {"x": "Period B", "y": calc.result["period_b_value"]},
        ]
        return ChartSpec(
            chart_type="bar",
            title=title or f"{calc.input_columns[1]}: period comparison",
            x_label="Period",
            y_label=calc.input_columns[1],
            series=[{"name": calc.input_columns[1], "data": data}],
        )

    return None
