"""CLI entry point: run the baseline agent against one dataset + question.

Usage:
    python baseline/run_baseline.py <dataset.csv> "<question>"

Requires GEMINI_API_KEY (see .env.example). Prints the raw response text
and a usage/cost summary to stdout.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.profiling.profiler import load_dataset  # noqa: E402
from baseline_agent import run_baseline  # noqa: E402


def main() -> None:
    if len(sys.argv) != 3:
        print(f"Usage: python {sys.argv[0]} <dataset.csv|.xlsx> \"<question>\"", file=sys.stderr)
        raise SystemExit(1)

    dataset_path = Path(sys.argv[1])
    question = sys.argv[2]

    df = load_dataset(dataset_path)
    response = run_baseline(df, question, dataset_name=dataset_path.name)

    print("=" * 80)
    print(response.text)
    print("=" * 80)
    print(
        f"stop_reason={response.stop_reason} "
        f"input_tokens={response.usage.input_tokens} "
        f"output_tokens={response.usage.output_tokens} "
        f"cost_usd={response.usage.cost_usd} "
        f"latency_s={response.latency_seconds:.2f}"
    )


if __name__ == "__main__":
    main()
