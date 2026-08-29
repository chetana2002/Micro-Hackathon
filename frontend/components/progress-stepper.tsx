import { CheckCircle2, Circle, Loader2 } from "lucide-react";

import { PIPELINE_STAGES, type PipelineStage } from "@/lib/types";
import { cn } from "@/lib/utils";

const STAGE_LABELS: Record<PipelineStage, string> = {
  profile: "Dataset Profile",
  plan: "Analysis Plan",
  analyst: "Data Analysis",
  evidence: "Evidence Collection",
  verification: "Verification",
  insights: "Insight Synthesis",
  recommendations: "Recommendations",
  report: "Report",
};

export function ProgressStepper({
  completedStages,
  running,
  failed = false,
}: {
  completedStages: string[];
  running: boolean;
  failed?: boolean;
}) {
  return (
    <ol className="flex flex-col gap-3">
      {PIPELINE_STAGES.map((stage, i) => {
        const done = completedStages.includes(stage);
        const isCurrent = !done && running && completedStages.length === i;
        return (
          <li key={stage} className="flex items-center gap-2 text-sm">
            {done ? (
              <CheckCircle2 className="h-4 w-4 shrink-0 text-[var(--success)]" />
            ) : isCurrent ? (
              <Loader2 className="h-4 w-4 shrink-0 animate-spin text-primary" />
            ) : (
              <Circle className={cn("h-4 w-4 shrink-0", failed ? "text-[var(--danger)]" : "text-muted-foreground")} />
            )}
            <span
              className={cn(
                done ? "text-foreground" : "text-muted-foreground",
                isCurrent && "font-medium text-foreground",
              )}
            >
              {STAGE_LABELS[stage]}
            </span>
          </li>
        );
      })}
    </ol>
  );
}
