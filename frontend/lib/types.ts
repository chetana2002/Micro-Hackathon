// Mirrors the Pydantic models in backend/app/models/*.py. Kept hand-written
// rather than generated, since the backend has no OpenAPI-schema export step
// yet — see docs/limitations.md.

export interface FilterSpec {
  column: string;
  op: "==" | "!=" | ">" | ">=" | "<" | "<=" | "in" | "not_in";
  value: unknown;
}

export interface CalculationResult {
  operation: string;
  input_columns: string[];
  filters: FilterSpec[];
  parameters: Record<string, unknown>;
  result: unknown;
  source_rows: number;
  reproducible_expression: string;
  warnings: string[];
}

export interface Evidence {
  evidence_id: string;
  claim: string;
  source_operation: string;
  source_columns: string[];
  filters: FilterSpec[];
  calculation: string;
  result: unknown;
  confidence: number;
}

export type VerificationStatus =
  | "VERIFIED"
  | "PARTIALLY_VERIFIED"
  | "UNSUPPORTED"
  | "CONTRADICTED";

export interface VerificationResult {
  claim: string;
  status: VerificationStatus;
  evidence: Evidence;
  confidence: number;
  issues: string[];
  corrected_value?: unknown;
}

export interface Insight {
  title: string;
  finding: string;
  evidence: Evidence[];
  business_significance: string;
  confidence: number;
  limitations: string[];
}

export interface Recommendation {
  recommendation: string;
  supporting_evidence: Evidence[];
  expected_impact: string;
  uncertainty: string;
  next_investigation: string;
}

export interface ChartSeries {
  name: string;
  data: { x: string; y: number }[];
}

export interface ChartSpec {
  chart_type: "line" | "bar";
  title: string;
  x_label: string;
  y_label: string;
  series: ChartSeries[];
}

export type SemanticType =
  | "numeric"
  | "categorical"
  | "date"
  | "boolean"
  | "identifier"
  | "text"
  | "unknown";

export interface ColumnProfile {
  name: string;
  dtype: string;
  semantic_type: SemanticType;
  missing_count: number;
  missing_pct: number;
  unique_count: number;
  sample_values: string[];
}

export interface DatasetProfile {
  dataset_name: string;
  row_count: number;
  column_count: number;
  columns: string[];
  data_types: Record<string, string>;
  missing_values: Record<string, number>;
  duplicate_count: number;
  date_columns: string[];
  numeric_columns: string[];
  categorical_columns: string[];
  warnings: string[];
  column_profiles: ColumnProfile[];
}

export interface Report {
  question: string;
  executive_summary: string;
  dataset_overview: DatasetProfile;
  data_quality_warnings: string[];
  key_findings: Insight[];
  evidence: Evidence[];
  charts: ChartSpec[];
  recommendations: Recommendation[];
  limitations: string[];
  open_questions: string[];
}

export const PIPELINE_STAGES = [
  "profile",
  "plan",
  "analyst",
  "evidence",
  "verification",
  "insights",
  "recommendations",
  "report",
] as const;

export type PipelineStage = (typeof PIPELINE_STAGES)[number];

export interface StageRecord {
  stage_name: string;
  payload: unknown;
}

export interface UploadDatasetResponse {
  dataset_id: string;
  profile: DatasetProfile;
}

export interface CreateRunResponse {
  run_id: string;
  status: "COMPLETED" | "FAILED";
  report: Report | null;
}

export interface RunStatusResponse {
  run_id: string;
  status: "PENDING" | "RUNNING" | "COMPLETED" | "FAILED";
  error: string | null;
  question: string;
  dataset_name: string;
  stages: StageRecord[];
}

export interface RunSummary {
  run_id: string;
  status: "PENDING" | "RUNNING" | "COMPLETED" | "FAILED";
  question: string;
  dataset_name: string;
  created_at: string;
}
