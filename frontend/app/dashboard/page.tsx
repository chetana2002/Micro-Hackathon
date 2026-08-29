"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { AlertTriangle, Plus } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ApiError, listRuns } from "@/lib/api";
import type { RunSummary } from "@/lib/types";

const STATUS_VARIANT: Record<RunSummary["status"], "success" | "warning" | "danger" | "neutral"> = {
  COMPLETED: "success",
  RUNNING: "warning",
  PENDING: "neutral",
  FAILED: "danger",
};

export default function DashboardPage() {
  const [runs, setRuns] = useState<RunSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listRuns()
      .then(setRuns)
      .catch((err: unknown) => {
        setError(
          err instanceof ApiError
            ? `Could not reach the InsightForge API (${err.message}).`
            : "Could not reach the InsightForge API. Is the backend running?",
        );
      });
  }, []);

  return (
    <div className="mx-auto max-w-4xl px-6 py-10">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Dashboard</h1>
          <p className="mt-1 text-sm text-muted-foreground">Every analysis you&apos;ve run, most recent first.</p>
        </div>
        <Button asChild>
          <Link href="/analyze">
            <Plus className="h-4 w-4" /> New analysis
          </Link>
        </Button>
      </div>

      <div className="mt-8">
        {error && (
          <Card className="border-[var(--danger)]/30 bg-[var(--danger-bg)]">
            <CardContent className="flex items-center gap-2 p-4 text-sm text-[var(--danger)]">
              <AlertTriangle className="h-4 w-4 shrink-0" />
              {error}
            </CardContent>
          </Card>
        )}

        {!error && runs === null && <p className="text-sm text-muted-foreground">Loading…</p>}

        {!error && runs !== null && runs.length === 0 && (
          <Card>
            <CardContent className="p-8 text-center text-sm text-muted-foreground">
              No analyses yet.{" "}
              <Link href="/analyze" className="text-primary hover:underline">
                Start your first one
              </Link>
              .
            </CardContent>
          </Card>
        )}

        {!error && runs !== null && runs.length > 0 && (
          <div className="flex flex-col gap-3">
            {runs.map((run) => (
              <Card key={run.run_id}>
                <CardHeader className="flex flex-row items-center justify-between gap-4 space-y-0">
                  <div>
                    <CardTitle className="text-base">{run.question}</CardTitle>
                    <p className="mt-1 text-xs text-muted-foreground">
                      {run.dataset_name} · {new Date(run.created_at).toLocaleString()}
                    </p>
                  </div>
                  <div className="flex items-center gap-3">
                    <Badge variant={STATUS_VARIANT[run.status]}>{run.status}</Badge>
                    {run.status === "COMPLETED" && (
                      <Button asChild size="sm" variant="outline">
                        <Link href={`/reports/${run.run_id}`}>View report</Link>
                      </Button>
                    )}
                  </div>
                </CardHeader>
              </Card>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
