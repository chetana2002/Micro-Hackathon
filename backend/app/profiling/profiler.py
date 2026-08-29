"""Deterministic dataset profiling.

No LLM involvement anywhere in this file. Every statistic in the returned
DatasetProfile comes from pandas computation over the actual data.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from app.models.profile import ColumnProfile, DatasetProfile

SUPPORTED_EXTENSIONS = {".csv", ".tsv", ".xlsx", ".xls"}

# Column-name substrings that suggest a quantity that should not be negative.
# Used only to raise a warning, never to alter the data.
_NON_NEGATIVE_NAME_HINTS = (
    "quantity", "qty", "price", "amount", "revenue", "cost", "units",
    "count", "sales", "volume", "stock", "inventory",
)

_HIGH_CARDINALITY_UNIQUE_RATIO = 0.95
_CATEGORICAL_MAX_UNIQUE = 50
_CATEGORICAL_MAX_UNIQUE_RATIO = 0.5
_DATE_PARSE_SUCCESS_THRESHOLD = 0.9
_HIGH_MISSING_THRESHOLD = 0.5


def load_dataset(file_path: str | Path) -> pd.DataFrame:
    path = Path(file_path)
    suffix = path.suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        raise ValueError(
            f"Unsupported file type '{suffix}'. Supported: {sorted(SUPPORTED_EXTENSIONS)}"
        )
    if suffix == ".csv":
        return pd.read_csv(path)
    if suffix == ".tsv":
        return pd.read_csv(path, sep="\t")
    return pd.read_excel(path)


def _infer_semantic_type(series: pd.Series) -> str:
    non_null = series.dropna()
    if non_null.empty:
        return "unknown"

    if pd.api.types.is_bool_dtype(series):
        return "boolean"

    if pd.api.types.is_numeric_dtype(series):
        return "numeric"

    if pd.api.types.is_datetime64_any_dtype(series):
        return "date"

    # Only attempt string->date parsing on non-numeric dtypes: calling
    # pd.to_datetime on an already-numeric column interprets values as
    # nanosecond epoch offsets, which silently misclassifies plain integer
    # columns (e.g. a "year" column) as dates.
    parsed = pd.to_datetime(non_null, errors="coerce", format="mixed")
    success_ratio = parsed.notna().mean()
    if success_ratio >= _DATE_PARSE_SUCCESS_THRESHOLD:
        return "date"

    unique_count = non_null.nunique()
    unique_ratio = unique_count / len(non_null)
    if unique_ratio >= _HIGH_CARDINALITY_UNIQUE_RATIO and unique_count > _CATEGORICAL_MAX_UNIQUE:
        return "identifier"

    if unique_count <= _CATEGORICAL_MAX_UNIQUE or unique_ratio <= _CATEGORICAL_MAX_UNIQUE_RATIO:
        return "categorical"

    return "text"


def _column_warnings(name: str, series: pd.Series, semantic_type: str) -> list[str]:
    warnings: list[str] = []
    non_null = series.dropna()

    missing_pct = series.isna().mean()
    if missing_pct >= _HIGH_MISSING_THRESHOLD:
        warnings.append(
            f"Column '{name}' is {missing_pct:.0%} missing — treat derived metrics with caution."
        )

    if len(non_null) > 0 and non_null.nunique() == 1:
        warnings.append(f"Column '{name}' has a single constant value across all rows.")

    if semantic_type == "numeric" and len(non_null) > 0:
        name_lower = name.lower()
        if any(hint in name_lower for hint in _NON_NEGATIVE_NAME_HINTS):
            negative_count = (non_null < 0).sum()
            if negative_count > 0:
                warnings.append(
                    f"Column '{name}' contains {negative_count} negative value(s) "
                    "in a field whose name suggests it should not be negative."
                )

    if semantic_type in ("text", "categorical", "identifier") and len(non_null) > 0:
        # Numeric-looking strings (e.g. "1,000" or "$50") stored as text.
        # Checked regardless of cardinality-based classification — a column
        # can have few unique values and still be a miscoerced numeric field.
        numeric_like = non_null.astype(str).str.match(r"^[\$\-]?[\d,.]+%?$").mean()
        if numeric_like >= 0.8:
            warnings.append(
                f"Column '{name}' looks numeric but is stored as text "
                "(e.g. thousands separators or currency symbols) — values were not coerced."
            )

    return warnings


def build_dataset_profile(df: pd.DataFrame, dataset_name: str = "") -> DatasetProfile:
    row_count = int(len(df))
    column_count = int(len(df.columns))
    warnings: list[str] = []

    if row_count == 0:
        warnings.append("Dataset has 0 rows — no statistics can be computed.")

    duplicate_count = int(df.duplicated().sum()) if row_count > 0 else 0
    if duplicate_count > 0:
        warnings.append(f"Dataset contains {duplicate_count} fully duplicate row(s).")

    column_profiles: list[ColumnProfile] = []
    data_types: dict[str, str] = {}
    missing_values: dict[str, int] = {}
    date_columns: list[str] = []
    numeric_columns: list[str] = []
    categorical_columns: list[str] = []

    for col in df.columns:
        series = df[col]
        semantic_type = _infer_semantic_type(series)
        missing_count = int(series.isna().sum())
        missing_pct = float(series.isna().mean()) if row_count > 0 else 0.0
        unique_count = int(series.dropna().nunique())
        sample_values = [str(v) for v in series.dropna().unique()[:5]]

        column_profiles.append(
            ColumnProfile(
                name=str(col),
                dtype=str(series.dtype),
                semantic_type=semantic_type,
                missing_count=missing_count,
                missing_pct=missing_pct,
                unique_count=unique_count,
                sample_values=sample_values,
            )
        )
        data_types[str(col)] = str(series.dtype)
        missing_values[str(col)] = missing_count

        if semantic_type == "date":
            date_columns.append(str(col))
        elif semantic_type == "numeric":
            numeric_columns.append(str(col))
        elif semantic_type == "categorical":
            categorical_columns.append(str(col))

        warnings.extend(_column_warnings(str(col), series, semantic_type))

    return DatasetProfile(
        dataset_name=dataset_name,
        row_count=row_count,
        column_count=column_count,
        columns=[str(c) for c in df.columns],
        data_types=data_types,
        missing_values=missing_values,
        duplicate_count=duplicate_count,
        date_columns=date_columns,
        numeric_columns=numeric_columns,
        categorical_columns=categorical_columns,
        warnings=warnings,
        column_profiles=column_profiles,
    )


def profile_file(file_path: str | Path) -> DatasetProfile:
    path = Path(file_path)
    df = load_dataset(path)
    return build_dataset_profile(df, dataset_name=path.name)
