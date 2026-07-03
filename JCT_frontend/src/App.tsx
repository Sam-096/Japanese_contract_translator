import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { RotateCcw } from "lucide-react"

import {
  ApiRequestError,
  exportUrl,
  getJobStatus,
  getPreview,
  getTranslation,
  sourceUrl,
  uploadDocument,
} from "@/lib/api"
import { useAppStore } from "@/lib/store"
import { cn } from "@/lib/utils"
import { DownloadButtons } from "@/components/DownloadButtons"
import { ErrorBanner } from "@/components/ErrorBanner"
import { ImagePreview } from "@/components/ImagePreview"
import { JobStatusIndicator } from "@/components/JobStatusIndicator"
import { PdfPreview } from "@/components/PdfPreview"
import { TwoPaneReview } from "@/components/TwoPaneReview"
import { UploadDropzone } from "@/components/UploadDropzone"
import { Button } from "@/components/ui/button"

const ACTIVE_STATUSES = new Set(["queued", "processing", "translating", "rendering"])
const IMAGE_EXTENSIONS = new Set(["png", "jpg", "jpeg", "tif", "tiff"])

type ViewTab = "original" | "translated" | "review"

function App() {
  const { documentId, jobId, filename, setDocument, reset } = useAppStore()
  const queryClient = useQueryClient()
  const [tab, setTab] = useState<ViewTab>("original")

  const uploadMutation = useMutation({
    mutationFn: uploadDocument,
    onSuccess: (data) => {
      setDocument({ documentId: data.document_id, jobId: data.job_id, filename: data.filename })
      setTab("original")
    },
  })

  const jobQuery = useQuery({
    queryKey: ["job", jobId],
    queryFn: () => getJobStatus(jobId!),
    enabled: !!jobId,
    refetchInterval: (query) =>
      query.state.data && ACTIVE_STATUSES.has(query.state.data.status) ? 1500 : false,
  })

  const job = jobQuery.data
  const isCompleted = job?.status === "completed"
  const canPreview = !!job && job.status !== "queued" && job.status !== "processing"
  const canTranslate = !!job && (job.status === "rendering" || job.status === "completed")
  const isTranslating = !!job && (job.status === "translating" || job.status === "rendering")

  const previewQuery = useQuery({
    queryKey: ["preview", documentId],
    queryFn: () => getPreview(documentId!),
    enabled: !!documentId && canPreview,
  })

  const translationQuery = useQuery({
    queryKey: ["translation", documentId],
    queryFn: () => getTranslation(documentId!),
    enabled: !!documentId && canTranslate,
  })

  const handleReset = () => {
    reset()
    queryClient.clear()
    setTab("original")
  }

  const uploadError =
    uploadMutation.error instanceof ApiRequestError ? uploadMutation.error : null

  const ext = filename?.split(".").pop()?.toLowerCase() ?? ""
  const isOriginalImage = IMAGE_EXTENSIONS.has(ext)

  const tabs: { id: ViewTab; label: string; disabled?: boolean }[] = [
    { id: "original", label: "Original" },
    { id: "translated", label: "Translated PDF", disabled: !isCompleted },
    { id: "review", label: "Clause review", disabled: !previewQuery.data },
  ]

  return (
    <div className="mx-auto flex min-h-svh w-full max-w-6xl flex-col px-6 py-8">
      <header className="mb-8 flex items-center justify-between border-b border-border pb-5">
        <div>
          <p className="text-xs font-medium tracking-widest text-muted-foreground uppercase">
            Contract Translation
          </p>
          <h1 className="mt-1 text-xl font-medium text-foreground">
            {filename ?? "Japanese → English"}
          </h1>
        </div>
        <div className="flex items-center gap-4">
          {previewQuery.data && previewQuery.data.flagged_count > 0 && (
            <span className="rounded-full bg-status-amber-bg px-2 py-0.5 text-xs font-medium text-status-amber">
              {previewQuery.data.flagged_count} flagged
            </span>
          )}
          {job && <JobStatusIndicator status={job.status} message={job.progress_message} />}
          {documentId && (
            <>
              <DownloadButtons documentId={documentId} disabled={!isCompleted} />
              <Button variant="ghost" size="icon-sm" onClick={handleReset} title="Start over">
                <RotateCcw className="size-4" />
              </Button>
            </>
          )}
        </div>
      </header>

      {!documentId && (
        <div className="flex flex-1 items-center justify-center">
          <UploadDropzone
            isUploading={uploadMutation.isPending}
            onFileSelected={(file) => uploadMutation.mutate(file)}
          />
        </div>
      )}

      {uploadError && (
        <div className="mb-6">
          <ErrorBanner message={uploadError.message} severity={uploadError.severity} />
        </div>
      )}

      {jobId && jobQuery.isError && (
        <div className="mb-6">
          <ErrorBanner
            message="We lost contact with the translation server. Don't close this page — we're automatically attempting to reconnect."
            severity="warning"
          />
        </div>
      )}

      {job?.status === "failed" && job.error && (
        <div className="mb-6">
          <ErrorBanner message={job.error.message} severity={job.error.severity} />
        </div>
      )}

      {documentId && (
        <div className="flex-1">
          <div className="mb-6 flex gap-1 border-b border-border">
            {tabs.map((t) => (
              <button
                key={t.id}
                type="button"
                disabled={t.disabled}
                onClick={() => setTab(t.id)}
                className={cn(
                  "px-3 py-2 text-sm font-medium text-muted-foreground disabled:cursor-not-allowed disabled:opacity-40",
                  tab === t.id && "border-b-2 border-primary text-foreground"
                )}
              >
                {t.label}
              </button>
            ))}
          </div>

          {tab === "original" && documentId && (
            isOriginalImage ? (
              <ImagePreview url={sourceUrl(documentId)} />
            ) : (
              <PdfPreview url={sourceUrl(documentId)} />
            )
          )}

          {tab === "translated" && documentId && isCompleted && (
            <PdfPreview url={exportUrl(documentId, "pdf")} />
          )}

          {tab === "review" && (
            <>
              {previewQuery.isLoading && (
                <p className="text-sm text-muted-foreground">Loading preview…</p>
              )}
              {previewQuery.data && (
                <TwoPaneReview
                  document={previewQuery.data.document}
                  clauses={translationQuery.data?.clauses ?? []}
                  isTranslating={isTranslating}
                />
              )}
            </>
          )}
        </div>
      )}
    </div>
  )
}

export default App
