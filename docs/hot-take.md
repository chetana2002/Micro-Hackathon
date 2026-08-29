# Hot Take

**Status: evidence-based, from one real run — not a statistically repeated
result.** A live 10-case, 2-system evaluation now exists
(`evaluation/results/*.json`, both systems on `gemini-3.5-flash-lite`). This
is a single run, on one (cheap, "lite"-tier) model, with no repeated trials —
real LLM stochasticity means a second run would likely shift individual case
scores (an earlier single-case smoke test of `01_sales_decline` actually
scored the agent *below* the baseline before this full run scored it above,
see `docs/improvement-changelog.md` Part 1). The pattern below held
consistently enough across all 10 cases that it's worth stating as this
project's actual finding, but "worth stating" is different from "proven at
scale" — a proper claim would need multiple runs per case and would ideally
test more than one model tier.

## What the evidence actually shows

The project brief offers a candidate hypothesis and explicitly warns not to
assume it in advance: that LLMs are unreliable at business analysis
specifically because the same model both calculates and judges its own
claims. The real evaluation data supports a **related but more specific**
finding than that:

> **The baseline's dominant failure mode was not causal overclaiming — it
> was confident numeric fabrication under uncertainty.** Given a question it
> couldn't actually compute an answer to from what it was shown, the
> baseline didn't decline, hedge vaguely, or ask for more data. It produced a
> specific, plausible-sounding number anyway, stated with the same
> confidence as its correct ones.

Counting the judge's own per-case rationale (`docs/failure-analysis.md` has
the full breakdown): 4 of 10 baseline reports contained an explicit
placeholder or "typical pattern" value presented as if computed — e.g.
`10_operational_performance`'s "typically averaging around 3.5% to 4.5%"
where the real, computable figure was 0.0451. Only 2 of 10 involved a clear
causal overclaim. Fabrication under uncertainty was twice as common as
causal overclaiming in this run. The self-judgment hypothesis is *not
wrong* — the agent's causal-downgrade rule did prevent every causal overclaim
the baseline made or came close to (`04`, `05`, `10`) — but it's the smaller
piece of the actual gap. The bigger piece is that the baseline, with no tool
access and no way to say "I don't have enough information to compute this,"
defaulted to inventing a number rather than admitting the gap.

The clean, measured contrast: **zero of the agent's 10 reports contained a
fabricated number** (every claim traced to a real `CalculationResult`), while
the agent's own failures were a *different kind of failure entirely* —
incomplete analyses (missing the regional-concentration trap in
`01_sales_decline`, missing the East-region data gap in
`02_regional_performance`), never invented ones. An incomplete analysis is
visible and fixable (extend the Planner's prompt, add a decomposition step);
a fabricated number dressed as fact is not visible to a reader without
independently re-deriving it themselves.

## The secondary finding, from building the project itself

A different real pattern showed up in *this project's own construction*, not
in the evaluation data, and it's worth keeping distinct rather than
conflating the two: every one of the 8 engineering bugs found during
development (`docs/improvement-changelog.md` Part 2) was caught by either a
failing automated test or a live end-to-end run — never by writing the code
carefully, and never by a passing test suite alone. The sharpest instance:
127 passing backend tests, including a full HTTP integration suite, did not
catch a missing CORS configuration that broke the frontend outright, because
none of those tests were a real browser. The same principle the Verification
Agent applies to business claims — recompute against the real thing, don't
trust a proxy for it — turned out to describe how this project's own
correctness had to be established too.

## What would change this conclusion

This is one run. The two things most likely to change the specific numbers
(not necessarily the qualitative pattern) are: running multiple trials per
case to check how much of the ±5-to-76-point spread is signal vs. model
variance, and re-running with a more capable model tier than
`gemini-3.5-flash-lite` (chosen for free-tier quota reasons, not
capability — see `docs/improvement-changelog.md` Iteration 8) to see whether
the agent's incomplete-decomposition failures shrink with a stronger
Planner. Both are natural next steps this document does not currently claim
to have done.
