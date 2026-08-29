# Failure Analysis

## Status

A live 10-case, 2-system evaluation run now exists
(`evaluation/results/{baseline_results,agent_results}.json`, `gemini-3.5-flash-lite`
for both systems). This document reports what actually happened, categorized
against the failure taxonomy the architecture was designed around, and is
honest about where the design's hypotheses held and where they didn't.

## Actual baseline failures, categorized

| Category | Cases observed | What actually happened (from the judge's stored `rationale`) |
|---|---|---|
| Numeric fabrication / placeholder values | `03_product_performance`, `04_customer_churn`, `07_customer_segmentation`, `10_operational_performance` (4/10 cases) | The baseline explicitly used hypothetical or "typical pattern" numbers instead of computing real ones — e.g. `10_operational_performance`: "typically averaging around 3.5% to 4.5%" for a defect rate whose real, computable value was 0.0451. This is the single most common baseline failure observed, at 40% of cases. |
| False factual assertion | `01_sales_decline` | Baseline stated "all regions saw some contraction"; the data shows three of four regions were flat or up. Not a fabricated number — a specific, checkable claim that is simply wrong. |
| Data-quality blindness | `02_regional_performance` | Baseline missed the East-region data-collection-gap entirely, analyzing the artifact as if it were a real performance signal — exactly the designed trap. |
| Causal overclaim | `04_customer_churn`, `10_operational_performance` | `04`: treated support-ticket volume as a "primary driver" of churn rather than a correlate. `10`: asserted specific root causes (operator fatigue, staffing) the data cannot establish. |
| Attribution-as-causation | `05_marketing_roi` | Treated attributed revenue as a direct causal return without caveating the attribution model, per the judge (this was the baseline's smallest miss — the report was otherwise strong). |

Baseline correctly avoided its designed trap in `06_inventory_analysis` (handled the warehouse dimension), `08_pricing_analysis` (explicitly avoided generalizing from one product), and `09_revenue_forecast_context` (addressed the seasonality/short-history caveat directly). Score alone doesn't tell this story — the per-case rationale does, which is why `evaluation/results/*.json` and not just `comparison.json` is the primary record.

## Actual agent failures, categorized

| Category | Cases observed | What actually happened |
|---|---|---|
| Incomplete trap coverage (segment/dimension not explored) | `01_sales_decline`, `02_regional_performance`, `03_product_performance`, `07_customer_segmentation` (partial), `06_inventory_analysis` (partial) | The Planner chose a valid but incomplete decomposition — e.g. `01`: trend + correlation instead of a regional breakdown, missing that North alone drives the decline. `02`: didn't notice the East data gap despite it being a real row-count anomaly the profiler surfaces. `03`: never incorporated return rates into the product ranking. |
| Numeric fabrication | **None observed in any of the 10 cases.** | Every case's judge rationale that mentions the agent's numbers describes them as grounded in real calculations. This is the clearest measured contrast with the baseline. |
| Causal overclaim | **None observed.** | `04_customer_churn`: explicitly framed the correlation as non-causal. `09`: declined to output a specific overconfident forecast number. `10`: avoided asserting a specific root cause despite finding the real defect-rate gap. |

## Category-by-category: did the designed mitigation actually work?

| Category (from the pre-registered taxonomy) | Verdict |
|---|---|
| Arithmetic error | **Not observed in either system** on this run, so `recompute()`'s deterministic catch was never exercised by a real mismatch. Still verified by unit tests (`test_verifier.py`) forcing a mismatch synthetically. |
| Causal overclaim | **Mitigation held.** The agent avoided causal overclaims in every case where the baseline made one or came close (`04`, `05`, `10`). |
| Incorrect/missing grouping | **Mitigation partially held.** The Planner's causal-decomposition prompt did not reliably produce a full regional/segment breakdown on `01`, `02`, `03` — this is the agent's actual dominant failure mode on this run, not a category the architecture fully solved. |
| Data-quality blindness | **Mitigation did not fully hold on `02`.** The Data Profiler does surface row-count warnings, but the agent's report for `02_regional_performance` still didn't catch the East-region gap — the profiler's warning existing is not the same as the Planner or Analyst actually acting on it. Worth a closer look before Phase 12-equivalent hardening in a follow-up. |
| Forecasting beyond the data | **Mitigation held.** `09_revenue_forecast_context`: agent reported trend direction and explicit uncertainty, no invented forecast number. |
| Small-sample overconfidence | **Mitigation held.** `08_pricing_analysis`: agent's report avoided generalizing from the single product with a price change. |
| Hallucinated statistic | **Mitigation held completely** — zero instances across all 10 agent reports, vs. 4 explicit instances in the baseline. |

## Honest summary

Five of seven designed mitigations held cleanly on this run; one (data-quality blindness) did not fully translate from "the profiler computes the warning" to "the agent acts on the warning," and one (grouping/decomposition completeness) is the agent's real, measured weak point — not a failure of Verification, but of the Planner not always choosing the most diagnostic decomposition. This matters for how the result should be read: the win over baseline is not "the agent is flawless," it's "the agent's failures are visibly incomplete analyses rather than invisible fabrications" — see `docs/hot-take.md`.
