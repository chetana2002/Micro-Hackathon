"use client";

import { use, useEffect, useMemo, useState } from "react";
import { AlertTriangle } from "lucide-react";

import { ReportView } from "@/components/report-view";
import { Card, CardContent } from "@/components/ui/card";
import { ApiError, getRun } from "@/lib/api";
import type { Report, RunStatusResponse, VerificationResult } from "@/lib/types";

export default function ReportPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const [run, setRun] = useState<RunStatusResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getRun(id)
      .then(setRun)
      .catch((err: unknown) => {
        setError(err instanceof ApiError ? err.message : "Could not load this report.");
      });
  }, [id]);

  const report = useMemo<Report | null>(() => {
    const stage = run?.stages.find((s) => s.stage_name === "report");
    return stage ? (stage.payload as Report) : null;
  }, [run]);

  const statusByEvidenceId = useMemo(() => {
    const verificationStage = run?.stages.find((s) => s.stage_name === "verification");
    const map: Record<string, VerificationResult["status"]> = {};
    if (verificationStage) {
      for (const vr of verificationStage.payload as VerificationResult[]) {
        map[vr.evidence.evidence_id] = vr.status;
      }
    }
    return map;
  }, [run]);

  if (error) {
    return (
      <div className="mx-auto max-w-4xl px-6 py-10">
        <Card className="border-[var(--danger)]/30 bg-[var(--danger-bg)]">
          <CardContent className="flex items-center gap-2 p-4 text-sm text-[var(--danger)]">
            <AlertTriangle className="h-4 w-4 shrink-0" />
            {error}
          </CardContent>
        </Card>
      </div>
    );
  }

  if (!run) {
    return (
      <div className="mx-auto max-w-4xl px-6 py-10">
        <p className="text-sm text-muted-foreground">Loading…</p>
      </div>
    );
  }

  if (run.status !== "COMPLETED" || !report) {
    return (
      <div className="mx-auto max-w-4xl px-6 py-10">
        <Card>
          <CardContent className="p-6 text-sm text-muted-foreground">
            This run is {run.status.toLowerCase()}
            {run.error ? `: ${run.error}` : "."} No report is available yet.
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-4xl px-6 py-10">
      <h1 className="text-2xl font-semibold tracking-tight">{run.question}</h1>
      <p className="mt-1 text-sm text-muted-foreground">Dataset: {run.dataset_name}</p>
      <div className="mt-6">
        <ReportView report={report} statusByEvidenceId={statusByEvidenceId} />
      </div>
    </div>
  );
}
