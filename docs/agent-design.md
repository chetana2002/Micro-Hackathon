# Agent Design

This document explains *why* each of the eight pipeline stages is built the way
it is — the prompts, the tool schemas, and the specific guardrails that keep the
LLM from doing the one thing this whole project exists to prevent: asserting a
number or a conclusion the data doesn't actually support.

Every stage lives in `backend/app/agents/`, is backed by a typed Pydantic model
in `backend/app/models/`, and is unit-tested against a fake LLM client
(`backend/tests/unit/fakes.py`) so its logic is verified without needing a live
API key. See `docs/reproduction.md` for how to run those tests yourself.

## The recurring pattern: forced tool use, not parsed free text

Every LLM-backed stage after the profiler calls the model with `tool_choice`
forced to a single stage-specific tool (`submit_analysis_plan`,
`submit_evidence`, `submit_verification`, `submit_insights`,
`submit_recommendations`). This is a deliberate choice over asking the model to
write JSON in its response text and parsing it: forced tool use gets JSON-Schema
validation for free (wrong types or missing fields fail before this code even
sees them), and it means "did the model actually engage with the task" is a
simple check (`response.tool_calls` is non-empty) rather than a fragile
free-text parse. Every agent module raises a `ValueError` immediately if the
forced tool call didn't come back — no silent fallback, no guessing.

## 1. Data Profiler (`app/profiling/profiler.py`)

No LLM involvement at all. This is the one stage where "LLM vs. deterministic
code" isn't even a design choice to defend — the brief is explicit that dataset
statistics must never be invented, so this is 100% pandas. Semantic column-type
inference (numeric/categorical/date/boolean/identifier/text) uses a handful of
heuristics: date-parsing is only attempted on non-numeric dtypes (an integer
"year" column must never be reinterpreted as a nanosecond-epoch date, which is
exactly what `pd.to_datetime` on a numeric Series would otherwise do); a numeric-
looking string check runs regardless of whether the column was bucketed as
"categorical" or "text" by cardinality, because a 5-row column of `"$1,000"`-style
values has few unique values and was originally misclassified — Phase 2's own
unit tests caught this and it's fixed (see `docs/improvement-changelog.md`).

## 2. Analysis Planner (`app/agents/planner.py`)

Input: `DatasetProfile` + the business question. Output: `AnalysisPlan`, an
ordered list of `AnalysisStep`s. The `submit_analysis_plan` tool's schema
constrains `operation` to an `enum` built directly from
`TOOL_REGISTRY.keys()` — the planner cannot propose an operation that doesn't
exist, and if it somehow did, this code raises before the plan reaches the Data
Analyst. The system prompt also explicitly tells the planner that a "why"
question requires a step that checks whether the data supports a causal
conclusion at all, not just a descriptive one — pushing the causal-overclaim
concern as early into the pipeline as possible, rather than leaving it entirely
to Verification to catch after the fact.

## 3. Data Analyst (`app/agents/analyst.py`, `app/tools/schemas.py`)

This is the stage where "the model never performs arithmetic" is actually
enforced, not just stated. The model sees the 11 deterministic tools
(`app/tools/registry.py`) as function-calling schemas and runs a bounded
(`MAX_TURNS = 8`) loop: it picks a tool and arguments, this code executes the
real pandas function and returns the exact `CalculationResult` as the tool
result, and the loop continues until the model stops requesting tools. There is
no code path anywhere in this stage that executes model-generated code — the
only thing the model can do is name one of 11 fixed functions and supply
JSON-Schema-validated arguments. An unrecognized tool name is caught and
returned to the model as an `is_error` tool result (so the model can retry
sensibly) rather than crashing the loop.

## 4. Evidence Builder (`app/agents/evidence_builder.py`)

This stage is deliberately the most restricted of all of them. The model is
given a numbered list of `CalculationResult`s and asked to write claims, but it
may only *reference* a calculation by index (`calculation_index`) — every other
field on the resulting `Evidence` object (`source_operation`, `source_columns`,
`filters`, `calculation` (the reproducible expression), and `result`) is copied
by this code directly from the referenced `CalculationResult`. The model
contributes exactly two things: the claim's wording and an initial confidence
estimate. This means a claim's displayed number is architecturally incapable of
being a model transcription error — it's the same object.

`build_evidence` returns `EvidenceItem(evidence, calculation)` pairs rather than
bare `Evidence` objects, specifically so the Verification stage can recompute
against the calculation's original parameters (`agg`, `n`, `freq`, filters) —
information the report-facing `Evidence` model deliberately doesn't carry. This
pairing was added when wiring the orchestrator end-to-end made clear that
`Evidence` alone wasn't enough for `verify_claim` to do its job (see the
changelog).

## 5. Verification Agent (`app/agents/verifier.py`) — the key differentiator

This is the stage the whole project's thesis rests on, so it's split explicitly
into a deterministic half and an LLM-judged half, and documented that way in
the module itself:

1. **Deterministic recompute.** `recompute()` re-executes the exact recorded
   operation, columns, parameters, and filters against the dataset through the
   *same* tool registry the analyst used, and diffs the fresh result against
   the reported one (`_numerically_close`, 1% relative tolerance). A mismatch
   short-circuits straight to `CONTRADICTED` with `corrected_value` set — no LLM
   call happens at all for this check. This catches transcription errors,
   result corruption, or non-determinism mechanically.

   *Known limitation:* this confirms the recorded operation/parameters
   reproduce the recorded number — it does **not** independently re-derive
   which operation/columns/filters *should* have been used from the claim's
   text. A wrong-but-internally-consistent analysis choice made upstream (right
   arithmetic, wrong column) would pass this check. This is recorded in
   `docs/limitations.md`, not glossed over.

2. **Deterministic causal-language pre-filter.** A keyword scan
   (`_contains_causal_language`: "because", "caused by", "drove", "leads to",
   ...) flags candidate causal claims *before* the LLM is asked anything.

3. **LLM-judged verdict**, informed by (2). The LLM assesses whether the data
   actually supports any causal language, and whether there's missing context
   or contradiction. Critically, this code does not trust the LLM to self-
   regulate here: **if the claim contains causal language and the LLM says
   VERIFIED anyway, this code forcibly downgrades the status to
   `PARTIALLY_VERIFIED`**, appends an issue explaining why, and caps confidence
   at 0.6. The LLM can only make a verdict *worse* than what it proposed; it can
   never single-handedly clear a causal claim to fully verified. This is the
   literal mechanism behind the brief's own worked example ("North region
   caused the revenue decline" → `PARTIALLY_VERIFIED`).

## 6. Insight Synthesizer (`app/agents/synthesizer.py`)

`UNSUPPORTED` and `CONTRADICTED` verification results are filtered out by this
code *before* the prompt is even constructed — the synthesizer's system prompt
never has the opportunity to narrate a claim that failed verification, because
that claim was never in its input. Each `Insight`'s `evidence` and `confidence`
are taken directly from the qualifying `VerificationResult`, not re-asserted by
the model. A `PARTIALLY_VERIFIED` insight automatically gets its verification
issues appended to `limitations` — the caveat travels with the insight whether
or not the model chose to mention it.

## 7. Recommendation Engine (`app/agents/recommender.py`)

Recommendations reference `insight_indices`; `supporting_evidence` is gathered
by this code from those insights. There is no path for a recommendation to cite
evidence that was never bound to a verified insight — the model cannot invent a
supporting citation, only choose among the insights it was actually given.

## 8. Report Generator (`app/agents/report_generator.py`, `app/charts/chart_builder.py`)

The LLM contributes exactly one thing here: the executive summary's prose.
Every structural section — dataset overview, data quality warnings, key
findings, evidence, charts, recommendations — is assembled by this code from
the typed objects produced upstream. `open_questions` is derived automatically
from any `UNSUPPORTED`/`CONTRADICTED` verification results (nothing requires
the model to remember to mention them), and `limitations` is deduplicated
across insights.

Charts (`app/charts/chart_builder.py`) are built entirely from
`CalculationResult.result` data with a fixed per-operation mapping
(`trend`→line, `group_by`/`segment_analysis`/`top_n`/`bottom_n`/
`compare_periods`→bar); operations without a natural series shape
(`calculate_sum`, `calculate_average`, `correlation`, `distribution`) correctly
return no chart rather than a fabricated one. The LLM never sees or influences
chart data.

## Orchestration (`app/orchestrator.py`)

`run_full_pipeline` is a single, linear function chaining all eight stages —
deliberately *not* a graph framework. A reviewer can read it top to bottom and
see exactly what each stage receives and produces; there's no framework
abstraction between "what the code does" and "what's visible in the source."
The optional `on_stage` callback is how the FastAPI layer persists each stage's
output as it completes (`backend/app/main.py`), which is what powers the
frontend's progress view and the report page's ability to re-render a
completed run from storage without re-calling the LLM.
