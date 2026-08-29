"""The deterministic analysis tool registry.

These eleven functions are the ONLY way data ever gets touched after
profiling. The LLM (Data Analyst agent, Phase 5) selects one of these by
name and supplies arguments; it never writes or executes its own code.
Every function returns a CalculationResult so the number, the exact filter
set, and a reproducible expression travel together.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from app.models.calculation import CalculationResult, FilterSpec
from app.tools.filters import apply_filters

_ROUND = 4


def _filters_repr(filters: list[FilterSpec] | None) -> str:
    if not filters:
        return ""
    parts = [f"{f.column} {f.op} {f.value!r}" for f in filters]
    return " WHERE " + " AND ".join(parts)


def _round(value: float) -> float:
    if pd.isna(value):
        return float("nan")
    return round(float(value), _ROUND)


def _round_pct(value: float) -> float:
    """Percentages are business-facing and reported to 2 decimals, matching
    the -23.04% convention used throughout the project brief — a coarser
    precision than the 4-decimal default used for raw metric values."""
    if pd.isna(value):
        return float("nan")
    return round(float(value), 2)


def calculate_sum(
    df: pd.DataFrame, column: str, filters: list[FilterSpec] | None = None
) -> CalculationResult:
    filtered = apply_filters(df, filters)
    result = _round(filtered[column].sum()) if len(filtered) else 0.0
    return CalculationResult(
        operation="calculate_sum",
        input_columns=[column],
        filters=filters or [],
        parameters={},
        result=result,
        source_rows=len(filtered),
        reproducible_expression=f"SUM({column}){_filters_repr(filters)}",
    )


def calculate_average(
    df: pd.DataFrame, column: str, filters: list[FilterSpec] | None = None
) -> CalculationResult:
    filtered = apply_filters(df, filters)
    warnings = []
    if len(filtered) == 0:
        warnings.append("No rows matched the given filters; average is undefined.")
        result = None
    else:
        result = _round(filtered[column].mean())
    return CalculationResult(
        operation="calculate_average",
        input_columns=[column],
        filters=filters or [],
        parameters={},
        result=result,
        source_rows=len(filtered),
        reproducible_expression=f"AVG({column}){_filters_repr(filters)}",
        warnings=warnings,
    )


def calculate_percentage_change(baseline: float, current: float) -> CalculationResult:
    warnings = []
    if baseline == 0:
        warnings.append("Baseline value is 0; percentage change is undefined.")
        result = None
    else:
        result = _round_pct((current - baseline) / baseline * 100)
    return CalculationResult(
        operation="calculate_percentage_change",
        input_columns=[],
        filters=[],
        parameters={"baseline": baseline, "current": current},
        result=result,
        source_rows=0,
        reproducible_expression=f"(({current} - {baseline}) / {baseline}) * 100",
        warnings=warnings,
    )


def compare_periods(
    df: pd.DataFrame,
    date_column: str,
    value_column: str,
    period_a: tuple[str, str],
    period_b: tuple[str, str],
    agg: str = "sum",
) -> CalculationResult:
    dates = pd.to_datetime(df[date_column], errors="coerce", format="mixed")
    a_mask = (dates >= period_a[0]) & (dates <= period_a[1])
    b_mask = (dates >= period_b[0]) & (dates <= period_b[1])

    agg_fn = getattr(df.loc[a_mask, value_column], agg)
    a_value = _round(agg_fn()) if a_mask.sum() else 0.0
    agg_fn_b = getattr(df.loc[b_mask, value_column], agg)
    b_value = _round(agg_fn_b()) if b_mask.sum() else 0.0

    pct_change = None
    warnings = []
    if a_value == 0:
        warnings.append("Period A value is 0; percentage change is undefined.")
    else:
        pct_change = _round_pct((b_value - a_value) / a_value * 100)

    return CalculationResult(
        operation="compare_periods",
        input_columns=[date_column, value_column],
        filters=[],
        parameters={
            "agg": agg,
            "period_a": list(period_a),
            "period_b": list(period_b),
        },
        result={"period_a_value": a_value, "period_b_value": b_value, "pct_change": pct_change},
        source_rows=int(a_mask.sum() + b_mask.sum()),
        reproducible_expression=(
            f"{agg.upper()}({value_column}) WHERE {date_column} IN {period_a} "
            f"vs {agg.upper()}({value_column}) WHERE {date_column} IN {period_b}"
        ),
        warnings=warnings,
    )


def group_by(
    df: pd.DataFrame,
    group_column: str,
    value_column: str,
    agg: str = "sum",
    filters: list[FilterSpec] | None = None,
) -> CalculationResult:
    filtered = apply_filters(df, filters)
    grouped = filtered.groupby(group_column)[value_column].agg(agg)
    result = {str(k): _round(v) for k, v in grouped.items()}
    return CalculationResult(
        operation="group_by",
        input_columns=[group_column, value_column],
        filters=filters or [],
        parameters={"agg": agg},
        result=result,
        source_rows=len(filtered),
        reproducible_expression=(
            f"{agg.upper()}({value_column}) GROUP BY {group_column}{_filters_repr(filters)}"
        ),
    )


def top_n(
    df: pd.DataFrame,
    group_column: str,
    value_column: str,
    n: int = 5,
    agg: str = "sum",
    filters: list[FilterSpec] | None = None,
) -> CalculationResult:
    filtered = apply_filters(df, filters)
    grouped = filtered.groupby(group_column)[value_column].agg(agg).sort_values(ascending=False)
    top = grouped.head(n)
    result = [{"group": str(k), "value": _round(v)} for k, v in top.items()]
    return CalculationResult(
        operation="top_n",
        input_columns=[group_column, value_column],
        filters=filters or [],
        parameters={"n": n, "agg": agg},
        result=result,
        source_rows=len(filtered),
        reproducible_expression=(
            f"TOP {n} {group_column} BY {agg.upper()}({value_column}){_filters_repr(filters)}"
        ),
    )


def bottom_n(
    df: pd.DataFrame,
    group_column: str,
    value_column: str,
    n: int = 5,
    agg: str = "sum",
    filters: list[FilterSpec] | None = None,
) -> CalculationResult:
    filtered = apply_filters(df, filters)
    grouped = filtered.groupby(group_column)[value_column].agg(agg).sort_values(ascending=True)
    bottom = grouped.head(n)
    result = [{"group": str(k), "value": _round(v)} for k, v in bottom.items()]
    return CalculationResult(
        operation="bottom_n",
        input_columns=[group_column, value_column],
        filters=filters or [],
        parameters={"n": n, "agg": agg},
        result=result,
        source_rows=len(filtered),
        reproducible_expression=(
            f"BOTTOM {n} {group_column} BY {agg.upper()}({value_column}){_filters_repr(filters)}"
        ),
    )


def correlation(
    df: pd.DataFrame,
    column_a: str,
    column_b: str,
    filters: list[FilterSpec] | None = None,
) -> CalculationResult:
    filtered = apply_filters(df, filters)
    pair = filtered[[column_a, column_b]].dropna()
    warnings = []
    if len(pair) < 3:
        warnings.append(
            f"Only {len(pair)} paired observations; correlation is unreliable below ~3 points."
        )
    result = _round(pair[column_a].corr(pair[column_b])) if len(pair) >= 2 else None
    warnings.append(
        "Correlation measures association only; it does not establish causation."
    )
    return CalculationResult(
        operation="correlation",
        input_columns=[column_a, column_b],
        filters=filters or [],
        parameters={},
        result=result,
        source_rows=len(pair),
        reproducible_expression=f"CORR({column_a}, {column_b}){_filters_repr(filters)}",
        warnings=warnings,
    )


def distribution(
    df: pd.DataFrame, column: str, filters: list[FilterSpec] | None = None
) -> CalculationResult:
    filtered = apply_filters(df, filters)
    series = filtered[column].dropna()
    if len(series) == 0:
        result = None
        warnings = ["No non-null values available; distribution is undefined."]
    else:
        result = {
            "mean": _round(series.mean()),
            "median": _round(series.median()),
            "std": _round(series.std()) if len(series) > 1 else 0.0,
            "min": _round(series.min()),
            "max": _round(series.max()),
            "q25": _round(series.quantile(0.25)),
            "q75": _round(series.quantile(0.75)),
        }
        warnings = []
    return CalculationResult(
        operation="distribution",
        input_columns=[column],
        filters=filters or [],
        parameters={},
        result=result,
        source_rows=len(series),
        reproducible_expression=f"DISTRIBUTION({column}){_filters_repr(filters)}",
        warnings=warnings,
    )


def trend(
    df: pd.DataFrame,
    date_column: str,
    value_column: str,
    freq: str = "MS",
    agg: str = "sum",
    filters: list[FilterSpec] | None = None,
) -> CalculationResult:
    filtered = apply_filters(df, filters).copy()
    filtered[date_column] = pd.to_datetime(filtered[date_column], errors="coerce", format="mixed")
    filtered = filtered.dropna(subset=[date_column])
    series = filtered.set_index(date_column)[value_column].resample(freq).agg(agg)

    direction = "flat"
    if len(series) >= 2:
        x = np.arange(len(series))
        y = series.to_numpy(dtype=float)
        slope = np.polyfit(x, y, 1)[0]
        if slope > 0:
            direction = "increasing"
        elif slope < 0:
            direction = "decreasing"

    result = {
        "series": {k.strftime("%Y-%m-%d"): _round(v) for k, v in series.items()},
        "direction": direction,
    }
    return CalculationResult(
        operation="trend",
        input_columns=[date_column, value_column],
        filters=filters or [],
        parameters={"freq": freq, "agg": agg},
        result=result,
        source_rows=len(filtered),
        reproducible_expression=(
            f"{agg.upper()}({value_column}) RESAMPLE({freq}) BY {date_column}{_filters_repr(filters)}"
        ),
    )


def segment_analysis(
    df: pd.DataFrame,
    segment_column: str,
    value_column: str,
    agg: str = "sum",
    filters: list[FilterSpec] | None = None,
) -> CalculationResult:
    filtered = apply_filters(df, filters)
    grouped = filtered.groupby(segment_column)[value_column].agg(agg)
    total = grouped.sum()
    result = {
        str(k): {
            "value": _round(v),
            "pct_of_total": _round_pct(v / total * 100) if total else 0.0,
        }
        for k, v in grouped.items()
    }
    return CalculationResult(
        operation="segment_analysis",
        input_columns=[segment_column, value_column],
        filters=filters or [],
        parameters={"agg": agg},
        result=result,
        source_rows=len(filtered),
        reproducible_expression=(
            f"{agg.upper()}({value_column}) BY SEGMENT({segment_column}) "
            f"WITH SHARE OF TOTAL{_filters_repr(filters)}"
        ),
    )


TOOL_REGISTRY = {
    "calculate_sum": calculate_sum,
    "calculate_average": calculate_average,
    "calculate_percentage_change": calculate_percentage_change,
    "compare_periods": compare_periods,
    "group_by": group_by,
    "top_n": top_n,
    "bottom_n": bottom_n,
    "correlation": correlation,
    "distribution": distribution,
    "trend": trend,
    "segment_analysis": segment_analysis,
}
