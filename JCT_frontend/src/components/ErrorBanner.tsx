import { AlertTriangle } from "lucide-react"

interface ErrorBannerProps {
  message: string
  severity?: "warning" | "error" | "critical"
  onRetry?: () => void
}

// `message` is always the already-safe, user-facing copy — the backend's
// error catalog (JCT_Backend_v1/app/core/error_catalog.py) does the
// translation from raw exception text to friendly copy, so there's nothing
// left to look up or mask here. Raw technical detail never reaches this
// component in the first place.
export function ErrorBanner({ message, severity = "error", onRetry }: ErrorBannerProps) {
  const isWarning = severity === "warning"
  const colorClasses = isWarning
    ? "border-status-amber/30 bg-status-amber-bg text-status-amber"
    : "border-status-red/30 bg-status-red-bg text-status-red"

  return (
    <div className={`flex items-start gap-3 rounded-lg border px-4 py-3 text-sm ${colorClasses}`}>
      <AlertTriangle className="mt-0.5 size-4 shrink-0" />
      <div className="flex-1 space-y-1">
        <p className="font-medium">{message}</p>
      </div>
      {onRetry && (
        <button
          type="button"
          onClick={onRetry}
          className="shrink-0 rounded-md border border-current/30 px-2.5 py-1 text-xs font-medium hover:bg-current/10"
        >
          Retry
        </button>
      )}
    </div>
  )
}
