import Link from "next/link";
import { CheckCircle2, FileSearch, ShieldCheck, Sparkles } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

const PIPELINE = [
  "Dataset Profile",
  "Analysis Plan",
  "Data Analysis",
  "Evidence Collection",
  "Verification",
  "Insights",
  "Recommendations",
  "Report",
];

export default function LandingPage() {
  return (
    <div className="mx-auto max-w-6xl px-6 py-16">
      <section className="mx-auto max-w-3xl text-center">
        <h1 className="text-4xl font-bold tracking-tight text-foreground sm:text-5xl">
          Evidence-backed business analytics
        </h1>
        <p className="mt-4 text-lg text-muted-foreground">
          Upload a dataset, ask a business question, and get a report where every number
          traces to a real calculation — and every claim is independently verified before
          it reaches you.
        </p>
        <div className="mt-8 flex items-center justify-center gap-3">
          <Button asChild size="lg">
            <Link href="/analyze">Start an analysis</Link>
          </Button>
          <Button asChild size="lg" variant="outline">
            <Link href="/dashboard">View dashboard</Link>
          </Button>
        </div>
      </section>

      <section className="mt-20 grid gap-6 sm:grid-cols-3">
        <Card>
          <CardHeader>
            <FileSearch className="h-6 w-6 text-primary" />
            <CardTitle className="text-base">Deterministic calculations</CardTitle>
          </CardHeader>
          <CardContent className="text-sm text-muted-foreground">
            The model never does arithmetic itself. Every number comes from a fixed set of
            pandas-backed tools, so it&apos;s reproducible and auditable.
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <ShieldCheck className="h-6 w-6 text-primary" />
            <CardTitle className="text-base">Independent verification</CardTitle>
          </CardHeader>
          <CardContent className="text-sm text-muted-foreground">
            A separate verification stage recomputes every claim and flags causal
            overreach — a descriptive finding is never dressed up as a proven cause.
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CheckCircle2 className="h-6 w-6 text-primary" />
            <CardTitle className="text-base">Traceable evidence</CardTitle>
          </CardHeader>
          <CardContent className="text-sm text-muted-foreground">
            Every insight links back to the calculation and rows that produced it, so you
            can check the work, not just trust it.
          </CardContent>
        </Card>
      </section>

      <section className="mt-20">
        <h2 className="flex items-center gap-2 text-sm font-semibold uppercase tracking-wide text-muted-foreground">
          <Sparkles className="h-4 w-4" /> How an analysis runs
        </h2>
        <ol className="mt-4 flex flex-wrap gap-2">
          {PIPELINE.map((stage, i) => (
            <li
              key={stage}
              className="flex items-center gap-2 rounded-full border border-border bg-card px-4 py-2 text-sm"
            >
              <span className="flex h-5 w-5 items-center justify-center rounded-full bg-accent text-xs font-semibold text-accent-foreground">
                {i + 1}
              </span>
              {stage}
            </li>
          ))}
        </ol>
      </section>
    </div>
  );
}
