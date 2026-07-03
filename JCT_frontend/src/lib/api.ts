import axios from "axios"

import type {
  ApiEnvelope,
  JobStatusResponse,
  PreviewResponse,
  TranslationResponse,
  UploadResponse,
} from "./types"

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "/api"

export const api = axios.create({ baseURL: BASE_URL })

export class ApiRequestError extends Error {
  code: string
  severity: "warning" | "error" | "critical"
  details?: Record<string, unknown>

  constructor(
    code: string,
    message: string,
    severity: "warning" | "error" | "critical" = "error",
    details?: Record<string, unknown>
  ) {
    super(message)
    this.code = code
    this.severity = severity
    this.details = details
  }
}

async function unwrap<T>(promise: Promise<{ data: ApiEnvelope<T> }>): Promise<T> {
  try {
    const { data: envelope } = await promise
    if (!envelope.ok || envelope.data === null) {
      const err = envelope.error
      throw new ApiRequestError(
        err?.code ?? "UNKNOWN_ERROR",
        err?.message ?? "Something went wrong.",
        err?.severity ?? "error",
        err?.details
      )
    }
    return envelope.data
  } catch (err) {
    if (err instanceof ApiRequestError) throw err
    if (axios.isAxiosError(err) && err.response?.data?.error) {
      const apiErr = err.response.data.error
      throw new ApiRequestError(apiErr.code, apiErr.message, apiErr.severity ?? "error", apiErr.details)
    }
    // Backend unreachable (network drop, wrong URL, CORS block, cold start) —
    // distinct from a real API error: "warning" since a retry may well
    // succeed, not something the backend could have told us about.
    throw new ApiRequestError("NETWORK_ERROR", "Could not reach the server.", "warning")
  }
}

export function uploadDocument(file: File): Promise<UploadResponse> {
  const form = new FormData()
  form.append("file", file)
  return unwrap(api.post("/upload", form))
}

export function getJobStatus(jobId: string): Promise<JobStatusResponse> {
  return unwrap(api.get(`/jobs/${jobId}`))
}

export function getPreview(documentId: string): Promise<PreviewResponse> {
  return unwrap(api.get(`/documents/${documentId}/preview`))
}

export function getTranslation(documentId: string): Promise<TranslationResponse> {
  return unwrap(api.get(`/documents/${documentId}/translation`))
}

export function exportUrl(documentId: string, kind: "pdf" | "xlsx"): string {
  return `${BASE_URL}/documents/${documentId}/export/${kind}`
}

export function sourceUrl(documentId: string): string {
  return `${BASE_URL}/documents/${documentId}/source`
}
