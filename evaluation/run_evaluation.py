"""Runs both systems (baseline and full InsightForge agent) over every
case in datasets/*/case.json, scores each output with scorer.score_output,
and writes evaluation/results/{baseline_results.json, agent_results.json,
comparison.json}.

Requires GEMINI_API_KEY — every run in here is a real LLM call. Nothing
in this file fabricates a result: if a case fails (an exception, a
malformed response), it is recorded with its error rather than skipped or
guessed. See docs/reproduction.md for exact commands and expected runtime.

Usage:
    python evaluation/run_evaluation.py [--cases 01_sales_decline,...]
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "baseline"))

from app.llm.client import LLMClient  # noqa: E402
from app.orchestrator import run_full_pipeline  # noqa: E402
from app.profiling.profiler import load_dataset  # noqa: E402
from app.reports.render_text import render_report_markdown  # noqa: E402
from baseline_agent import run_baseline  # noqa: E402
from scorer import score_output  # noqa: E402

DATASETS_DIR = ROOT / "datasets"
RESULTS_DIR = ROOT / "evaluation" / "results"


def _load_cases(names: list[str] | None) -> list[dict[str, Any]]:
    cases = []
    for case_dir in sorted(DATASETS_DIR.iterdir()):
        if not case_dir.is_dir():
            continue
        if names and case_dir.name not in names:
            continue
        case_file = case_dir / "case.json"
        if not case_file.exists():
            continue
        case = json.loads(case_file.read_text())
        case["_dataset_dir"] = case_dir.name
        cases.append(case)
    return cases


def _run_one(case: dict[str, Any], system: str, llm_client: LLMClient) -> dict[str, Any]:
    dataset_path = DATASETS_DIR / case["_dataset_dir"] / "data.csv"
    question = case["question"]

    start = time.monotonic()
    try:
        df = load_dataset(dataset_path)
        if system == "baseline":
            response = run_baseline(df, question, dataset_name=dataset_path.name, llm_client=llm_client)
            output_text = response.text
            usage = response.usage
        else:
            pipeline_run = run_full_pipeline(df, question, llm_client, dataset_name=dataset_path.name)
            output_text = render_report_markdown(pipeline_run.report) if pipeline_run.report else ""
            usage = None  # multi-call; per-call cost isn't a single number here
        runtime_s = time.monotonic() - start

        score = score_output(question, output_text, case, llm_client)
        return {
            "dataset": case["_dataset_dir"],
            "question": question,
            "system": system,
            "output_text": output_text,
            "score": score,
            "runtime_seconds": round(runtime_s, 2),
            "usage": {"input_tokens": usage.input_tokens, "output_tokens": usage.output_tokens, "cost_usd": usage.cost_usd}
            if usage
            else None,
            "error": None,
        }
    except Exception as exc:  # noqa: BLE001 - recorded, never silently skipped
        runtime_s = time.monotonic() - start
        return {
            "dataset": case["_dataset_dir"],
            "question": question,
            "system": system,
            "output_text": None,
            "score": None,
            "runtime_seconds": round(runtime_s, 2),
            "usage": None,
            "error": f"{type(exc).__name__}: {exc}",
        }


def _summarize(results: list[dict[str, Any]]) -> dict[str, Any]:
    scored = [r for r in results if r["score"] is not None]
    if not scored:
        return {"mean_total_score": None, "cases_scored": 0, "cases_failed": len(results)}
    metrics = ["numerical_correctness", "key_findings", "evidence_grounding", "unsupported_claims", "recommendation_grounding", "business_usefulness", "total_score"]
    means = {m: round(sum(r["score"][m] for r in scored) / len(scored), 2) for m in metrics}
    means["cases_scored"] = len(scored)
    means["cases_failed"] = len(results) - len(scored)
    return means


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", type=str, default=None, help="Comma-separated dataset dir names to run")
    args = parser.parse_args()
    names = args.cases.split(",") if args.cases else None

    cases = _load_cases(names)
    if not cases:
        print("No cases found.", file=sys.stderr)
        raise SystemExit(1)

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    llm_client = LLMClient()

    baseline_results = [_run_one(case, "baseline", llm_client) for case in cases]
    agent_results = [_run_one(case, "agent", llm_client) for case in cases]

    (RESULTS_DIR / "baseline_results.json").write_text(json.dumps(baseline_results, indent=2, default=str))
    (RESULTS_DIR / "agent_results.json").write_text(json.dumps(agent_results, indent=2, default=str))

    baseline_summary = _summarize(baseline_results)
    agent_summary = _summarize(agent_results)
    comparison = {
        "baseline": baseline_summary,
        "agent": agent_summary,
        "improvement": {
            m: round(agent_summary[m] - baseline_summary[m], 2)
            for m in baseline_summary
            if isinstance(baseline_summary.get(m), (int, float)) and isinstance(agent_summary.get(m), (int, float))
        },
    }
    (RESULTS_DIR / "comparison.json").write_text(json.dumps(comparison, indent=2))

    print(json.dumps(comparison, indent=2))


if __name__ == "__main__":
    main()
