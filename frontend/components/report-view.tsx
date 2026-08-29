import { ChartPanel } from "@/components/chart-panel";
import { ClaimBadge } from "@/components/claim-badge";
import { EvidenceCard } from "@/components/evidence-card";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { Report, VerificationStatus } from "@/lib/types";

export function ReportView({
  report,
  statusByEvidenceId,
}: {
  report: Report;
  statusByEvidenceId: Record<string, VerificationStatus>;
}) {
  return (
    <div className="flex flex-col gap-6">
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Executive Summary</CardTitle>
        </CardHeader>
        <CardContent className="text-sm">{report.executive_summary}</CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Dataset Overview</CardTitle>
        </CardHeader>
        <CardContent className="text-sm text-muted-foreground">
          {report.dataset_overview.row_count} rows × {report.dataset_overview.column_count} columns:{" "}
          {report.dataset_overview.columns.join(", ")}
        </CardContent>
      </Card>

      {report.data_quality_warnings.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Data Quality</CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="list-inside list-disc text-sm text-muted-foreground">
              {report.data_quality_warnings.map((w, i) => (
                <li key={i}>{w}</li>
              ))}
            </ul>
          </CardContent>
        </Card>
      )}

      <div>
        <h2 className="mb-3 text-lg font-semibold">Key Findings</h2>
        <div className="flex flex-col gap-4">
          {report.key_findings.length === 0 && (
            <p className="text-sm text-muted-foreground">No verified findings for this question.</p>
          )}
          {report.key_findings.map((insight, i) => {
            const evidenceId = insight.evidence[0]?.evidence_id;
            const status = evidenceId ? statusByEvidenceId[evidenceId] : undefined;
            return (
              <Card key={i}>
                <CardHeader className="flex flex-row items-center justify-between space-y-0">
                  <CardTitle className="text-base">{insight.title}</CardTitle>
                  {status && <ClaimBadge status={status} />}
                </CardHeader>
                <CardContent className="flex flex-col gap-3">
                  <p className="text-sm">{insight.finding}</p>
                  <p className="text-sm text-muted-foreground">{insight.business_significance}</p>
                  {insight.limitations.length > 0 && (
                    <ul className="list-inside list-disc text-xs text-muted-foreground">
                      {insight.limitations.map((lim, j) => (
                        <li key={j}>{lim}</li>
                      ))}
                    </ul>
                  )}
                  {insight.evidence.map((ev) => (
                    <EvidenceCard key={ev.evidence_id} evidence={ev} />
                  ))}
                </CardContent>
              </Card>
            );
          })}
        </div>
      </div>

      {report.charts.length > 0 && (
        <div>
          <h2 className="mb-3 text-lg font-semibold">Charts</h2>
          <div className="grid gap-4 sm:grid-cols-2">
            {report.charts.map((chart, i) => (
              <ChartPanel key={i} chart={chart} />
            ))}
          </div>
        </div>
      )}

      <div>
        <h2 className="mb-3 text-lg font-semibold">Recommendations</h2>
        <div className="flex flex-col gap-3">
          {report.recommendations.length === 0 && (
            <p className="text-sm text-muted-foreground">No recommendations for this question.</p>
          )}
          {report.recommendations.map((rec, i) => (
            <Card key={i}>
              <CardContent className="flex flex-col gap-1 p-4 text-sm">
                <p className="font-medium">{rec.recommendation}</p>
                <p className="text-muted-foreground">Expected impact: {rec.expected_impact}</p>
                <p className="text-muted-foreground">Uncertainty: {rec.uncertainty}</p>
                <p className="text-muted-foreground">Next investigation: {rec.next_investigation}</p>
              </CardContent>
            </Card>
          ))}
        </div>
      </div>

      {report.limitations.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Limitations</CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="list-inside list-disc text-sm text-muted-foreground">
              {report.limitations.map((lim, i) => (
                <li key={i}>{lim}</li>
              ))}
            </ul>
          </CardContent>
        </Card>
      )}

      {report.open_questions.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Questions Requiring Further Investigation</CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="list-inside list-disc text-sm text-muted-foreground">
              {report.open_questions.map((q, i) => (
                <li key={i}>{q}</li>
              ))}
            </ul>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
