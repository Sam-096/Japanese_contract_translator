import { FileText } from "lucide-react";

import { exportUrl } from "@/lib/api"
import { Button } from "@/components/ui/button"

interface DownloadButtonsProps {
  documentId: string
  disabled?: boolean
}

export function DownloadButtons({ documentId, disabled }: DownloadButtonsProps) {
  return (
    <div className="flex items-center gap-2">
      <Button variant="outline" size="sm" disabled={disabled} asChild={!disabled}>
        {disabled ? (
          <span className="inline-flex items-center gap-1.5">
            <FileText className="size-3.5" /> English PDF
          </span>
        ) : (
          <a href={exportUrl(documentId, "pdf")} className="inline-flex items-center gap-1.5">
            <FileText className="size-3.5" /> English PDF
          </a>
        )}
      </Button>
      {/* <Button variant="outline" size="sm" disabled={disabled} asChild={!disabled}>
        {disabled ? (
          <span className="inline-flex items-center gap-1.5">
            <FileSpreadsheet className="size-3.5" /> Clause Excel
          </span>
        ) : (
          <a href={exportUrl(documentId, "xlsx")} className="inline-flex items-center gap-1.5">
            <FileSpreadsheet className="size-3.5" /> Clause Excel
          </a>
        )}
      </Button> */}
    </div>
  )
}
