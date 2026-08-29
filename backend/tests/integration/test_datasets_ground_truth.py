"""Cross-checks each synthetic dataset's case.json ground truth against the
actual deterministic tool registry (not just the generator script's inline
arithmetic) — this is a genuine independent check, since compare_periods/
group_by/correlation in app.tools.registry are a different code path than
scripts/generate_datasets.py's own pandas calls.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from app.models.calculation import FilterSpec
from app.tools import registry

DATASETS_DIR = Path(__file__).resolve().parent.parent.parent.parent / "datasets"


def _load(dirname: str) -> tuple[pd.DataFrame, dict]:
    d = DATASETS_DIR / dirname
    df = pd.read_csv(d / "data.csv")
    case = json.loads((d / "case.json").read_text())
    return df, case


def _tol(finding: dict) -> float:
    return finding.get("tolerance_abs", 0.01)


def test_01_sales_decline_matches_registry():
    df, case = _load("01_sales_decline")
    findings = {f["metric"]: f for f in case["expected_findings"]}

    cp = registry.compare_periods(
        df, "date", "revenue", ("2024-01-01", "2024-03-31"), ("2024-04-01", "2024-06-30")
    )
    assert cp.result["pct_change"] == pytest.approx(
        findings["pct_change_q1_to_q2_total_revenue"]["expected_value"],
        abs=_tol(findings["pct_change_q1_to_q2_total_revenue"]),
    )

    q1 = [FilterSpec(column="date", op=">=", value="2024-01-01"), FilterSpec(column="date", op="<=", value="2024-03-31")]
    q2 = [FilterSpec(column="date", op=">=", value="2024-04-01"), FilterSpec(column="date", op="<=", value="2024-06-30")]
    seg_q1 = registry.segment_analysis(df, "region", "revenue", filters=q1)
    seg_q2 = registry.segment_analysis(df, "region", "revenue", filters=q2)
    q1_total = sum(v["value"] for v in seg_q1.result.values())
    q2_total = sum(v["value"] for v in seg_q2.result.values())
    north_decline = seg_q1.result["North"]["value"] - seg_q2.result["North"]["value"]
    total_decline = q1_total - q2_total
    north_share = round(north_decline / total_decline * 100, 2)
    assert north_share == pytest.approx(
        findings["north_share_of_total_decline_pct"]["expected_value"],
        abs=_tol(findings["north_share_of_total_decline_pct"]),
    )


def test_02_regional_performance_matches_registry():
    df, case = _load("02_regional_performance")
    findings = {f["metric"]: f for f in case["expected_findings"]}

    result = registry.top_n(df, "region", "revenue", n=1)
    assert result.result[0]["group"] == findings["top_region_by_total_revenue"]["expected_value"]

    result = registry.bottom_n(df, "region", "revenue", n=1)
    assert result.result[0]["group"] == findings["bottom_region_by_total_revenue"]["expected_value"]

    # The documented trap: East is missing exactly 3 weeks of March records.
    march_east = df[(df["region"] == "East") & (df["week"] >= "2024-03-01") & (df["week"] <= "2024-03-31")]
    assert len(march_east) < 4  # normal months have ~4-5 weekly rows


def test_03_product_performance_matches_registry():
    df, case = _load("03_product_performance")
    findings = {f["metric"]: f for f in case["expected_findings"]}

    result = registry.top_n(df, "product_id", "revenue", n=1)
    assert result.result[0]["group"] == findings["top_product_by_total_revenue"]["expected_value"]

    result = registry.bottom_n(df, "product_id", "revenue", n=1)
    assert result.result[0]["group"] == findings["bottom_product_by_total_revenue"]["expected_value"]


def test_04_customer_churn_matches_registry():
    df, case = _load("04_customer_churn")
    findings = {f["metric"]: f for f in case["expected_findings"]}

    df["churned_int"] = df["churned"].astype(int)
    result = registry.correlation(df, "support_tickets", "churned_int")
    assert result.result == pytest.approx(
        findings["correlation_support_tickets_churned"]["expected_value"],
        abs=_tol(findings["correlation_support_tickets_churned"]),
    )
    assert any("causation" in w for w in result.warnings)

    result = registry.calculate_average(df, "churned_int")
    churn_rate_pct = round(result.result * 100, 2)
    assert churn_rate_pct == pytest.approx(
        findings["overall_churn_rate_pct"]["expected_value"],
        abs=_tol(findings["overall_churn_rate_pct"]),
    )


def test_05_marketing_roi_matches_registry():
    df, case = _load("05_marketing_roi")
    findings = {f["metric"]: f for f in case["expected_findings"]}

    spend_by_channel = registry.group_by(df, "channel", "spend", agg="sum")
    revenue_by_channel = registry.group_by(df, "channel", "revenue_attributed", agg="sum")
    roi = {
        ch: revenue_by_channel.result[ch] / spend_by_channel.result[ch]
        for ch in spend_by_channel.result
    }
    best_channel = max(roi, key=roi.get)
    assert best_channel == findings["top_channel_by_roi"]["expected_value"]
    assert round(roi[best_channel], 2) == pytest.approx(
        findings["top_channel_roi_ratio"]["expected_value"],
        abs=_tol(findings["top_channel_roi_ratio"]),
    )


def test_06_inventory_analysis_matches_registry():
    df, case = _load("06_inventory_analysis")
    findings = {f["metric"]: f for f in case["expected_findings"]}

    at_risk = df[df["stock_level"] < df["reorder_point"]]
    assert at_risk["sku"].nunique() == pytest.approx(
        findings["at_risk_sku_count"]["expected_value"], abs=_tol(findings["at_risk_sku_count"])
    )

    result = registry.calculate_sum(df, "stockout_days")
    assert result.result == pytest.approx(
        findings["total_stockout_days"]["expected_value"], abs=_tol(findings["total_stockout_days"])
    )


def test_07_customer_segmentation_matches_registry():
    df, case = _load("07_customer_segmentation")
    findings = {f["metric"]: f for f in case["expected_findings"]}

    result = registry.segment_analysis(df, "segment", "total_spend")
    top_segment = max(result.result, key=lambda k: result.result[k]["value"])
    assert top_segment == findings["top_segment_by_total_spend"]["expected_value"]
    assert result.result[top_segment]["pct_of_total"] == pytest.approx(
        findings["top_segment_spend_share_pct"]["expected_value"],
        abs=_tol(findings["top_segment_spend_share_pct"]),
    )


def test_08_pricing_analysis_matches_registry():
    df, case = _load("08_pricing_analysis")
    findings = {f["metric"]: f for f in case["expected_findings"]}

    p01 = [FilterSpec(column="product_id", op="==", value="P01")]
    result = registry.compare_periods(
        df[df["product_id"] == "P01"],
        "date",
        "units_sold",
        ("2024-01-01", "2024-04-30"),
        ("2024-05-01", "2024-08-01"),
        agg="mean",
    )
    assert result.result["pct_change"] == pytest.approx(
        findings["p01_pct_unit_change_after_price_increase"]["expected_value"],
        abs=_tol(findings["p01_pct_unit_change_after_price_increase"]),
    )
    assert p01  # keep FilterSpec import exercised for symmetry with other tests


def test_09_revenue_forecast_context_matches_registry():
    df, case = _load("09_revenue_forecast_context")
    findings = {f["metric"]: f for f in case["expected_findings"]}

    result = registry.trend(df, "date", "revenue", freq="MS")
    assert result.result["direction"] == findings["trend_direction"]["expected_value"]
    assert df["date"].nunique() < 12  # too short a history for seasonal forecasting


def test_10_operational_performance_matches_registry():
    df, case = _load("10_operational_performance")
    findings = {f["metric"]: f for f in case["expected_findings"]}

    result = registry.group_by(df, "shift", "defect_rate", agg="mean")
    worst_shift = max(result.result, key=result.result.get)
    assert worst_shift == findings["worst_shift_by_defect_rate"]["expected_value"]
    assert result.result[worst_shift] == pytest.approx(
        findings["worst_shift_defect_rate"]["expected_value"],
        abs=_tol(findings["worst_shift_defect_rate"]),
    )


def test_all_ten_datasets_exist_with_case_files():
    dirs = sorted(p.name for p in DATASETS_DIR.iterdir() if p.is_dir())
    assert len(dirs) == 10
    for d in dirs:
        assert (DATASETS_DIR / d / "data.csv").exists()
        assert (DATASETS_DIR / d / "case.json").exists()
