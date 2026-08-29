# Improvement Changelog

Two different kinds of "improvement" happened in this project:

1. **Comparative evaluation** (baseline LLM call vs. the verified pipeline) —
   the changelog the brief's template is really asking for. Now filled in
   with real results from a live run against the Gemini API (both systems on
   `gemini-3.5-flash-lite`, identical model, per `docs/architecture.md`).
2. **Engineering-correctness iterations** — real bugs, caught by real test
   failures or a real live run, during the build itself. Recorded in the same
   "what we tried / evidence / result / decision" format, because they're
   exactly what the brief means by "include experiments that were removed if
   they taught us something."

---

## Part 1: Comparative evaluation (baseline vs. agent)

**Run:** all 10 datasets in `datasets/`, both systems, `gemini-3.5-flash-lite`
for baseline generation, every pipeline stage, and the evaluation judge.
Raw output in `evaluation/results/{baseline_results,agent_results,comparison}.json`.
Rubric and scoring method in `docs/evaluation.md`.

### Baseline

**What we tried:** one unstructured LLM call per case, per the brief's exact
system prompt, given the same dataset context text as the agent.
**Evidence:** mean score across 10 cases: **54.5 / 100**
(numerical_correctness 13.5/30, key_findings 11.25/25, evidence_grounding
12.7/20, unsupported_claims 9.75/15, recommendation_grounding 3.65/5,
business_usefulness 3.65/5). Mean runtime 3.4s/case, 7,421 input + 8,504
output tokens total across all 10 cases (one call each, so this is exact —
$ cost unknown, see `docs/limitations.md`).
**Result:** the LLM judge's per-case rationale shows a specific, repeated
failure signature: on 4 of 10 cases (`03_product_performance`,
`04_customer_churn`, `07_customer_segmentation`, `10_operational_performance`)
the baseline explicitly used placeholder or "typical pattern" values instead
of computing real numbers from the data — e.g. "typically averaging around
3.5% to 4.5%" (`10_operational_performance`), when the real, computable
figure was 0.0451 for the worst shift. On `01_sales_decline` it asserted a
specific factual claim the data contradicts ("all regions saw some
contraction" — three of four were flat or up). On `02_regional_performance`
it missed the dataset's data-collection-gap trap entirely, treating a missing-
records artifact as a real performance signal.
**Decision:** this is the baseline working exactly as specified — no tools,
no verification, one call. The failure pattern (specifically: confident
placeholder numbers when the real number isn't computable from what the
model was shown) is the empirical basis for `docs/hot-take.md`.

### Iteration 1 — the full agentic pipeline

**Change:** all 8 stages, same model, same datasets, same questions.
**Why:** to measure whether separating calculation (deterministic tools) from
judgment (Verification's independent recompute + causal-language floor)
actually produces better answers, or just more expensive ones.
**Evidence:** mean score across the same 10 cases: **80.0 / 100** — an
improvement on **every one of the 6 rubric sub-metrics**, not just the total
(numerical_correctness +7.5, key_findings +7.5, evidence_grounding +5.5,
unsupported_claims +3.82, recommendation_grounding +0.73, business_usefulness
+0.45). The agent won on all 10 individual cases, from +5.0
(`01_sales_decline`) to +76.0 (`10_operational_performance`). Mean runtime
65.9s/case (~19x the baseline) — the real cost of 8+ sequential calls per run
plus retry-backoff against the free tier's 15-requests/minute cap (see
Iteration 7 below).
**Result:** the failure signature is qualitatively different from the
baseline's, not just smaller. In every one of the agent's 10 reports, every
stated number traces to a real `CalculationResult` — the judge's rationale
never once describes a placeholder or hypothetical value for the agent,
across all 10 cases. Where the agent lost points, it was for *incomplete*
trap coverage, not fabrication: missing the regional-concentration trap in
`01_sales_decline` (the Planner chose trend/correlation over a region
breakdown), missing the East-region data-gap trap in
`02_regional_performance`, missing the return-rate caveat in
`03_product_performance`, and a partial miss on the per-customer-value nuance
in `07_customer_segmentation`. The agent correctly navigated the traps in the
other 6 cases, including explicitly framing support-ticket correlation as
non-causal in `04_customer_churn` and declining to output a specific
overconfident Q4 number in `09_revenue_forecast_context`.
**Decision:** kept the full 8-stage architecture as the reported result.
The pattern — baseline fails by inventing numbers, agent fails by
incompletely exploring the analysis space — is real, reproducible in the
per-case rationale, and is the actual finding `docs/hot-take.md` is built on,
not the brief's example hypothesis assumed in advance.

### Final

**Combined result:** agent 80.0/100 vs. baseline 54.5/100 across all 10
cases, same model, same questions, same datasets, same scoring method
applied to both (see `docs/evaluation.md`'s fairness section). Improvement
holds on every sub-metric, not concentrated in one.
**Evidence:** `evaluation/results/comparison.json`, cross-checked case-by-case
against each result file's stored `rationale` and `output_text` above —
not just the aggregate score.
**Main contribution:** the architecture's core bet — separating deterministic
calculation from LLM judgment, with an independent verification stage that
never lets the model self-certify a causal claim — measurably reduces the
single most common baseline failure (confident numeric fabrication) without
introducing a new failure mode of comparable severity. The agent's residual
failures are omissions (a trap not explored), which are visible and
correctable by extending the Planner's prompt or the tool selection, not
silent fabrications a business reader would have to catch themselves.

## Part 2: Engineering-correctness iterations (real, from this build)

### Iteration 1 — Numeric-looking-text detection missed low-cardinality columns

**Change:** In `app/profiling/profiler.py`, the "column looks numeric but is
stored as text" warning check moved from running only when a column was
classified `"text"` to running for `"text"`, `"categorical"`, and
`"identifier"` alike.
**Why:** A 5-row column of `"$1,000"`-style strings has 5 unique values out of
5 rows, so the cardinality heuristic (`unique_count <= 50` → categorical)
classified it as `"categorical"`, and the numeric-text check was gated behind
`semantic_type == "text"` — so it never ran.
**Evidence:** `test_numeric_looking_text_column_not_silently_coerced` failed on
the first run of the Phase 2 test suite.
**Result:** Test passes after widening the gate; the other 12 profiler tests
were unaffected.
**Decision:** Kept the fix; added a code comment explaining why the check must
not be scoped to one semantic type.

### Iteration 2 — Percentage results rounded to the wrong precision

**Change:** `calculate_percentage_change`, `compare_periods`, and
`segment_analysis` now round percentage-shaped results to 2 decimals via a
dedicated `_round_pct` helper, instead of the 4-decimal `_round` used for
other metric values.
**Why:** The project brief's own worked example reports `-23.04%` — 2
decimals. The initial implementation used one rounding function everywhere
(4 decimals), producing `-23.0392`.
**Evidence:** `test_percentage_change_matches_spec_example` (which asserts the
brief's exact worked numbers, 1,020,000 → 785,000 → -23.04%) failed with
`-23.0392 == -23.04` → `False`.
**Result:** Test passes after splitting rounding precision by value type; two
dependent tests (`compare_periods`, `segment_analysis` percentage fields) were
updated to the same 2-decimal convention for consistency.
**Decision:** Kept two rounding conventions rather than one, since a business
report's percentage figures and its raw currency/count figures have different
natural precision — flattening them to one convention would have been the
simpler fix but the wrong one for the actual output format.

### Iteration 3 — Evidence lost the information Verification needed

**Change:** `build_evidence` now returns `EvidenceItem(evidence, calculation)`
pairs instead of bare `Evidence` objects.
**Why:** Wiring the full 8-stage orchestrator end-to-end (Phase 8) made clear
that `verify_claim`'s deterministic recompute needs the *original*
`CalculationResult` — including parameters like `agg`, `n`, or `freq` that the
report-facing `Evidence` model deliberately does not carry (it's meant to be a
compact, human-facing citation, not a full replay record). There was no way to
get from an `Evidence` back to the calculation that produced it.
**Evidence:** Discovered while writing `run_full_pipeline` — there was no
existing test failure yet, because no test exercised the full chain until this
point in development.
**Result:** All 5 existing `evidence_builder` tests updated to the new return
shape; `verify_claim` now receives the calculation directly, tests pass.
**Decision:** Kept the pairing rather than re-deriving parameters from
`Evidence`'s reduced field set (which would have required guessing/duplicating
information already available), or adding those fields back onto `Evidence`
(which would have polluted the report-facing model with internal-replay
details it doesn't need).

### Iteration 4 — Evaluation driver swallowed missing-dataset errors incorrectly

**Change:** In `evaluation/run_evaluation.py::_run_one`, moved
`df = load_dataset(dataset_path)` from before the `try` block to inside it.
**Why:** As originally written, a missing/misnamed dataset file raised an
uncaught `FileNotFoundError` instead of being recorded as a per-case error —
defeating the entire point of the try/except, which exists so one bad case
doesn't abort the whole evaluation sweep.
**Evidence:** `test_run_one_records_error_instead_of_raising` failed with an
unhandled `FileNotFoundError` traceback instead of the expected
`result["error"] is not None`.
**Result:** Test passes after moving the load inside the try block; no other
tests affected.
**Decision:** Kept the fix as a one-line move — no broader refactor needed
once the actual scope of the try block matched its intent.

### Iteration 5 — Missing CORS middleware (found only by a live browser run)

**Change:** Added `CORSMiddleware` to `backend/app/main.py`, configured via a
new `CORS_ORIGINS` env var (default `http://localhost:3000`).
**Why:** None of the 100+ backend tests up to this point could have caught
this — `TestClient` and `curl` don't enforce CORS, only real browsers do.
**Evidence:** Running the real `uvicorn` backend and real `next dev` frontend
together and driving them with a live Playwright browser produced a hard
browser-console failure: `Access to fetch at 'http://localhost:8000/api/runs'
... has been blocked by CORS policy`. The dashboard and analyze pages appeared
broken (upload silently failed, dashboard showed a connection error) despite
every automated test passing.
**Result:** After adding the middleware and restarting the backend, the same
live browser flow worked: the dashboard listed real runs, the analyze page
showed the real computed profile (`216 rows × 5 columns`) for an uploaded
dataset.
**Decision:** Added a regression test
(`test_cors_allows_the_frontend_dev_origin`) so this specific failure mode is
now covered by the automated suite too — but the lesson generalizes: **a
green test suite does not mean the browser-facing behavior works**, and this
project's `docs/hot-take.md` returns to that point directly.

### Iteration 6 — Malformed dataset uploads crashed instead of failing cleanly

**Change:** `POST /api/datasets`'s exception handling broadened from catching
only `ValueError` (unsupported file extension) to also catching
`pandas.errors.EmptyDataError`, `pandas.errors.ParserError`, and
`UnicodeDecodeError`, all mapped to a clean `400` response.
**Why:** Writing explicit malformed-dataset tests (empty file, ragged CSV,
corrupt binary content) for the profiler surfaced that the API layer had never
been tested against the same inputs — and indeed, all three produced
unhandled `500`s with FastAPI's default error page instead of the client-
facing `400` the upload endpoint already returned for a `.json` file.
**Evidence:** `test_upload_rejects_empty_csv_with_clean_400`,
`test_upload_rejects_ragged_csv_with_clean_400`, and
`test_upload_rejects_corrupt_binary_with_clean_400` all failed against the
original endpoint (500 instead of 400).
**Result:** All three pass after broadening the exception tuple; the
unsupported-extension test continues to pass unchanged.
**Decision:** Kept the broadened catch narrow (specific exception types, not a
bare `except Exception`) so a genuine server-side bug elsewhere in the request
still surfaces as a real 500 rather than being silently reclassified as a
client error.

### Iteration 7 — Ported the LLM backend from Anthropic to Gemini

**Change:** `app/llm/client.py` rewritten to call Gemini's REST API directly
via `httpx`, replacing the Anthropic SDK. `LLMClient.create_message()`'s
signature and the `LLMResponse`/`ToolCallRequest`/`LLMUsage` dataclasses were
kept unchanged on purpose.
**Why:** the only credential available was a Gemini API key, not an
Anthropic one — a direct cost decision by the project owner, not a technical
one.
**Evidence:** every Gemini wire-format detail (message roles, that function-
call parts must carry their `thoughtSignature` back verbatim on replay,
function responses keyed by name on a `role: "user"` turn) was verified with
live `curl` calls against the real API before being encoded — see the
commit for the exact request/response pairs. A naive first attempt (echoing
function-call parts without their signature) failed with a real 400:
`"Function call is missing a thought_signature..."`.
**Result:** because the fake/real seam in `LLMClient` was already isolated at
the "system + messages/tools/tool_choice in, content/usage/stop_reason out"
level, all 7 agent modules needed zero changes, and all ~130 existing tests
needed only a mechanical model-string update plus one legitimate rewrite of
a test that had asserted Anthropic's specific pricing numbers. 16 new tests
cover the translation layer itself, which the existing fakes never exercise.
**Decision:** kept `MODEL_PRICING_PER_MTOK` empty rather than filled with
guessed Gemini prices — `ai.google.dev` and `cloud.google.com`'s pricing
pages are blocked by this environment's network egress policy (confirmed via
direct `curl`, a 403 on the CONNECT). Cost is honestly reported as unknown
(0.0) rather than fabricated; token counts are real and unaffected.

### Iteration 8 — Free-tier rate limits required real retry logic, and a model change

**Change:** switched the default model from `gemini-3.6-flash` to
`gemini-3.5-flash-lite`, and added retry-with-backoff on HTTP 429 to
`_GeminiMessagesAPI.create()`, honoring the server's own `retryDelay`.
**Why:** the first live evaluation attempt on `gemini-3.6-flash` failed after
~2.5 minutes with a 429 whose error body named the quota explicitly:
`GenerateRequestsPerDayPerProjectPerModel-FreeTier, limit: 20`. A **daily**
cap of 20 requests cannot support an 8+-call-per-run pipeline across 10
evaluation cases — no amount of retrying within the same day would help.
**Evidence:** live `curl` calls confirmed `gemini-3.5-flash-lite` accepts the
same API shape (including function calling) and, when it was in turn hit
with a 429, the quota name was different —
`GenerateRequestsPerMinutePerProjectPerModel-FreeTier, limit: 15` — a
rolling per-minute window, which retrying *does* fix.
**Result:** the full 10-case, 2-system evaluation sweep completed
successfully end to end (`evaluation/results/*.json`) after both changes;
before them, both the baseline-only smoke test and the first full-sweep
attempt failed partway through with an uncaught 429.
**Decision:** kept the retry bounded (`_MAX_RATE_LIMIT_RETRIES = 4`) rather
than unbounded, specifically so a genuine daily-quota exhaustion (like the
first `gemini-3.6-flash` failure) still surfaces as an error after a bounded
number of attempts instead of retrying forever against a limit that will not
reset for hours.
