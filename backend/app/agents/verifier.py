"""Verification Agent — the key differentiator.

Split explicitly into deterministic and LLM-judged checks so this agent's
own reliability is auditable rather than asserted:

1. Deterministic: re-execute the exact recorded operation, columns,
   parameters, and filters against the dataset via the same tool registry
   the analyst used, and diff the fresh result against the reported one.
   A mismatch is CONTRADICTED with corrected_value set, and short-circuits
   the LLM-judged checks below entirely — no LLM call is needed to catch
   an arithmetic/transcription error.
2. Deterministic pre-filter: a keyword scan for causal language in the
   claim ("because", "caused by", "drove", "why", ...). This never grants
   a pass by itself — it only ever pushes a claim toward stricter scrutiny.
3. LLM-judged: does the data actually support any causal language in the
   claim, and is there missing context or contradiction relative to other
   stated information? Combined with (2): if the claim contains causal
   language, this code refuses to accept a VERIFIED verdict from the LLM —
   it is downgraded to PARTIALLY_VERIFIED with an appended issue and a
   capped confidence. The LLM can make a claim's status worse; it cannot,
   by itself, clear a causal claim to fully verified.

Known limitation (see docs/limitations.md): step 1 confirms the recorded
operation/parameters reproduce the recorded number from the actual data —
it catches corruption, transcription errors, and non-determinism. It does
NOT independently re-derive which operation/columns/filters *should* have
been used from the claim's natural-language text; a wrong-but-internally-
consistent analysis choice made upstream (wrong column, wrong filter) is
not caught by recomputation alone.
"""
from __future__ import annotations

from typing import Any

import pandas as pd

from app.llm.client import LLMClient
from app.models.calculation import CalculationResult
from app.models.evidence import Evidence
from app.models.verification import VerificationResult
from app.tools.registry import TOOL_REGISTRY

_OPERATION_COLUMN_ARGS: dict[str, list[str]] = {
    "calculate_sum": ["column"],
    "calculate_average": ["column"],
    "group_by": ["group_column", "value_column"],
    "top_n": ["group_column", "value_column"],
    "bottom_n": ["group_column", "value_column"],
    "correlation": ["column_a", "column_b"],
    "distribution": ["column"],
    "trend": ["date_column", "value_column"],
    "segment_analysis": ["segment_column", "value_column"],
    "compare_periods": ["date_column", "value_column"],
}

_CAUSAL_MARKERS = (
    "because", "due to", "caused by", "causes", "causing", "leads to", "led to",
    "results in", "resulted in", "driving", "drove", "responsible for", "as a result of",
)

_NUMERIC_TOLERANCE = 0.01

SYSTEM_PROMPT = (
    "You are an independent verification reviewer for a business analytics "
    "report. You will be given a claim, the calculation that backs it "
    "(already recomputed and confirmed numerically correct), and any known "
    "dataset limitations. Judge only what the data can actually support: "
    "flag causal language that goes beyond a descriptive/associational "
    "finding, note missing context (e.g. small sample size, data gaps), and "
    "flag contradictions with other stated context. Do not re-check the "
    "arithmetic — that has already been verified independently. Submit your "
    "verdict via submit_verification."
)

VERIFY_TOOL = {
    "name": "submit_verification",
    "description": "Submit the verification verdict for one claim.",
    "input_schema": {
        "type": "object",
        "properties": {
            "status": {
                "type": "string",
                "enum": ["VERIFIED", "PARTIALLY_VERIFIED", "UNSUPPORTED", "CONTRADICTED"],
            },
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            "issues": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["status", "confidence", "issues"],
    },
}


def _contains_causal_language(text: str) -> bool:
    lowered = text.lower()
    return any(marker in lowered for marker in _CAUSAL_MARKERS)


def recompute(df: pd.DataFrame, calc: CalculationResult) -> Any:
    fn = TOOL_REGISTRY[calc.operation]
    if calc.operation == "calculate_percentage_change":
        return fn(**calc.parameters).result

    arg_names = _OPERATION_COLUMN_ARGS[calc.operation]
    kwargs: dict[str, Any] = dict(zip(arg_names, calc.input_columns))
    kwargs.update(calc.parameters)
    if calc.filters:
        kwargs["filters"] = calc.filters
    return fn(df, **kwargs).result


def _numerically_close(a: Any, b: Any, tol: float = _NUMERIC_TOLERANCE) -> bool:
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        if a == 0:
            return abs(b) <= tol
        return abs(a - b) / abs(a) <= tol
    return a == b


def verify_claim(
    df: pd.DataFrame,
    evidence: Evidence,
    calc: CalculationResult,
    llm_client: LLMClient,
    dataset_warnings: list[str] | None = None,
) -> VerificationResult:
    recomputed = recompute(df, calc)
    if not _numerically_close(calc.result, recomputed):
        return VerificationResult(
            claim=evidence.claim,
            status="CONTRADICTED",
            evidence=evidence,
            confidence=1.0,
            issues=[
                f"Independent recomputation produced {recomputed}, which does not match "
                f"the reported result {calc.result}."
            ],
            corrected_value=recomputed,
        )

    causal = _contains_causal_language(evidence.claim)
    warnings_text = "\n".join(dataset_warnings or []) or "(none)"
    user_message = (
        f"Claim: {evidence.claim}\n"
        f"Backing calculation: {calc.reproducible_expression} = {calc.result} "
        f"(source rows: {calc.source_rows})\n"
        f"Known dataset warnings: {warnings_text}\n"
        f"Contains causal language (detected by keyword scan): {causal}"
    )
    response = llm_client.create_message(
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_message}],
        tools=[VERIFY_TOOL],
        tool_choice={"type": "tool", "name": "submit_verification"},
        max_tokens=1024,
    )

    if not response.tool_calls:
        raise ValueError("Verification Agent did not return a verdict via submit_verification")

    verdict = response.tool_calls[0].input
    status = verdict["status"]
    issues = list(verdict.get("issues", []))
    confidence = verdict["confidence"]

    if causal and status == "VERIFIED":
        status = "PARTIALLY_VERIFIED"
        issues.append(
            "Claim contains causal language; downgraded from VERIFIED because a "
            "descriptive calculation alone cannot establish causation."
        )
        confidence = min(confidence, 0.6)

    return VerificationResult(claim=evidence.claim, status=status, evidence=evidence, confidence=confidence, issues=issues)
