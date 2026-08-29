"""Generates the 10 synthetic evaluation datasets under datasets/.

Deterministic (fixed seeds per dataset) so re-running this script reproduces
byte-identical CSVs and ground-truth case.json files — required for
docs/reproduction.md. Every expected_findings value in a case.json is
computed here, from the same generated DataFrame, using the same kind of
pandas aggregation the deterministic tool registry performs — so the
ground truth is directly checkable against the data, not hand-guessed.

Run: python scripts/generate_datasets.py
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DATASETS_DIR = ROOT / "datasets"


def _write(dirname: str, df: pd.DataFrame, case: dict) -> None:
    out_dir = DATASETS_DIR / dirname
    out_dir.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_dir / "data.csv", index=False)
    case["dataset"] = f"{dirname}/data.csv"
    with open(out_dir / "case.json", "w") as f:
        json.dump(case, f, indent=2)
    print(f"wrote {dirname}: {len(df)} rows")


# --------------------------------------------------------------------------
# 1. Sales decline (the flagship / deliberately difficult case)
# --------------------------------------------------------------------------
def build_01_sales_decline() -> tuple[pd.DataFrame, dict]:
    rng = np.random.default_rng(101)
    regions = ["North", "South", "East", "West"]
    categories = ["Electronics", "Apparel", "Home"]
    months = pd.date_range("2023-01-01", "2024-06-01", freq="MS")

    base_revenue = {
        ("North", "Electronics"): 12000, ("North", "Apparel"): 7000, ("North", "Home"): 5000,
        ("South", "Electronics"): 9000, ("South", "Apparel"): 6000, ("South", "Home"): 4000,
        ("East", "Electronics"): 8000, ("East", "Apparel"): 5000, ("East", "Home"): 3500,
        ("West", "Electronics"): 7000, ("West", "Apparel"): 4500, ("West", "Home"): 3000,
    }

    rows = []
    for month in months:
        for region in regions:
            for cat in categories:
                base = base_revenue[(region, cat)]
                noise = rng.normal(1.0, 0.04)
                # Deliberate, region-specific decline: North only, starting Q2 2024.
                decline_mult = 1.0
                if region == "North" and month >= pd.Timestamp("2024-04-01"):
                    decline_mult = {"2024-04-01": 0.62, "2024-05-01": 0.55, "2024-06-01": 0.50}[
                        month.strftime("%Y-%m-01")
                    ]
                revenue = round(base * noise * decline_mult, 2)
                units = max(1, int(revenue / rng.uniform(40, 60)))
                rows.append(
                    {
                        "date": month.strftime("%Y-%m-%d"),
                        "region": region,
                        "product_category": cat,
                        "units_sold": units,
                        "revenue": revenue,
                    }
                )
    df = pd.DataFrame(rows)

    dates = pd.to_datetime(df["date"])
    q1_2024 = df[(dates >= "2024-01-01") & (dates <= "2024-03-31")]
    q2_2024 = df[(dates >= "2024-04-01") & (dates <= "2024-06-30")]
    q1_total = round(q1_2024["revenue"].sum(), 2)
    q2_total = round(q2_2024["revenue"].sum(), 2)
    pct_change = round((q2_total - q1_total) / q1_total * 100, 2)

    q1_north = round(q1_2024[q1_2024["region"] == "North"]["revenue"].sum(), 2)
    q2_north = round(q2_2024[q2_2024["region"] == "North"]["revenue"].sum(), 2)
    total_decline = q1_total - q2_total
    north_decline = q1_north - q2_north
    north_share_of_decline = round(north_decline / total_decline * 100, 2)

    case = {
        "question": "Why did revenue decline in Q2 2024, and what should we investigate next?",
        "expected_findings": [
            {
                "claim": "Total revenue declined from Q1 2024 to Q2 2024",
                "metric": "pct_change_q1_to_q2_total_revenue",
                "expected_value": pct_change,
                "tolerance_abs": 0.5,
            },
            {
                "claim": "The North region accounts for the large majority of the Q2 decline",
                "metric": "north_share_of_total_decline_pct",
                "expected_value": north_share_of_decline,
                "tolerance_abs": 2.0,
            },
        ],
        "expected_evidence": [
            "compare_periods(revenue, Q1 2024 vs Q2 2024)",
            "segment_analysis or group_by(region, revenue) for Q1 2024 and Q2 2024",
        ],
        "known_traps": [
            "The dataset contains no causal driver column (no marketing spend, pricing, "
            "competitor, or promotion data). A correct system should quantify North's "
            "contribution to the decline (a supported, descriptive claim) but must NOT "
            "assert a root cause for *why* North declined — that would be an unsupported "
            "causal claim given what's actually in the data.",
            "South, East, and West are flat to slightly up — a system that claims "
            "'revenue declined across the business' is wrong; the decline is regionally "
            "concentrated.",
        ],
    }
    return df, case


# --------------------------------------------------------------------------
# 2. Regional performance (with a data-quality trap)
# --------------------------------------------------------------------------
def build_02_regional_performance() -> tuple[pd.DataFrame, dict]:
    rng = np.random.default_rng(102)
    regions = ["North", "South", "East", "West"]
    weeks = pd.date_range("2024-01-01", "2024-12-30", freq="W-MON")

    base_weekly = {"North": 5000, "South": 4600, "East": 4200, "West": 3900}
    rows = []
    for week in weeks:
        for region in regions:
            # Data-quality trap: East is missing 3 weeks of records in March
            # (simulated system migration), not an actual revenue drop.
            if region == "East" and pd.Timestamp("2024-03-04") <= week <= pd.Timestamp("2024-03-18"):
                continue
            revenue = round(base_weekly[region] * rng.normal(1.0, 0.05), 2)
            margin = round(rng.uniform(0.15, 0.32), 4)
            rows.append(
                {"week": week.strftime("%Y-%m-%d"), "region": region, "revenue": revenue, "profit_margin": margin}
            )
    df = pd.DataFrame(rows)

    totals = df.groupby("region")["revenue"].sum().round(2)
    best_region = totals.idxmax()
    worst_region = totals.idxmin()
    march_east_rows = df[
        (df["region"] == "East")
        & (pd.to_datetime(df["week"]) >= "2024-03-01")
        & (pd.to_datetime(df["week"]) <= "2024-03-31")
    ]

    case = {
        "question": "Which region is performing best and worst this year, and are there any regions we should be concerned about?",
        "expected_findings": [
            {
                "claim": f"{best_region} has the highest total annual revenue",
                "metric": "top_region_by_total_revenue",
                "expected_value": best_region,
            },
            {
                "claim": f"{worst_region} has the lowest total annual revenue",
                "metric": "bottom_region_by_total_revenue",
                "expected_value": worst_region,
            },
        ],
        "expected_evidence": ["group_by(region, revenue, sum) across all weeks"],
        "known_traps": [
            f"East region has only {len(march_east_rows)} recorded weeks in March 2024 "
            "(3 weeks of records are missing due to a simulated system migration), which "
            "makes March look like a severe East revenue decline if analyzed naively by "
            "week count or raw sum. A correct system should notice the row-count gap "
            "(via the dataset profiler's row counts per region/period) before concluding "
            "East had a real March decline.",
        ],
    }
    return df, case


# --------------------------------------------------------------------------
# 3. Product performance
# --------------------------------------------------------------------------
def build_03_product_performance() -> tuple[pd.DataFrame, dict]:
    rng = np.random.default_rng(103)
    products = [f"P{i:03d}" for i in range(1, 21)]
    categories = {p: rng.choice(["Electronics", "Apparel", "Home", "Toys"]) for p in products}
    months = pd.date_range("2024-01-01", "2024-06-01", freq="MS")

    base_units = {p: rng.integers(50, 500) for p in products}
    rows = []
    for month in months:
        for p in products:
            units = max(0, int(base_units[p] * rng.normal(1.0, 0.15)))
            price = round(rng.uniform(10, 200), 2)
            revenue = round(units * price, 2)
            returns = int(units * rng.uniform(0.0, 0.08))
            rows.append(
                {
                    "date": month.strftime("%Y-%m-%d"),
                    "product_id": p,
                    "category": categories[p],
                    "units_sold": units,
                    "revenue": revenue,
                    "returns": returns,
                }
            )
    df = pd.DataFrame(rows)

    totals = df.groupby("product_id")["revenue"].sum().round(2).sort_values(ascending=False)
    top_product = totals.index[0]
    bottom_product = totals.index[-1]

    case = {
        "question": "Which products are driving the most revenue, and which are underperforming?",
        "expected_findings": [
            {
                "claim": f"{top_product} is the top revenue-generating product over the period",
                "metric": "top_product_by_total_revenue",
                "expected_value": top_product,
            },
            {
                "claim": f"{bottom_product} is the lowest revenue-generating product over the period",
                "metric": "bottom_product_by_total_revenue",
                "expected_value": bottom_product,
            },
        ],
        "expected_evidence": ["top_n(product_id, revenue)", "bottom_n(product_id, revenue)"],
        "known_traps": [
            "Revenue ranking alone doesn't account for return rates — a product with high "
            "revenue but also a high return rate is a weaker performer than the raw ranking "
            "suggests; a thorough answer should surface returns as a caveat."
        ],
    }
    return df, case


# --------------------------------------------------------------------------
# 4. Customer churn
# --------------------------------------------------------------------------
def build_04_customer_churn() -> tuple[pd.DataFrame, dict]:
    rng = np.random.default_rng(104)
    n = 500
    tenure = rng.integers(1, 60, size=n)
    support_tickets = rng.poisson(1.5, size=n)
    # Churn probability rises with support tickets and falls with tenure —
    # deliberately confounded so ticket count and churn correlate without
    # ticket count being asserted as the cause.
    churn_prob = 1 / (1 + np.exp(-(0.35 * support_tickets - 0.03 * tenure - 1.0)))
    churned = rng.binomial(1, churn_prob)
    monthly_spend = np.round(rng.uniform(20, 300, size=n) * (1 - 0.1 * churned), 2)

    df = pd.DataFrame(
        {
            "customer_id": [f"C{i:04d}" for i in range(n)],
            "tenure_months": tenure,
            "monthly_spend": monthly_spend,
            "support_tickets": support_tickets,
            "churned": churned.astype(bool),
        }
    )

    corr = round(df["support_tickets"].corr(df["churned"].astype(int)), 4)
    churn_rate = round(df["churned"].mean() * 100, 2)

    case = {
        "question": "What factors are associated with customer churn, and what should we do about it?",
        "expected_findings": [
            {
                "claim": "Support ticket count is positively correlated with churn",
                "metric": "correlation_support_tickets_churned",
                "expected_value": corr,
                "tolerance_abs": 0.05,
            },
            {
                "claim": "Overall churn rate in the dataset",
                "metric": "overall_churn_rate_pct",
                "expected_value": churn_rate,
                "tolerance_abs": 1.0,
            },
        ],
        "expected_evidence": ["correlation(support_tickets, churned)", "calculate_average(churned)"],
        "known_traps": [
            "Support tickets correlating with churn does not establish that tickets cause "
            "churn — the reverse is equally plausible (customers already planning to churn "
            "may file more tickets out of frustration). A correct system should flag this as "
            "an association, not a cause, and recommend further investigation rather than a "
            "confident causal claim."
        ],
    }
    return df, case


# --------------------------------------------------------------------------
# 5. Marketing ROI
# --------------------------------------------------------------------------
def build_05_marketing_roi() -> tuple[pd.DataFrame, dict]:
    rng = np.random.default_rng(105)
    channels = ["Search", "Social", "Email", "Display", "Affiliate"]
    months = pd.date_range("2024-01-01", "2024-06-01", freq="MS")
    roi_factor = {"Search": 4.2, "Social": 2.1, "Email": 5.5, "Display": 1.6, "Affiliate": 3.0}

    rows = []
    for month in months:
        for ch in channels:
            spend = round(rng.uniform(5000, 20000), 2)
            revenue_attributed = round(spend * roi_factor[ch] * rng.normal(1.0, 0.1), 2)
            rows.append(
                {"month": month.strftime("%Y-%m-%d"), "channel": ch, "spend": spend, "revenue_attributed": revenue_attributed}
            )
    df = pd.DataFrame(rows)

    by_channel = df.groupby("channel").agg(spend=("spend", "sum"), revenue=("revenue_attributed", "sum"))
    by_channel["roi"] = round(by_channel["revenue"] / by_channel["spend"], 4)
    best_channel = by_channel["roi"].idxmax()
    best_roi = round(by_channel["roi"].max(), 2)

    case = {
        "question": "Which marketing channel gives us the best return, and should we shift budget toward it?",
        "expected_findings": [
            {
                "claim": f"{best_channel} has the highest ROI (revenue attributed / spend)",
                "metric": "top_channel_by_roi",
                "expected_value": best_channel,
            },
            {
                "claim": f"{best_channel}'s ROI ratio",
                "metric": "top_channel_roi_ratio",
                "expected_value": best_roi,
                "tolerance_abs": 0.3,
            },
        ],
        "expected_evidence": ["group_by(channel, spend, sum)", "group_by(channel, revenue_attributed, sum)"],
        "known_traps": [
            "'Revenue attributed' is an attribution-model output, not measured incremental "
            "revenue — some of it is likely revenue that would have happened anyway "
            "(organic/brand demand). A recommendation to 'shift budget toward the top ROI "
            "channel' should be flagged as dependent on attribution-model accuracy, not "
            "presented as a guaranteed causal return."
        ],
    }
    return df, case


# --------------------------------------------------------------------------
# 6. Inventory analysis
# --------------------------------------------------------------------------
def build_06_inventory_analysis() -> tuple[pd.DataFrame, dict]:
    rng = np.random.default_rng(106)
    skus = [f"SKU{i:03d}" for i in range(1, 31)]
    warehouses = ["W1", "W2", "W3"]
    months = pd.date_range("2024-01-01", "2024-06-01", freq="MS")

    rows = []
    for month in months:
        for sku in skus:
            for wh in warehouses:
                reorder_point = int(rng.integers(50, 150))
                stock_level = int(max(0, rng.normal(reorder_point * 1.3, reorder_point * 0.4)))
                stockout_days = int(rng.poisson(1)) if stock_level < reorder_point else 0
                rows.append(
                    {
                        "date": month.strftime("%Y-%m-%d"),
                        "sku": sku,
                        "warehouse": wh,
                        "stock_level": stock_level,
                        "reorder_point": reorder_point,
                        "stockout_days": stockout_days,
                    }
                )
    df = pd.DataFrame(rows)

    at_risk = df[df["stock_level"] < df["reorder_point"]]
    at_risk_skus = sorted(at_risk["sku"].unique().tolist())
    total_stockout_days = int(df["stockout_days"].sum())

    case = {
        "question": "Which SKUs are at risk of stocking out, and how big is the problem?",
        "expected_findings": [
            {
                "claim": "Number of SKUs that have fallen below their reorder point at least once",
                "metric": "at_risk_sku_count",
                "expected_value": len(at_risk_skus),
                "tolerance_abs": 2,
            },
            {
                "claim": "Total stockout-days recorded across all SKUs and warehouses",
                "metric": "total_stockout_days",
                "expected_value": total_stockout_days,
                "tolerance_abs": 5,
            },
        ],
        "expected_evidence": ["segment_analysis or filter(stock_level < reorder_point)", "calculate_sum(stockout_days)"],
        "known_traps": [
            "A SKU can be 'below reorder point' at one warehouse while healthy at others — "
            "aggregating stock risk at the SKU level without the warehouse dimension can "
            "overstate or understate the actual operational risk."
        ],
    }
    return df, case


# --------------------------------------------------------------------------
# 7. Customer segmentation
# --------------------------------------------------------------------------
def build_07_customer_segmentation() -> tuple[pd.DataFrame, dict]:
    rng = np.random.default_rng(107)
    n = 400
    segment = rng.choice(["Premium", "Standard", "Budget"], size=n, p=[0.2, 0.5, 0.3])
    spend_base = {"Premium": 800, "Standard": 300, "Budget": 100}
    total_spend = np.round([rng.normal(spend_base[s], spend_base[s] * 0.2) for s in segment], 2)
    freq_base = {"Premium": 12, "Standard": 6, "Budget": 3}
    purchase_frequency = np.array([max(1, int(rng.normal(freq_base[s], 2))) for s in segment])
    avg_order_value = np.round(total_spend / purchase_frequency, 2)

    df = pd.DataFrame(
        {
            "customer_id": [f"C{i:04d}" for i in range(n)],
            "segment": segment,
            "total_spend": total_spend,
            "purchase_frequency": purchase_frequency,
            "avg_order_value": avg_order_value,
        }
    )

    by_segment = df.groupby("segment")["total_spend"].sum().round(2)
    total = by_segment.sum()
    shares = (by_segment / total * 100).round(2)
    top_segment_by_spend = by_segment.idxmax()

    case = {
        "question": "How much does each customer segment contribute to total revenue, and where should we focus retention efforts?",
        "expected_findings": [
            {
                "claim": f"{top_segment_by_spend} segment contributes the largest share of total spend",
                "metric": "top_segment_by_total_spend",
                "expected_value": top_segment_by_spend,
            },
            {
                "claim": f"{top_segment_by_spend} segment's share of total spend",
                "metric": "top_segment_spend_share_pct",
                "expected_value": float(shares.max()),
                "tolerance_abs": 3.0,
            },
        ],
        "expected_evidence": ["segment_analysis(segment, total_spend)"],
        "known_traps": [
            "Highest total spend by segment is partly a function of segment size (Standard "
            "is the largest group by customer count) — a system should distinguish "
            "'contributes the most total revenue' from 'is the most valuable customer on "
            "average', which requires looking at avg_order_value / per-customer spend too."
        ],
    }
    return df, case


# --------------------------------------------------------------------------
# 8. Pricing analysis
# --------------------------------------------------------------------------
def build_08_pricing_analysis() -> tuple[pd.DataFrame, dict]:
    rng = np.random.default_rng(108)
    products = [f"P{i:02d}" for i in range(1, 11)]
    months = pd.date_range("2024-01-01", "2024-08-01", freq="MS")

    rows = []
    for p in products:
        base_price = round(rng.uniform(20, 100), 2)
        base_units = rng.integers(200, 800)
        # One product (P01) gets a deliberate mid-period price increase with a
        # units drop, to give a genuine (if still confounded-by-seasonality) signal.
        for i, month in enumerate(months):
            price = base_price
            if p == "P01" and month >= pd.Timestamp("2024-05-01"):
                price = round(base_price * 1.25, 2)
            units = int(base_units * rng.normal(1.0, 0.08))
            if p == "P01" and month >= pd.Timestamp("2024-05-01"):
                units = int(units * 0.78)
            rows.append({"date": month.strftime("%Y-%m-%d"), "product_id": p, "price": price, "units_sold": units})
    df = pd.DataFrame(rows)

    p01 = df[df["product_id"] == "P01"]
    before = p01[pd.to_datetime(p01["date"]) < "2024-05-01"]["units_sold"].mean()
    after = p01[pd.to_datetime(p01["date"]) >= "2024-05-01"]["units_sold"].mean()
    pct_unit_change = round((after - before) / before * 100, 2)

    case = {
        "question": "Does raising prices reduce units sold? Look specifically at P01, which changed price mid-year.",
        "expected_findings": [
            {
                "claim": "P01's average monthly units sold dropped after its May 2024 price increase",
                "metric": "p01_pct_unit_change_after_price_increase",
                "expected_value": pct_unit_change,
                "tolerance_abs": 3.0,
            },
        ],
        "expected_evidence": ["compare_periods(units_sold, before vs after 2024-05-01, filtered to product_id=P01)"],
        "known_traps": [
            "Only one product (P01) has a price change in this dataset; the other 9 products "
            "have constant prices and cannot be used to generalize a price-elasticity "
            "conclusion. A system should not claim 'raising prices reduces demand across our "
            "catalog' from a single-product, single-event observation — and should note that "
            "seasonality (not price alone) could also explain part of the change."
        ],
    }
    return df, case


# --------------------------------------------------------------------------
# 9. Revenue forecast context (deliberately insufficient for confident forecasting)
# --------------------------------------------------------------------------
def build_09_revenue_forecast_context() -> tuple[pd.DataFrame, dict]:
    rng = np.random.default_rng(109)
    # Only 9 months of history — deliberately too short to support a
    # confident seasonal forecast, which is the point of this case.
    months = pd.date_range("2024-01-01", "2024-09-01", freq="MS")
    base = 100000
    trend_per_month = 1500
    rows = []
    for i, month in enumerate(months):
        revenue = round(base + trend_per_month * i + rng.normal(0, 4000), 2)
        rows.append({"date": month.strftime("%Y-%m-%d"), "revenue": revenue})
    df = pd.DataFrame(rows)

    case = {
        "question": "Based on this data, what should we expect revenue to be next quarter (Q4)?",
        "expected_findings": [
            {
                "claim": "Revenue shows a generally increasing trend over the observed months",
                "metric": "trend_direction",
                "expected_value": "increasing",
            },
        ],
        "expected_evidence": ["trend(date, revenue)"],
        "known_traps": [
            "Only 9 months of history exist and there is no prior-year data, so seasonality "
            "cannot be estimated. A system that outputs a specific confident Q4 revenue "
            "number (rather than a trend direction plus an explicit statement that the data "
            "is insufficient for a reliable seasonal forecast) is overclaiming beyond what "
            "the data supports."
        ],
    }
    return df, case


# --------------------------------------------------------------------------
# 10. Operational performance
# --------------------------------------------------------------------------
def build_10_operational_performance() -> tuple[pd.DataFrame, dict]:
    rng = np.random.default_rng(110)
    plants = ["Plant-A", "Plant-B", "Plant-C"]
    shifts = ["Morning", "Afternoon", "Night"]
    days = pd.date_range("2024-01-01", "2024-03-31", freq="D")

    defect_base = {"Morning": 0.015, "Afternoon": 0.02, "Night": 0.045}
    rows = []
    for day in days:
        for plant in plants:
            for shift in shifts:
                orders = int(rng.integers(80, 200))
                defect_rate = round(max(0.0, rng.normal(defect_base[shift], 0.01)), 4)
                cycle_time = round(rng.normal(22 if shift != "Night" else 27, 3), 2)
                rows.append(
                    {
                        "date": day.strftime("%Y-%m-%d"),
                        "plant": plant,
                        "shift": shift,
                        "orders_processed": orders,
                        "defect_rate": defect_rate,
                        "cycle_time_minutes": cycle_time,
                    }
                )
    df = pd.DataFrame(rows)

    by_shift = df.groupby("shift")["defect_rate"].mean().round(4)
    worst_shift = by_shift.idxmax()

    case = {
        "question": "Which shift has the highest defect rate, and is it worth investigating further?",
        "expected_findings": [
            {
                "claim": f"{worst_shift} shift has the highest average defect rate",
                "metric": "worst_shift_by_defect_rate",
                "expected_value": worst_shift,
            },
            {
                "claim": f"{worst_shift} shift's average defect rate",
                "metric": "worst_shift_defect_rate",
                "expected_value": float(by_shift.max()),
                "tolerance_abs": 0.005,
            },
        ],
        "expected_evidence": ["group_by(shift, defect_rate, mean)"],
        "known_traps": [
            "Defect rate differences by shift could reflect staffing/training differences "
            "(a real operational cause) or could reflect that fewer supervisors review "
            "night-shift output (a measurement artifact) — the dataset alone cannot "
            "distinguish these, so a root-cause claim beyond 'night shift has a higher "
            "measured defect rate' is unsupported."
        ],
    }
    return df, case


def main() -> None:
    builders = [
        ("01_sales_decline", build_01_sales_decline),
        ("02_regional_performance", build_02_regional_performance),
        ("03_product_performance", build_03_product_performance),
        ("04_customer_churn", build_04_customer_churn),
        ("05_marketing_roi", build_05_marketing_roi),
        ("06_inventory_analysis", build_06_inventory_analysis),
        ("07_customer_segmentation", build_07_customer_segmentation),
        ("08_pricing_analysis", build_08_pricing_analysis),
        ("09_revenue_forecast_context", build_09_revenue_forecast_context),
        ("10_operational_performance", build_10_operational_performance),
    ]
    for dirname, builder in builders:
        df, case = builder()
        _write(dirname, df, case)


if __name__ == "__main__":
    main()
