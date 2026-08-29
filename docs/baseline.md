# Baseline

`baseline/` implements the fair baseline InsightForge's full agentic workflow
is measured against, exactly as the project brief specifies: one
general-purpose LLM call, no tools, no planning stage, no evidence graph, no
independent verification.

## System prompt (verbatim, per the brief)

> You are a business analyst. Analyze the provided dataset and answer the
> user's question. Provide calculations, insights and recommendations.

`baseline/baseline_agent.py::SYSTEM_PROMPT` is this string, unmodified, and a
test (`test_baseline_uses_the_brief_system_prompt`) asserts it stays that way.

## What it gets

- The same dataset file and the same question string as the full agent, on
  every evaluation case.
- Dataset context built by `app.llm.dataset_context.build_dataset_context_text`
  — the **identical function** used to construct the full agent's planner
  input from the Data Profiler's output (row/column counts, per-column
  semantic type and missing/unique counts, data-quality warnings, and a
  20-row sample). This is the fairness anchor: if this function ever changed
  to give the agent richer context, the baseline would automatically get the
  same richer context, because it's the same code path. A test
  (`test_baseline_context_matches_shared_profiling_code`) checks the baseline's
  prompt contains this text byte-for-byte, not just "similar" text.

## What it explicitly does NOT get

- No `tools` parameter on the API call at all (`test_baseline_sends_dataset_context_and_question`
  asserts `"tools" not in call`).
- No multi-stage structure: one request, whatever comes back is the final
  answer. No planning, no evidence binding, no verification, no retries.
- No model advantage: it runs on the exact same `LLM_MODEL` as every
  InsightForge stage (`gemini-3.5-flash-lite`) — see `docs/architecture.md`.
  A quality gap between the two systems, measured in `docs/evaluation.md`,
  has to come from workflow design, not from a bigger model.

## Running it

Requires `GEMINI_API_KEY` (see `.env.example`).

```bash
cd backend && pip install -r requirements.txt   # once
export GEMINI_API_KEY=...
python ../baseline/run_baseline.py ../datasets/01_sales_decline/data.csv \
  "Why did revenue decline in Q2 2024, and what should we investigate next?"
```

Its logic (prompt construction, response parsing, cost/usage tracking) is
fully covered by unit tests using a fake client (`backend/tests/unit/test_baseline_agent.py`).
It has also been run live, across all 10 evaluation datasets — see below.

## How it's scored, and what actually happened

`evaluation/run_evaluation.py` calls `baseline_agent.run_baseline` for every
case in `datasets/*/case.json` and scores the raw response text with
`evaluation/scorer.py` — the same scorer, run the same way, as the full
agent's rendered report. See `docs/evaluation.md`.

Live result across all 10 cases: mean score **54.5/100**. The dominant
failure mode was not a model quirk — it was structural: with no tool access
and no way to say "I can't compute this from what I've been shown," the
baseline's most common failure (4 of 10 cases) was stating a specific,
plausible-sounding placeholder number as if it were computed from the data.
Full breakdown in `docs/failure-analysis.md` and `docs/hot-take.md`.
