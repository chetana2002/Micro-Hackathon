"""Reproducible scoring for the ANALYTICAL CORRECTNESS SCORE.

Both systems (baseline and full agent) are reduced to the same
representation — plain text — before scoring, so the identical method
applies to both: the full agent's structured Report is rendered to
Markdown by app.reports.render_text.render_report_markdown, and the
baseline's output is already plain text. The scorer must never see the
agent's Report as structured JSON while only reading the baseline's raw
text — that would make the two systems' scores incomparable.

Rubric weights below were reviewed against real score distributions from a
live 10-case evaluation run (see docs/evaluation.md's rubric section) and
kept as originally proposed: every metric showed a real, non-degenerate
gap between baseline and agent, and the four reliability-diagnostic metrics
(numerical correctness, key findings, evidence grounding, unsupported
claims) already carry 90 of the 100 points and show the largest relative
gaps -- the review supported the original allocation rather than
contradicting it.

Numerical correctness and key finding coverage are fully deterministic:
regex-based number/keyword matching against each case's case.json ground
truth. Evidence grounding, unsupported-claim rate, recommendation
grounding, and business usefulness require judgment about a free-text
passage that regex cannot reliably make, so they are LLM-judged via a
forced submit_judge_scores tool call — a separate, clearly-labeled step
that only scores an already-written report, never generates content.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.llm.client import LLMClient  # noqa: E402

RUBRIC_WEIGHTS: dict[str, float] = {
    "numerical_correctness": 30,
    "key_findings": 25,
    "evidence_grounding": 20,
    "unsupported_claims": 15,
    "recommendation_grounding": 5,
    "business_usefulness": 5,
}
assert sum(RUBRIC_WEIGHTS.values()) == 100, "RUBRIC_WEIGHTS must sum to 100"

_NUMBER_RE = re.compile(r"-?\$?\d[\d,]*\.?\d*%?")


def extract_numbers(text: str) -> list[float]:
    """Pulls every number-shaped token out of free text, stripping $, commas,
    and %. Deliberately permissive (regex, not an NLP number parser) so it
    works identically on both systems' output without special-casing."""
    numbers = []
    for match in _NUMBER_RE.findall(text):
        cleaned = match.replace("$", "").replace(",", "").replace("%", "")
        if cleaned in ("", "-", "."):
            continue
        try:
            numbers.append(float(cleaned))
        except ValueError:
            continue
    return numbers


def _finding_covered(finding: dict[str, Any], output_text: str, extracted_numbers: list[float]) -> bool:
    expected = finding["expected_value"]
    if isinstance(expected, (int, float)):
        tol = finding.get("tolerance_abs", 0.01)
        return any(abs(n - expected) <= tol for n in extracted_numbers)
    return str(expected).lower() in output_text.lower()


def numeric_and_finding_scores(output_text: str, expected_findings: list[dict[str, Any]]) -> dict[str, Any]:
    numbers = extract_numbers(output_text)
    numeric_findings = [f for f in expected_findings if isinstance(f["expected_value"], (int, float))]

    numeric_hits = sum(1 for f in numeric_findings if _finding_covered(f, output_text, numbers))
    all_hits = sum(1 for f in expected_findings if _finding_covered(f, output_text, numbers))

    numeric_ratio = numeric_hits / len(numeric_findings) if numeric_findings else 1.0
    coverage_ratio = all_hits / len(expected_findings) if expected_findings else 1.0

    return {
        "numerical_correctness": round(numeric_ratio * RUBRIC_WEIGHTS["numerical_correctness"], 2),
        "key_findings": round(coverage_ratio * RUBRIC_WEIGHTS["key_findings"], 2),
        "numeric_ratio": numeric_ratio,
        "coverage_ratio": coverage_ratio,
    }


JUDGE_SYSTEM_PROMPT = (
    "You are scoring a business analytics report against a rubric. You will "
    "be given the business question, the report's known dataset traps (facts "
    "about what the data can and cannot support), and the report text. Score "
    "each from 0.0 to 1.0: evidence_grounding (are numeric/factual claims "
    "shown with their basis, e.g. a calculation or comparison, rather than "
    "asserted without support?), unsupported_claims_rate (fraction of claims "
    "that overreach the data — e.g. asserting causation the data cannot "
    "establish, or a conclusion not backed by any shown calculation — higher "
    "means WORSE), recommendation_grounding (are recommendations tied to a "
    "specific finding rather than generic advice?), and business_usefulness "
    "(would a business reader get a specific, actionable takeaway?). Submit "
    "via submit_judge_scores."
)

JUDGE_TOOL = {
    "name": "submit_judge_scores",
    "description": "Submit rubric scores for a business analytics report.",
    "input_schema": {
        "type": "object",
        "properties": {
            "evidence_grounding": {"type": "number", "minimum": 0, "maximum": 1},
            "unsupported_claims_rate": {"type": "number", "minimum": 0, "maximum": 1},
            "recommendation_grounding": {"type": "number", "minimum": 0, "maximum": 1},
            "business_usefulness": {"type": "number", "minimum": 0, "maximum": 1},
            "rationale": {"type": "string"},
        },
        "required": [
            "evidence_grounding", "unsupported_claims_rate",
            "recommendation_grounding", "business_usefulness", "rationale",
        ],
    },
}


def llm_judge_scores(
    question: str, output_text: str, known_traps: list[str], llm_client: LLMClient
) -> dict[str, Any]:
    traps_text = "\n".join(f"- {t}" for t in known_traps) or "(none)"
    user_message = (
        f"Business question: {question}\n\nKnown dataset traps:\n{traps_text}\n\nReport text:\n{output_text}"
    )
    response = llm_client.create_message(
        system=JUDGE_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_message}],
        tools=[JUDGE_TOOL],
        tool_choice={"type": "tool", "name": "submit_judge_scores"},
        max_tokens=1024,
    )
    if not response.tool_calls:
        raise ValueError("Judge did not return scores via submit_judge_scores")
    verdict = response.tool_calls[0].input
    return {
        "evidence_grounding": round(verdict["evidence_grounding"] * RUBRIC_WEIGHTS["evidence_grounding"], 2),
        "unsupported_claims": round(
            (1 - verdict["unsupported_claims_rate"]) * RUBRIC_WEIGHTS["unsupported_claims"], 2
        ),
        "recommendation_grounding": round(
            verdict["recommendation_grounding"] * RUBRIC_WEIGHTS["recommendation_grounding"], 2
        ),
        "business_usefulness": round(verdict["business_usefulness"] * RUBRIC_WEIGHTS["business_usefulness"], 2),
        "rationale": verdict["rationale"],
    }


def score_output(question: str, output_text: str, case: dict[str, Any], llm_client: LLMClient) -> dict[str, Any]:
    deterministic = numeric_and_finding_scores(output_text, case["expected_findings"])
    judged = llm_judge_scores(question, output_text, case.get("known_traps", []), llm_client)

    total = (
        deterministic["numerical_correctness"]
        + deterministic["key_findings"]
        + judged["evidence_grounding"]
        + judged["unsupported_claims"]
        + judged["recommendation_grounding"]
        + judged["business_usefulness"]
    )
    return {
        "total_score": round(total, 2),
        "numerical_correctness": deterministic["numerical_correctness"],
        "key_findings": deterministic["key_findings"],
        "evidence_grounding": judged["evidence_grounding"],
        "unsupported_claims": judged["unsupported_claims"],
        "recommendation_grounding": judged["recommendation_grounding"],
        "business_usefulness": judged["business_usefulness"],
        "rationale": judged["rationale"],
    }
