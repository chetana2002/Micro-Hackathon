import type { CreateRunResponse, RunStatusResponse, RunSummary, UploadDatasetResponse } from "./types";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function handleResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = await response.json();
      detail = body.detail ?? detail;
    } catch {
      // response body wasn't JSON; fall back to statusText
    }
    throw new ApiError(detail, response.status);
  }
  return response.json() as Promise<T>;
}

export async function uploadDataset(file: File): Promise<UploadDatasetResponse> {
  const formData = new FormData();
  formData.append("file", file);
  const response = await fetch(`${API_BASE_URL}/api/datasets`, {
    method: "POST",
    body: formData,
  });
  return handleResponse<UploadDatasetResponse>(response);
}

export async function createRun(datasetId: string, question: string): Promise<CreateRunResponse> {
  const params = new URLSearchParams({ dataset_id: datasetId, question });
  const response = await fetch(`${API_BASE_URL}/api/runs?${params.toString()}`, {
    method: "POST",
  });
  return handleResponse<CreateRunResponse>(response);
}

export async function getRun(runId: string): Promise<RunStatusResponse> {
  const response = await fetch(`${API_BASE_URL}/api/runs/${runId}`);
  return handleResponse<RunStatusResponse>(response);
}

export async function listRuns(): Promise<RunSummary[]> {
  const response = await fetch(`${API_BASE_URL}/api/runs`, { cache: "no-store" });
  return handleResponse<RunSummary[]>(response);
}
