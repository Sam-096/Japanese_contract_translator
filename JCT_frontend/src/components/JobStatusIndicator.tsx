import { CheckCircle2, Loader2, XCircle } from "lucide-react"

import type { JobStatus } from "@/lib/types"

const LABELS: Record<JobStatus, string> = {
  queued: "Queued",
  processing: "Extracting text / running OCR",
  translating: "Translating clauses",
  rendering: "Rendering downloads",
  completed: "Done",
  failed: "Failed",
}

interface JobStatusIndicatorProps {
  status: JobStatus
  message?: string
}

export function JobStatusIndicator({ status, message }: JobStatusIndicatorProps) {
  if (status === "completed") {
    return (
      <span className="inline-flex items-center gap-1.5 text-sm font-medium text-status-green">
        <CheckCircle2 className="size-4" />
        Ready
      </span>
    )
  }
  if (status === "failed") {
    return (
      <span className="inline-flex items-center gap-1.5 text-sm font-medium text-status-red">
        <XCircle className="size-4" />
        Failed
      </span>
    )
  }
  return (
    <span className="inline-flex items-center gap-1.5 text-sm font-medium text-muted-foreground">
      <Loader2 className="size-4 animate-spin" />
      {message || LABELS[status]}
    </span>
  )
}
