export type JobStatus =
  | "queued"
  | "processing"
  | "translating"
  | "rendering"
  | "completed"
  | "failed"

export interface ApiError {
  code: string
  message: string
  severity?: "warning" | "error" | "critical"
  details?: Record<string, unknown>
}

export interface ApiEnvelope<T> {
  ok: boolean
  data: T | null
  error: ApiError | null
}

export interface UploadResponse {
  document_id: string
  job_id: string
  filename: string
}

export interface JobStatusResponse {
  id: string
  document_id: string
  status: JobStatus
  progress_message: string
  error: ApiError | null
}

export interface BBox {
  x0: number
  y0: number
  x1: number
  y1: number
}

export interface Block {
  id: string
  page: number
  type: "paragraph" | "heading" | "table" | "seal" | "list" | "unknown"
  text: string
  text_ja: string | null
  bbox: BBox | null
  source: string
  confidence: number
  needs_review: boolean
  order: number
  table: string[][] | null
}

export interface Page {
  number: number
  width: number
  height: number
  blocks: Block[]
}

export interface DocumentModel {
  source_path: string
  sha256: string
  kind: string
  pages: Page[]
}

export interface PreviewResponse {
  document: DocumentModel
  flagged_count: number
}

export type ConfidenceStatus = "green" | "amber" | "red"

export interface ClauseRow {
  clause_id: string
  page: number
  type: string
  source_jp: string | null
  translation_en: string | null
  confidence: number
  status: ConfidenceStatus
  needs_review: boolean
  translator: string
  notes: string
}

export interface TranslationResponse {
  clauses: ClauseRow[]
}
