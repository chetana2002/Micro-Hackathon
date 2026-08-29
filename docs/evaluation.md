# Evaluation

## Status

**Run.** The full 10-case, 2-system sweep has been executed against the real
Gemini API (`gemini-3.5-flash-lite` for both systems). Results:
`evaluation/results/{baseline_results,agent_results,comparison}.json`.
Headline: **agent 80.0/100 vs. baseline 54.5/100, mean across all 10 cases,
winning every individual case and every rubric sub-metric.** Full per-case
breakdown, failure categorization, and honest caveats (single run, cheap
model tier, no repeated trials) in `docs/improvement-changelog.md` Part 1,
`docs/failure-analysis.md`, and `docs/hot-take.md` — read those before citing
the headline number alone.

Reproduce with:

```bash
export GEMINI_API_KEY=...
python evaluation/run_evaluation.py
```

which overwrites `evaluation/results/*.json`. `docs/reproduction.md` has
exact runtime/timing notes (mean 3.4s/case for baseline, 65.9s/case for the
agent, due to 8+ sequential calls plus free-tier rate-limit backoff).

The framework itself (datasets, ground truth, scorer, driver) is also
covered by 28 unit/integration tests using a fake LLM client
(`backend/tests/{unit,integration}/test_*evaluation*.py`,
`test_datasets_ground_truth.py`, `test_run_evaluation.py`), so its logic was
verified correct before ever making a real API call.

## The 10 evaluation datasets

`scripts/generate_datasets.py` deterministically builds all 10 (fixed seeds
per dataset, so re-running it reproduces byte-identical CSVs). Each has a
`case.json` with the question, `expected_findings` (metric + expected value +
tolerance), `expected_evidence` (which tool calls should produce it), and
`known_traps` — specific ways a naive analysis goes wrong on *this* dataset.

`01_sales_decline` is the flagship difficult case, and doubles as the
project's own running example: revenue genuinely declines in Q2 2024, and
North region genuinely accounts for the overwhelming majority of that decline
— both are real, verifiable numbers in the data (confirmed independently
against the Phase 3 tool registry in
`test_01_sales_decline_matches_registry`). But the dataset contains **no
causal driver column** (no marketing spend, pricing, competitor, or promotion
data) — so a system that answers "why" with a specific root cause is
overclaiming, no matter how correct its regional-attribution number is. This
is exactly the distinction Verification's causal-language downgrade exists to
catch.

The other traps: a simulated data-collection gap in `02_regional_performance`
(East region is missing 3 weeks of March records — a naive read sees a
revenue crater that's actually a row-count artifact); reverse-causation risk
in `04_customer_churn` (support tickets correlate with churn, but dissatisfied
customers about to churn plausibly file *more* tickets, not fewer); attribution-
model uncertainty in `05_marketing_roi` ("revenue attributed" isn't measured
incrementality); a single-product, no-control pricing signal in
`08_pricing_analysis` that can't support a catalog-wide elasticity claim; and
`09_revenue_forecast_context`, which has only 9 months of history — too short
to estimate seasonality, so a confident specific Q4 forecast number is
overclaiming regardless of the trend direction being genuinely upward.

## Rubric — reviewed against real score distributions, kept as-is

| Metric | Points | How it's scored |
|---|---|---|
| Numerical correctness | 30 | Deterministic: regex-extracted numbers from the output text, checked against each numeric `expected_findings` value within its `tolerance_abs` |
| Key finding coverage | 25 | Deterministic: numeric findings as above, plus categorical findings (e.g. `"North"`) via case-insensitive substring match |
| Evidence grounding | 20 | LLM-judged |
| Unsupported-claim rate (penalty) | 15 | LLM-judged, inverted: `(1 - rate) * 15` |
| Recommendation grounding | 5 | LLM-judged |
| Business usefulness | 5 | LLM-judged |

This is the same weighting proposed in `docs/architecture.md` before any code
existed, and the brief is explicit that it should not be assumed final —
so, with real data now available (`evaluation/results/*.json`), here is the
actual review: comparing each metric's baseline-vs-agent gap as a percentage
of its own weight (i.e. how much of that metric's available discrimination
the two systems actually used) —

| Metric | Weight | Baseline mean | Agent mean | Gap as % of weight |
|---|---|---|---|---|
| Numerical correctness | 30 | 13.50 | 21.00 | 25.0% |
| Key findings | 25 | 11.25 | 18.75 | 30.0% |
| Evidence grounding | 20 | 12.70 | 18.20 | 27.5% |
| Unsupported claims | 15 | 9.75 | 13.57 | 25.5% |
| Recommendation grounding | 5 | 3.65 | 4.38 | 14.5% |
| Business usefulness | 5 | 3.65 | 4.10 | 9.0% |

Every metric shows a real, positive gap — none is degenerate (always maxed
or always zero for both systems), which would have been the signal to
reweight or drop it. The four metrics most diagnostic of reliability
(numerical correctness, key findings, evidence grounding, unsupported
claims) carry 90 of the 100 points and show the largest relative gaps
(25–30%); the two softer "framing quality" metrics (recommendation
grounding, business usefulness) carry only 10 points and show smaller gaps
(9–14.5%) — both systems tend to *frame* recommendations reasonably well
even when the underlying baseline claim is fabricated, so weighting that
dimension heavily would have diluted the signal that actually separates the
two systems. **Decision: keep the weights as originally proposed** — the
review supports the original allocation rather than contradicting it, which
is itself a legitimate outcome of a real review, not a skipped one.

## Why two different scoring methods for one rubric

Numerical correctness and key-finding coverage are fully deterministic —
regex number/keyword matching — because these are checkable facts about the
text and shouldn't depend on an LLM's mood. Evidence grounding, unsupported-
claim rate, recommendation grounding, and business usefulness require judgment
about a free-text passage that regex cannot make reliably, so they go through
a forced `submit_judge_scores` tool call — a separate, clearly-labeled
scoring-only step (`evaluation/scorer.py::llm_judge_scores`) that never
generates report content, only scores an already-written one.

## The fairness requirement this scorer enforces

The full agent produces a structured `Report` object; the baseline produces
free text. If the scorer read the agent's `Report` as structured JSON while
only reading the baseline's raw text, the two scores would not be measuring
the same thing — the agent would get credit for having *fields*, not for
having *better answers*. `app.reports.render_text.render_report_markdown`
renders the agent's `Report` to plain Markdown before scoring, so both systems
are reduced to the same representation and go through the identical scoring
function. This is enforced by `evaluation/run_evaluation.py::_run_one`, not
left as a convention someone could forget.

## Cost and runtime

`evaluation/run_evaluation.py` records `runtime_seconds` and (for the
baseline, which is one call) exact token usage and cost per case, using the
per-model pricing table in `app/llm/client.py`. The full agent makes ~8+ LLM
calls per run, so its total cost and latency are expected to be higher — by
how much, and whether the quality difference justifies it, is exactly what
running this framework for real is meant to answer honestly, not assume.
