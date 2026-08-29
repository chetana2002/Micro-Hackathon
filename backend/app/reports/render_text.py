"""Deterministic Markdown rendering of a Report object.

Used both to let a user export/download the report (per the brief) and to
give the evaluation framework a plain-text representation of the full
agent's output so it can be scored by exactly the same method as the
baseline's free-text output — a fairness requirement, not a UI nicety.
"""
from __future__ import annotations

from app.models.report import Report


def render_report_markdown(report: Report) -> str:
    lines: list[str] = []
    lines.append("# Business Analytics Report")
    lines.append("")
    lines.append("## Business Question")
    lines.append(report.question)
    lines.append("")
    lines.append("## Executive Summary")
    lines.append(report.executive_summary)
    lines.append("")

    p = report.dataset_overview
    lines.append("## Dataset Overview")
    lines.append(f"- Rows: {p.row_count}, Columns: {p.column_count}")
    lines.append(f"- Columns: {', '.join(p.columns)}")
    lines.append("")

    lines.append("## Data Quality")
    if report.data_quality_warnings:
        lines.extend(f"- {w}" for w in report.data_quality_warnings)
    else:
        lines.append("- No data quality issues detected.")
    lines.append("")

    lines.append("## Key Findings")
    if report.key_findings:
        for i, ins in enumerate(report.key_findings, 1):
            lines.append(f"### {i}. {ins.title}")
            lines.append(ins.finding)
            lines.append(f"Business significance: {ins.business_significance}")
            lines.append(f"Confidence: {ins.confidence}")
            if ins.limitations:
                lines.append(f"Limitations: {'; '.join(ins.limitations)}")
            lines.append("")
    else:
        lines.append("(No verified findings.)")
        lines.append("")

    lines.append("## Evidence")
    for e in report.evidence:
        lines.append(f"- [{e.evidence_id}] {e.claim} — {e.calculation} = {e.result} (confidence {e.confidence})")
    lines.append("")

    lines.append("## Charts")
    for c in report.charts:
        lines.append(f"- {c.chart_type} chart: {c.title}")
    lines.append("")

    lines.append("## Business Implications")
    for ins in report.key_findings:
        lines.append(f"- {ins.business_significance}")
    lines.append("")

    lines.append("## Recommendations")
    for r in report.recommendations:
        lines.append(
            f"- {r.recommendation} (expected impact: {r.expected_impact}; "
            f"uncertainty: {r.uncertainty}; next investigation: {r.next_investigation})"
        )
    lines.append("")

    lines.append("## Limitations")
    for lim in report.limitations:
        lines.append(f"- {lim}")
    lines.append("")

    lines.append("## Questions Requiring Further Investigation")
    for q in report.open_questions:
        lines.append(f"- {q}")

    return "\n".join(lines)
