# InsightForge — Evidence-Backed Business Analytics Agent

Built for the micro1 Agentic Workflows Hackathon.

**Status:** fully implemented, tested (151 backend tests, all passing without
an API key), and evaluated live against the real Gemini API. **Result: the
full agent scored 80.0/100 vs. the baseline's 54.5/100, mean across all 10
evaluation cases, winning every case and every rubric sub-metric.** See
[`docs/evaluation.md`](docs/evaluation.md) for the full breakdown and
[`docs/limitations.md`](docs/limitations.md) for what this result does and
doesn't establish (one run, no repeated trials, a free-tier model).

## Who has the problem, and what's the bottleneck?

Business, data, and operations analysts who need to answer questions like "why
did revenue decline in Q2?" from a spreadsheet. The bottleneck isn't getting
an LLM to *sound like* an analyst — it's that a single LLM call asked to
analyze a dataset and answer a business question will confidently produce
arithmetic errors, unsupported conclusions, wrong aggregations, correlation
dressed up as causation, and outright invented numbers, with no signal
distinguishing the correct parts of its answer from the wrong parts. That
gap — between "sounds authoritative" and "is actually checkable" — is what
makes this kind of output unsafe to hand a business decision-maker as-is.

## Why is this valuable?

Because the fix isn't "use a smarter model" — it's workflow design. If
calculation and self-judgment are separated (deterministic code calculates,
an independent stage verifies), and every claim is required to carry a
traceable link back to the exact computation that produced it, then a report
can honestly distinguish "I calculated this and confirmed it independently"
from "the data doesn't actually support this claim" — instead of asserting
both with the same confident tone. The live evaluation below measures whether
that actually holds, rather than just arguing it should.

## The baseline

One general-purpose LLM call, no tools, no verification, exactly the system
prompt specified in the original brief: *"You are a business analyst.
Analyze the provided dataset and answer the user's question. Provide
calculations, insights and recommendations."* It receives the identical
dataset and question as the full agent — see
[`docs/baseline.md`](docs/baseline.md) for how fairness between the two
systems is enforced (and tested, not just asserted).

## What the agent adds

An 8-stage pipeline — Data Profiler → Analysis Planner → Data Analyst →
Evidence Builder → Verification Agent → Insight Synthesizer → Recommendation
Engine → Report Generator — where the LLM plans, interprets, and writes
prose, and deterministic pandas code does every calculation. The
differentiator is the Verification stage: it independently *recomputes* every
numeric claim against the actual data (catching arithmetic errors
mechanically, no LLM judgment needed), and it applies a hard rule that a
causal-worded claim can never be marked fully verified by the LLM's own say-so
— only downgraded. Full design rationale, including the specific bugs found
while building each stage, is in [`docs/agent-design.md`](docs/agent-design.md).

## How improvement is measured, and what was found

[`evaluation/`](evaluation/) runs both systems over the same 10 synthetic
business-analysis datasets (sales decline, regional performance, product
performance, churn, marketing ROI, inventory, segmentation, pricing, revenue-
forecast context, operational performance), each with hand-designed ground
truth and at least one deliberately difficult analytical trap. Both systems'
outputs are reduced to the same plain-text representation and scored by the
identical rubric (numerical correctness, key-finding coverage, evidence
grounding, unsupported-claim rate, recommendation grounding, business
usefulness) — this fairness requirement is enforced in code, not just
described.

**Real result:** agent 80.0/100, baseline 54.5/100, mean across all 10 cases
— the agent won every case (from +5.0 to +76.0) and every one of the 6 rubric
sub-metrics. The gap is not evenly distributed by luck: the baseline's most
common failure, in 4 of 10 cases, was stating a specific, confident placeholder
number ("typically averaging around 3.5% to 4.5%") when it had no way to
actually compute the real one (0.0451, in that case) from what it was shown.
**Zero of the agent's 10 reports contained a fabricated number** — every
claim traced to a real calculation. Where the agent lost points, it was for
incomplete analysis (missing a trap dimension), never for inventing one. Full
per-case breakdown in [`docs/evaluation.md`](docs/evaluation.md) and
[`docs/failure-analysis.md`](docs/failure-analysis.md).

## What failed, and what we learned

Real bugs were found and fixed during development — each one caught by an
actual failing test or a live end-to-end run, documented with the specific
evidence in [`docs/improvement-changelog.md`](docs/improvement-changelog.md).
Two stand out. First: **127 passing automated backend tests did not catch a
missing CORS configuration that completely broke the frontend in a real
browser** — because `TestClient` and `curl`, unlike a browser, don't enforce
CORS; it was only caught by running the real backend and frontend together
behind a live browser. Second: the only available LLM credential turned out
to be a Gemini key, not the Anthropic one the project was designed against —
a real, cost-driven pivot made mid-build, requiring a full port of the LLM
client that (by design) needed zero changes to any of the 7 agent modules.

The resulting lesson, in [`docs/hot-take.md`](docs/hot-take.md): the
baseline's dominant failure wasn't causal overclaiming specifically (the
brief's own candidate hypothesis) — it was confident numeric fabrication
under uncertainty, a related but distinct and more common failure. And
separately: a passing test suite is itself a claim, and it needed the same
kind of independent, different-mechanism verification (a live browser, a
live API call) that this project's Verification Agent applies to business
insights.

## Quick facts

- Backend: Python / FastAPI / pandas / SQLite (`backend/`)
- Frontend: Next.js / TypeScript / Tailwind / hand-written shadcn-style
  components (`frontend/`) — see [`docs/limitations.md`](docs/limitations.md)
  for why the shadcn CLI itself couldn't run here
- LLM: Google Gemini, model `gemini-3.5-flash-lite` — identical across the
  baseline, every agent stage, and the evaluation judge (ported mid-build
  from Anthropic Claude; see `docs/improvement-changelog.md`)
- 151 backend tests passing without needing an API key (unit + integration,
  using an injectable fake LLM client), plus a completed live evaluation run

## Documentation map

- [`docs/architecture.md`](docs/architecture.md) — system design, the LLM vs. deterministic-code split
- [`docs/agent-design.md`](docs/agent-design.md) — per-stage design rationale
- [`docs/baseline.md`](docs/baseline.md) — the fair baseline and how fairness is enforced
- [`docs/evaluation.md`](docs/evaluation.md) — datasets, rubric, scorer design, and the real results
- [`docs/improvement-changelog.md`](docs/improvement-changelog.md) — the real baseline-vs-agent comparison, plus every bug found and fixed, with evidence
- [`docs/failure-analysis.md`](docs/failure-analysis.md) — actual failure categorization from the live run, checked against the designed mitigations
- [`docs/limitations.md`](docs/limitations.md) — everything not yet done, and why
- [`docs/reproduction.md`](docs/reproduction.md) — exact commands and verified outputs
- [`docs/hot-take.md`](docs/hot-take.md) — the most important thing learned, grounded in the real evaluation evidence
