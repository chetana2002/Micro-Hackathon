# Limitations

Honest, current, and specific — this document is maintained as things change,
not written once and left stale.

## The LLM provider changed mid-build (Anthropic → Gemini)

This project was designed and initially built against Anthropic's Claude
API. The only credential actually available turned out to be a Google
Gemini key — a cost decision by the project owner (Anthropic's API is paid;
Gemini has a free tier), not a technical one. `app/llm/client.py` was ported
to call Gemini's REST API directly; see `docs/improvement-changelog.md`
Iterations 7-8 for exactly what changed and how it was verified. Consequence
worth naming: the architecture, prompts, and evaluation results in this
repository were validated against Gemini (`gemini-3.5-flash-lite`), not
Claude. The design decisions (tool-use forcing, the verification
causal-downgrade floor, evidence binding) are provider-agnostic by
construction, but the *quality* numbers in `docs/evaluation.md` are specific
to this model and would need re-running to claim for a different one.

## Live evaluation used the cheapest available model tier, not the most capable

`gemini-3.5-flash-lite` was chosen specifically because a more capable tier
(`gemini-3.6-flash`) hit a **20-requests-per-day** free-tier quota that
cannot support an 8-call-per-run pipeline across 10 cases at all —
retrying doesn't help a daily cap. This means the evaluation results in
`docs/evaluation.md` measure the architecture's effect on a low-capability
model, which is arguably the harder and more interesting test (a stronger
model might paper over some of the architectural gap by being less prone to
fabrication even without tools), but it is a specific, named choice made for
quota reasons, not a claim that this is the best model for the job. Re-running
against a more capable tier is a natural next step, not yet done.

## The live evaluation is one run, not a repeated statistical result

`evaluation/results/*.json` reflects a single pass over all 10 cases for each
system. LLM outputs are stochastic — an earlier single-case smoke test of
`01_sales_decline` actually scored the agent *below* the baseline, before a
subsequent full run scored it above (see `docs/improvement-changelog.md`
Part 1 and `docs/hot-take.md`). The qualitative pattern (baseline fails by
fabricating numbers, agent fails by incomplete analysis, never by
fabrication) held consistently across all 10 cases in the run that's
recorded, but the exact point gap per case should not be read as a precise,
reproducible-to-the-decimal number without multiple trials.

## Pipeline execution is synchronous, not backgrounded

`POST /api/runs` runs all 8 stages inside the request handler and blocks until
they finish or fail. This was a deliberate simplification for hackathon-scale
datasets (the 10 evaluation datasets are all well under 1,000 rows) and it
avoids the real complexity of background-task/database thread-safety for a
demo. The direct consequence: the frontend cannot show *live* per-stage
progress during a run — `docs/reproduction.md` and the `analyze` page are
honest about this, showing an indeterminate "Analyzing…" state and then
revealing the already-completed stage list once the response returns, rather
than a real-time stream. A production version would move execution to a
background job queue (or use Gemini's streaming + SSE to the client) so the
UI could show genuine incremental progress.

## No OpenAPI-generated frontend types

`frontend/lib/types.ts` is hand-written to mirror the Pydantic models in
`backend/app/models/`. There's no generation step keeping them in sync — if a
backend model's field changes, the frontend type has to be updated by hand.
For a project this size that's a manageable discipline, but it's a real gap a
larger project would close with an OpenAPI schema export + a codegen step.

## shadcn/ui's CLI could not run in this environment

`ui.shadcn.com`, the registry host the `shadcn` CLI fetches component
templates from, is blocked by this sandbox's outbound network policy
(confirmed via the proxy status endpoint — a 403 on the CONNECT, not a
timeout or a transient failure). `frontend/components/ui/*.tsx` are hand-
written against the same underlying libraries (Radix UI primitives,
`class-variance-authority`, `tailwind-merge`) the CLI itself would have used,
so the result should be structurally equivalent — but they weren't generated
by, or diffed against, the actual shadcn registry output.

## No automated frontend test suite yet

The frontend has no test runner configured (no Vitest/Jest, no React Testing
Library, no Playwright test suite checked into the repo). What verification
exists: `npm run build` and `next lint` both pass clean, and the app was
manually driven with a live Playwright browser session against a real running
backend during development (see `docs/improvement-changelog.md`, Iteration
5) — which is how the CORS bug was actually found — but that session's script
lived in `/tmp`, not in the repository, and isn't re-run automatically. A
follow-up would add component tests and a checked-in Playwright suite.

## `correlation()` on a column against itself

`app.tools.registry.correlation(df, "revenue", "revenue")` raises a pandas
`ValueError` ("truth value of a DataFrame is ambiguous") rather than failing
gracefully, because selecting the same column name twice produces a DataFrame
with duplicate column labels instead of two distinct Series. This surfaced
while writing verifier tests (worked around there by using a genuinely
duplicated column with a different name) but was never hardened in the
registry itself, since a planner asking to correlate a column with itself is
a degenerate case the tool-selection prompt doesn't invite, not one expected
to occur in practice. Left as a known minor gap rather than a silent
behavior change.

## Verification's recompute check has a specific, stated blind spot

`verify_claim`'s deterministic recompute confirms that the recorded
operation/columns/parameters/filters reproduce the recorded number against
the actual data. It does **not** independently re-derive which
operation/columns/filters *should* have been used from the claim's natural-
language text. A claim that used the wrong column but got internally
consistent arithmetic (right math, wrong input) would pass this check and
fall through to the LLM-judged half, which may or may not catch it depending
on how legible the error is from context alone. This is stated in
`app/agents/verifier.py`'s own module docstring, not just here.

## Scale and deployment assumptions

Single-user, no authentication, no multi-tenancy. SQLite, not a networked
database — fine for a demo and for `docs/reproduction.md`'s "no external
infra" goal, wrong for concurrent multi-user production use. Datasets are
assumed to fit comfortably in memory (the largest evaluation dataset is 819
rows); nothing here has been tested against a dataset with hundreds of
thousands of rows.

## CORS defaults to localhost only

`CORS_ORIGINS` defaults to `http://localhost:3000,http://127.0.0.1:3000`.
Deploying the frontend anywhere else requires setting this env var explicitly
— it will not work out of the box against a different origin, by design (an
open CORS policy would be a worse default for a project that also accepts
file uploads).
