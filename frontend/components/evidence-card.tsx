"use client";

import { useState } from "react";
import { ChevronDown, ChevronUp } from "lucide-react";

import { Card, CardContent } from "@/components/ui/card";
import type { Evidence } from "@/lib/types";

export function EvidenceCard({ evidence }: { evidence: Evidence }) {
  const [open, setOpen] = useState(false);

  return (
    <Card>
      <CardContent className="p-4">
        <p className="text-sm text-foreground">{evidence.claim}</p>
        <button
          type="button"
          onClick={() => setOpen((o) => !o)}
          className="mt-2 flex items-center gap-1 text-xs font-medium text-primary hover:underline"
        >
          {open ? "Hide calculation" : "View calculation"}
          {open ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
        </button>
        {open && (
          <div className="mt-2 rounded-md bg-muted p-3 font-mono text-xs text-muted-foreground">
            <div>{evidence.calculation}</div>
            <div className="mt-1">Result: {JSON.stringify(evidence.result)}</div>
            <div className="mt-1">Confidence: {(evidence.confidence * 100).toFixed(0)}%</div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
