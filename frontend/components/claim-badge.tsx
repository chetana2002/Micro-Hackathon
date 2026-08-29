import { Badge } from "@/components/ui/badge";
import type { VerificationStatus } from "@/lib/types";

const STATUS_CONFIG: Record<
  VerificationStatus,
  { label: string; variant: "success" | "warning" | "danger" | "neutral" }
> = {
  VERIFIED: { label: "VERIFIED", variant: "success" },
  PARTIALLY_VERIFIED: { label: "PARTIALLY VERIFIED", variant: "warning" },
  UNSUPPORTED: { label: "UNSUPPORTED", variant: "neutral" },
  CONTRADICTED: { label: "CONTRADICTED", variant: "danger" },
};

export function ClaimBadge({ status }: { status: VerificationStatus }) {
  const config = STATUS_CONFIG[status];
  return <Badge variant={config.variant}>{config.label}</Badge>;
}
