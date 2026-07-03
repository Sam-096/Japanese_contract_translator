import type { ConfidenceStatus } from "@/lib/types"
import { cn } from "@/lib/utils"

const STYLES: Record<ConfidenceStatus, string> = {
  green: "bg-status-green-bg text-status-green",
  amber: "bg-status-amber-bg text-status-amber",
  red: "bg-status-red-bg text-status-red",
}

const LABELS: Record<ConfidenceStatus, string> = {
  green: "High confidence",
  amber: "Review recommended",
  red: "Needs attention",
}

interface ConfidenceBadgeProps {
  status: ConfidenceStatus
  confidence: number
  compact?: boolean
}

export function ConfidenceBadge({ status, confidence, compact }: ConfidenceBadgeProps) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium whitespace-nowrap",
        STYLES[status]
      )}
      title={LABELS[status]}
    >
      <span className="size-1.5 rounded-full bg-current" />
      {compact ? `${Math.round(confidence * 100)}%` : `${LABELS[status]} · ${Math.round(confidence * 100)}%`}
    </span>
  )
}
