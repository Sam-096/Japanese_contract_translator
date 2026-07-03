import { useCallback, useRef, useState } from "react"
import { FileUp, Loader2 } from "lucide-react"

import { cn } from "@/lib/utils"

const ACCEPTED = [".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff"]

interface UploadDropzoneProps {
  onFileSelected: (file: File) => void
  isUploading: boolean
}

export function UploadDropzone({ onFileSelected, isUploading }: UploadDropzoneProps) {
  const [isDragging, setIsDragging] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  const handleFiles = useCallback(
    (files: FileList | null) => {
      const file = files?.[0]
      if (file) onFileSelected(file)
    },
    [onFileSelected]
  )

  return (
    <div
      className={cn(
        "flex min-h-[320px] w-full max-w-xl flex-col items-center justify-center gap-4 rounded-xl border border-dashed border-border bg-card px-10 py-16 text-center transition-colors",
        isDragging && "border-primary bg-accent",
        isUploading && "pointer-events-none opacity-60"
      )}
      onDragOver={(e) => {
        e.preventDefault()
        setIsDragging(true)
      }}
      onDragLeave={() => setIsDragging(false)}
      onDrop={(e) => {
        e.preventDefault()
        setIsDragging(false)
        handleFiles(e.dataTransfer.files)
      }}
    >
      {isUploading ? (
        <Loader2 className="size-8 animate-spin text-primary" />
      ) : (
        <FileUp className="size-8 text-muted-foreground" strokeWidth={1.5} />
      )}
      <div className="space-y-1">
        <p className="text-sm font-medium text-foreground">
          {isUploading ? "Uploading…" : "Drop a Japanese contract or policy file"}
        </p>
        <p className="text-xs text-muted-foreground">
          PDF, PNG, JPG, or TIFF · up to 25MB
        </p>
      </div>
      <button
        type="button"
        onClick={() => inputRef.current?.click()}
        disabled={isUploading}
        className="rounded-lg border border-border bg-background px-4 py-2 text-sm font-medium text-foreground transition-colors hover:bg-muted disabled:opacity-50"
      >
        Choose file
      </button>
      <input
        ref={inputRef}
        type="file"
        accept={ACCEPTED.join(",")}
        className="hidden"
        onChange={(e) => handleFiles(e.target.files)}
      />
    </div>
  )
}
