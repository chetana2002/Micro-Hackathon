"""Gemini function-calling JSON schemas for the deterministic tool registry.

These are the ONLY tools ever exposed to the Data Analyst agent. Each
schema's shape mirrors the corresponding function's real parameters in
app.tools.registry, so a valid tool call always maps onto a real function
call with no additional translation layer that could drift from the
underlying implementation.
"""
from __future__ import annotations

_FILTERS_PARAM = {
    "type": "array",
    "description": "Optional row filters, combined with AND.",
    "items": {
        "type": "object",
        "properties": {
            "column": {"type": "string"},
            "op": {"type": "string", "enum": ["==", "!=", ">", ">=", "<", "<=", "in", "not_in"]},
            "value": {"description": "Comparison value; an array when op is 'in' or 'not_in'."},
        },
        "required": ["column", "op", "value"],
    },
}

_AGG_PARAM = {"type": "string", "enum": ["sum", "mean", "median", "min", "max", "count"], "default": "sum"}


def _tool(name: str, description: str, properties: dict, required: list[str]) -> dict:
    return {
        "name": name,
        "description": description,
        "input_schema": {"type": "object", "properties": properties, "required": required},
    }


TOOL_SCHEMAS: list[dict] = [
    _tool(
        "calculate_sum",
        "Sum a numeric column, optionally filtered.",
        {"column": {"type": "string"}, "filters": _FILTERS_PARAM},
        ["column"],
    ),
    _tool(
        "calculate_average",
        "Average a numeric column, optionally filtered.",
        {"column": {"type": "string"}, "filters": _FILTERS_PARAM},
        ["column"],
    ),
    _tool(
        "calculate_percentage_change",
        "Compute percentage change between two already-known numeric values "
        "(e.g. two period totals you obtained from prior tool calls).",
        {"baseline": {"type": "number"}, "current": {"type": "number"}},
        ["baseline", "current"],
    ),
    _tool(
        "compare_periods",
        "Aggregate a value column over two date ranges and compute the percentage change between them.",
        {
            "date_column": {"type": "string"},
            "value_column": {"type": "string"},
            "period_a": {"type": "array", "items": {"type": "string"}, "description": "[start_date, end_date]"},
            "period_b": {"type": "array", "items": {"type": "string"}, "description": "[start_date, end_date]"},
            "agg": _AGG_PARAM,
        },
        ["date_column", "value_column", "period_a", "period_b"],
    ),
    _tool(
        "group_by",
        "Aggregate a value column grouped by a categorical column.",
        {
            "group_column": {"type": "string"},
            "value_column": {"type": "string"},
            "agg": _AGG_PARAM,
            "filters": _FILTERS_PARAM,
        },
        ["group_column", "value_column"],
    ),
    _tool(
        "top_n",
        "Return the top N groups by aggregated value.",
        {
            "group_column": {"type": "string"},
            "value_column": {"type": "string"},
            "n": {"type": "integer", "default": 5},
            "agg": _AGG_PARAM,
            "filters": _FILTERS_PARAM,
        },
        ["group_column", "value_column"],
    ),
    _tool(
        "bottom_n",
        "Return the bottom N groups by aggregated value.",
        {
            "group_column": {"type": "string"},
            "value_column": {"type": "string"},
            "n": {"type": "integer", "default": 5},
            "agg": _AGG_PARAM,
            "filters": _FILTERS_PARAM,
        },
        ["group_column", "value_column"],
    ),
    _tool(
        "correlation",
        "Pearson correlation between two numeric columns. Association only, never causation.",
        {"column_a": {"type": "string"}, "column_b": {"type": "string"}, "filters": _FILTERS_PARAM},
        ["column_a", "column_b"],
    ),
    _tool(
        "distribution",
        "Summary statistics (mean, median, std, min, max, quartiles) for a numeric column.",
        {"column": {"type": "string"}, "filters": _FILTERS_PARAM},
        ["column"],
    ),
    _tool(
        "trend",
        "Resample a value column over time and report the direction (increasing/decreasing/flat).",
        {
            "date_column": {"type": "string"},
            "value_column": {"type": "string"},
            "freq": {"type": "string", "description": "pandas offset alias, e.g. 'MS', 'W', 'D'", "default": "MS"},
            "agg": _AGG_PARAM,
            "filters": _FILTERS_PARAM,
        },
        ["date_column", "value_column"],
    ),
    _tool(
        "segment_analysis",
        "Aggregate a value column by segment and report each segment's share of the total.",
        {
            "segment_column": {"type": "string"},
            "value_column": {"type": "string"},
            "agg": _AGG_PARAM,
            "filters": _FILTERS_PARAM,
        },
        ["segment_column", "value_column"],
    ),
]

TOOL_SCHEMA_NAMES = {t["name"] for t in TOOL_SCHEMAS}
