# Baseline agent

The fair baseline InsightForge's full agentic workflow is measured against:
one general-purpose LLM call, no tools, no verification, no multi-stage
structure — matching the project brief exactly.

## What it gets

- The same dataset and the same question as the full agent.
- Dataset context built by `app.llm.dataset_context.build_dataset_context_text`,
  the identical function used to construct context for the full agent's
  planner from the Data Profiler's output. This is enforced by
  `backend/tests/unit/test_baseline_agent.py::test_baseline_context_matches_shared_profiling_code`
  — the baseline's prompt is checked byte-for-byte against what the shared
  profiler produces, so neither system can silently drift into an
  information advantage.
- The system prompt specified in the brief, verbatim:

  > You are a business analyst. Analyze the provided dataset and answer the
  > user's question. Provide calculations, insights and recommendations.

## What it explicitly does NOT get

- No tool access (`tools` is never passed to the API call).
- No planning stage, no evidence graph, no independent verification.
- No retries or multi-turn refinement — one call, whatever comes back is
  the final answer.

## Running it

Requires `GEMINI_API_KEY` (see `.env.example` at the repo root).

```bash
cd backend && pip install -r requirements.txt   # once
export GEMINI_API_KEY=...
python baseline/run_baseline.py datasets/01_sales_decline/data.csv \
  "Why did revenue decline in Q2 2024, and what should we investigate next?"
```

`evaluation/run_evaluation.py` calls `baseline.baseline_agent.run_baseline`
directly across all 10 evaluation cases and scores the output the same way
the full agent's report is scored. Live result across all 10 cases: mean
54.5/100 — see `docs/evaluation.md` and `docs/failure-analysis.md` for the
full breakdown of what actually went wrong.
