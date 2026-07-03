import { useEffect, useRef, useState } from "react"

import { pdfjsLib } from "@/lib/pdf"

interface PdfPreviewProps {
  url: string
}

export function PdfPreview({ url }: PdfPreviewProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading")

  useEffect(() => {
    let cancelled = false
    setStatus("loading")

    async function run() {
      const container = containerRef.current
      if (!container) return
      container.innerHTML = ""

      try {
        const pdf = await pdfjsLib.getDocument({ url }).promise
        if (cancelled) return

        const targetWidth = container.clientWidth || 800

        for (let i = 1; i <= pdf.numPages; i++) {
          if (cancelled) return
          const page = await pdf.getPage(i)
          const unscaled = page.getViewport({ scale: 1 })
          const scale = targetWidth / unscaled.width
          const viewport = page.getViewport({ scale })

          const canvas = document.createElement("canvas")
          canvas.width = viewport.width
          canvas.height = viewport.height
          canvas.className = "mb-4 w-full rounded-lg border border-border shadow-sm last:mb-0"
          container.appendChild(canvas)

          const ctx = canvas.getContext("2d")
          if (!ctx) continue
          await page.render({ canvasContext: ctx, viewport, canvas }).promise
        }
        if (!cancelled) setStatus("ready")
      } catch (err) {
        console.error("PDF preview failed", err)
        if (!cancelled) setStatus("error")
      }
    }

    run()
    return () => {
      cancelled = true
    }
  }, [url])

  return (
    <div>
      {status === "loading" && <p className="text-sm text-muted-foreground">Loading preview…</p>}
      {status === "error" && (
        <p className="text-sm text-status-red">Could not load the PDF preview.</p>
      )}
      <div ref={containerRef} />
    </div>
  )
}
