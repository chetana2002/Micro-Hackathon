"""Safe, dict-driven row filtering — no eval(), no arbitrary expressions.

Every tool in the registry filters through this single function, so the
`filters` field on a CalculationResult always corresponds exactly to what
was actually applied to the DataFrame.
"""
from __future__ import annotations

import operator

import pandas as pd

from app.models.calculation import FilterSpec

_OPS = {
    "==": operator.eq,
    "!=": operator.ne,
    ">": operator.gt,
    ">=": operator.ge,
    "<": operator.lt,
    "<=": operator.le,
}


def apply_filters(df: pd.DataFrame, filters: list[FilterSpec] | None) -> pd.DataFrame:
    if not filters:
        return df

    mask = pd.Series(True, index=df.index)
    for f in filters:
        if f.column not in df.columns:
            raise ValueError(f"Filter references unknown column '{f.column}'")
        series = df[f.column]
        if f.op == "in":
            mask &= series.isin(f.value)
        elif f.op == "not_in":
            mask &= ~series.isin(f.value)
        else:
            mask &= _OPS[f.op](series, f.value)
    return df[mask]
