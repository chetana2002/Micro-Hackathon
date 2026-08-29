"use client";

import { useMemo, useState } from "react";
import { AlertTriangle, Loader2, UploadCloud } from "lucide-react";

import { ProgressStepper } from "@/components/progress-stepper";
import { ReportView } from "@/components/report-view";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import { ApiError, createRun, getRun, uploadDataset } from "@/lib/api";
import { PIPELINE_STAGES, type DatasetProfile, type Report, type StageRecord, type VerificationResult } from "@/lib/types";

type Phase = "idle" | "uploading" | "ready" | "running" | "done" | "error";

export default function AnalyzePage() {
  const [phase, setPhase] = useState<Phase>("idle");
  const [datasetId, setDatasetId] = useState<string | null>(null);
  const [fileName, setFileName] = useState<string | null>(null);
  const [profile, setProfile] = useState<DatasetProfile | null>(null);
  const [question, setQuestion] = useState("");
  const [report, setReport] = useState<Report | null>(null);
  const [stages, setStages] = useState<StageRecord[]>([]);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const statusByEvidenceId = useMemo(() => {
    const verificationStage = stages.find((s) => s.stage_name === "verification");
    const map: Record<string, VerificationResult["status"]> = {};
    if (verificationStage) {
      for (const vr of verificationStage.payload as VerificationResult[]) {
        map[vr.evidence.evidence_id] = vr.status;
      }
    }
    return map;
  }, [stages]);

  async function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setFileName(file.name);
    setPhase("uploading");
    setErrorMessage(null);
    try {
      const result = await uploadDataset(file);
      setDatasetId(result.dataset_id);
      setProfile(result.profile);
      setPhase("ready");
    } catch (err) {
      setErrorMessage(err instanceof ApiError ? err.message : "Upload failed.");
      setPhase("error");
    }
  }

  async function handleAnalyze() {
    if (!datasetId || !question.trim()) return;
    setPhase("running");
    setErrorMessage(null);
    setReport(null);
    setStages([]);
    try {
      const runResult = await createRun(datasetId, question.trim());
      const runDetail = await getRun(runResult.run_id);
      setStages(runDetail.stages);
      setReport(runResult.report);
      setPhase("done");
    } catch (err) {
      setErrorMessage(
        err instanceof ApiError
          ? err.message
          : "Analysis failed. Make sure the backend is running and GEMINI_API_KEY is set.",
      );
      setPhase("error");
    }
  }

  const completedStages = phase === "done" ? [...PIPELINE_STAGES] : stages.map((s) => s.stage_name);

  return (
    <div className="mx-auto max-w-5xl px-6 py-10">
      <h1 className="text-2xl font-semibold tracking-tight">InsightForge</h1>
      <p className="mt-1 text-sm text-muted-foreground">
        Upload a dataset, ask a business question, get an evidence-backed report.
      </p>

      <Card className="mt-6">
        <CardContent className="flex flex-col gap-4 p-6">
          <div>
            <label className="mb-2 block text-sm font-medium">Dataset</label>
            <label className="flex cursor-pointer items-center gap-2 rounded-md border border-dashed border-border bg-muted px-4 py-3 text-sm text-muted-foreground hover:bg-accent/50">
              <UploadCloud className="h-4 w-4" />
              {fileName ?? "Choose a CSV or XLSX file"}
              <input type="file" accept=".csv,.tsv,.xlsx,.xls" className="hidden" onChange={handleFileChange} />
            </label>
            {phase === "uploading" && (
              <p className="mt-2 flex items-center gap-1 text-xs text-muted-foreground">
                <Loader2 className="h-3 w-3 animate-spin" /> Profiling dataset…
              </p>
            )}
            {profile && (
              <p className="mt-2 text-xs text-muted-foreground">
                {profile.row_count} rows × {profile.column_count} columns
                {profile.warnings.length > 0 && ` · ${profile.warnings.length} data quality warning(s)`}
              </p>
            )}
          </div>

          <div>
            <label className="mb-2 block text-sm font-medium">Question</label>
            <Textarea
              placeholder="Why did revenue decline in Q2?"
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              disabled={!datasetId}
            />
          </div>

          <Button
            onClick={handleAnalyze}
            disabled={!datasetId || !question.trim() || phase === "running"}
            className="w-fit"
          >
            {phase === "running" && <Loader2 className="h-4 w-4 animate-spin" />}
            {phase === "running" ? "Analyzing…" : "Analyze"}
          </Button>
          {phase === "running" && (
            <p className="text-xs text-muted-foreground">
              Running all 8 pipeline stages as a single request — this can take a little while.
            </p>
          )}
        </CardContent>
      </Card>

      {errorMessage && (
        <Card className="mt-6 border-[var(--danger)]/30 bg-[var(--danger-bg)]">
          <CardContent className="flex items-center gap-2 p-4 text-sm text-[var(--danger)]">
            <AlertTriangle className="h-4 w-4 shrink-0" />
            {errorMessage}
          </CardContent>
        </Card>
      )}

      {(phase === "running" || phase === "done") && (
        <Card className="mt-6">
          <CardHeader>
            <CardTitle className="text-base">Analysis Progress</CardTitle>
          </CardHeader>
          <CardContent>
            <ProgressStepper completedStages={completedStages} running={phase === "running"} />
          </CardContent>
        </Card>
      )}

      {report && (
        <div className="mt-6">
          <ReportView report={report} statusByEvidenceId={statusByEvidenceId} />
        </div>
      )}
    </div>
  );
}
