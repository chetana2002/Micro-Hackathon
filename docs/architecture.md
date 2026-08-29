# InsightForge — Architecture

Status: implemented and evaluated live. Profiler, deterministic tool
registry, all 8 pipeline stages, the FastAPI backend, and the Next.js
frontend are built and tested (151 backend tests, all passing without
needing an API key; see `docs/reproduction.md`). The full 10-case baseline-
vs-agent evaluation has also been run for real against the Gemini API
(agent 80.0/100 vs. baseline 54.5/100 — see `docs/evaluation.md` and
`docs/improvement-changelog.md`). Note the model: this project was built
against Anthropic Claude and later ported to Google Gemini mid-build when
the only available credential turned out to be a Gemini key (a cost
decision, not a technical one) — see `docs/improvement-changelog.md`
Iteration 7 for the port itself and `docs/limitations.md` for what that
changed.

## 1. Problem

Business/data/operations analysts need to answer questions like "why did revenue
decline in Q2?" from structured datasets. A general-purpose LLM asked to do this
directly produces plausible-sounding analysis that can contain arithmetic errors,
unsupported conclusions, incorrect aggregations, correlation-as-causation, and
outright hallucinated numbers. InsightForge's bet: an agentic workflow that
separates "what tool to run and how to interpret it" (LLM) from "the actual
calculation" (deterministic code), and adds an independent verification stage,
produces answers that are both correct and honestly qualified — and this claim is
tested against a fair single-agent baseline, not asserted.

## 2. Tech stack and key decisions

| Layer | Choice | Reasoning |
|---|---|---|
| Backend | Python + FastAPI | Pandas-native; Pydantic gives typed stage contracts; async for progress polling |
| LLM | Google Gemini API, model `gemini-3.5-flash-lite` (used everywhere: baseline, every agent stage, and the evaluation judge — ported mid-build from Anthropic Claude when a Gemini key turned out to be the only available credential; see `docs/improvement-changelog.md` Iteration 7-8) | One model across baseline and agent keeps the comparison about workflow design, not model capability. Single knob (`LLM_MODEL` env var) so this is never silently changed. The flash-lite tier was chosen for free-tier quota reasons (a more capable tier hit a 20-requests/*day* cap), not capability — see Iteration 8. |
| Orchestration | Hand-rolled sequential pipeline (no LangGraph/CrewAI) | Fully auditable — a reviewer can read `orchestrator.py` top to bottom and see exactly what "verification" checks, with no framework abstraction hiding it. Avoids adding agent-framework complexity the task doesn't need. |
| Tool execution | Fixed Python function registry, invoked via Gemini function calling | The model never writes or executes code; it only selects from a closed, schema-validated set of deterministic analysis functions. Satisfies "never execute arbitrary model-generated code." |
| Storage | SQLite (SQLModel) + filesystem | No external infra — `docs/reproduction.md` only needs `pip install` + `npm install`. SQLite holds Run/StageResult records (also powers progress polling and doubles as the trajectory log); filesystem holds uploads, chart specs, rendered reports. |
| Frontend | Next.js + TypeScript + Tailwind + shadcn/ui | As specified in the brief |
| Progress updates | Polling (`GET /runs/{id}` every ~1s) | Simpler and lower-risk than WebSocket/SSE for a single-user demo; documented tradeoff |

## 3. Pipeline

```
Upload -> DATA PROFILER -> ANALYSIS PLANNER -> DATA ANALYST (tool-use loop)
       -> EVIDENCE BUILDER -> VERIFICATION AGENT -> INSIGHT SYNTHESIZER
       -> RECOMMENDATION ENGINE -> REPORT GENERATOR -> UI
```

Each arrow carries a typed Pydantic object (see `backend/app/models/`), persisted to
SQLite as soon as it's produced. This persisted stage-by-stage state is what powers
the UI's progress view, the report's evidence links, and the `trajectories/` logs —
one mechanism serves all three, rather than separate instrumentation.

## 4. LLM vs. deterministic-code split (explicit, per stage)

| Stage | LLM does | Code does |
|---|---|---|
| Data Profiler | nothing | 100% — pandas dtype inference, null counts, dupes, warnings |
| Analysis Planner | selects analysis operations and order | validates the plan against the tool registry's schema |
| Data Analyst | chooses tool + params per plan step | executes the deterministic tool, returns `CalculationResult` |
| Evidence Builder | writes the human-readable claim text | binds the claim to the exact `CalculationResult` that produced it |
| Verification Agent | judges causal language, contradictions, missing context | recomputes every numeric claim independently via the same tool registry and diffs against tolerance |
| Insight Synthesizer | writes business narrative | restricted to claims with status VERIFIED or PARTIALLY_VERIFIED |
| Recommendation Engine | drafts recommendation text | filtered to insights with supporting evidence only |
| Report Generator | writes prose sections | renders charts from `CalculationResult` data, never LLM-supplied numbers |

## 5. Directory structure

```
insightforge/
├── README.md
├── docs/                    architecture, agent-design, baseline, evaluation,
│                             improvement-changelog, reproduction, failure-analysis,
│                             limitations, hot-take
├── backend/
│   ├── app/
│   │   ├── main.py                  FastAPI app
│   │   ├── api/                     routes: upload, analyze, runs/{id}, reports/{id}
│   │   ├── models/                  Pydantic contracts (DatasetProfile, AnalysisPlan,
│   │   │                            CalculationResult, Evidence, VerificationResult,
│   │   │                            Insight, Recommendation, Report)
│   │   ├── profiling/               deterministic profiler
│   │   ├── tools/                   deterministic analysis tool registry
│   │   ├── agents/                  planner, analyst, evidence_builder, verifier,
│   │   │                            synthesizer, recommender, report_generator
│   │   ├── orchestrator.py          wires the pipeline, persists stage state
│   │   ├── charts/                  CalculationResult -> chart-spec JSON
│   │   ├── storage/                 SQLModel tables + filesystem helpers
│   │   └── llm/                     Gemini client wrapper, prompts, cost tracking
│   └── tests/{unit,integration,e2e}/
├── baseline/                        single-call baseline agent (no tools, no verification)
├── frontend/                        Next.js app: /, /dashboard, /analyze, /reports/[id]
├── datasets/                        10 synthetic evaluation datasets
├── evaluation/                      cases, scorer, run_evaluation.py, results/
├── trajectories/                    per-run, per-agent structured traces
├── observability/                   JSONL event logger
└── scripts/
```

## 6. Storage design

- `Run` (SQLModel/SQLite): id, dataset_ref, question, status, created_at, current_stage,
  cost_estimate, duration.
- `StageResult` (SQLModel/SQLite): run_id, stage_name, payload_json (serialized
  Pydantic object), created_at.
- Filesystem, keyed by run_id: `backend/data/uploads/{run_id}/` (original file),
  `backend/data/charts/{run_id}/` (chart specs), `backend/data/reports/{run_id}/`
  (rendered report).

This gives full replay: a report can be re-rendered from stored stage JSON without
re-calling the LLM.

## 7. Evaluation architecture (summary; full detail in docs/evaluation.md once Phase 10 lands)

Provisional rubric (to be recalibrated in Phase 11 against real score
distributions — not treated as final):

| Metric | Points |
|---|---|
| Numerical correctness | 30 |
| Key finding coverage | 25 |
| Evidence grounding | 20 |
| Unsupported/overclaimed rate (penalty) | 15 |
| Recommendation grounding | 5 |
| Business usefulness | 5 |

Baseline and agent run on identical datasets and questions; the dataset-context
text handed to the baseline is generated by the same profiling code the agent's
Data Profiler stage uses, so neither system gets an information advantage.

## 8. Risks (see docs/limitations.md for the maintained, evidence-based version)

- LLM cost/latency: ~8 calls per agent run vs. 1 for baseline, across 10 eval cases.
- Eval tolerance calibration: too strict fails correct rounding; too loose hides real errors.
- Fairness leakage: any accidental extra context to one system invalidates the comparison.
- The Verification Agent's numeric checks are deterministic (recompute + diff), but
  its causal/contradiction judgment is still LLM-based and can itself be wrong —
  this is exactly what the eval framework and failure-analysis doc are meant to surface.

## 9. Assumptions

- Single-user, local/demo deployment — no auth, no multi-tenancy.
- `GEMINI_API_KEY` supplied by the operator via `.env`, never committed.
- Datasets are small-to-medium (fits in memory), synthetic, no PII.
- Reproduction requires only Python + Node + an API key — no external infra.
