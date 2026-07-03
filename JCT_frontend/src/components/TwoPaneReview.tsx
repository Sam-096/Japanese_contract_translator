import { useState } from "react"

import type { ClauseRow, DocumentModel } from "@/lib/types"
import { cn } from "@/lib/utils"
import { ConfidenceBadge } from "./ConfidenceBadge"

interface Row {
  clauseId: string
  page: number
  type: string
  sourceJa: string
  clause: ClauseRow | null
}

function buildRows(document: DocumentModel): Row[] {
  const rows: Row[] = []
  for (const page of document.pages) {
    const blocks = [...page.blocks].sort((a, b) => a.order - b.order)
    for (const block of blocks) {
      rows.push({
        clauseId: block.id,
        page: page.number,
        type: block.type,
        sourceJa: block.text_ja ?? block.text,
        clause: null,
      })
    }
  }
  return rows
}

interface TwoPaneReviewProps {
  document: DocumentModel
  clauses: ClauseRow[]
  isTranslating: boolean
}

export function TwoPaneReview({ document, clauses, isTranslating }: TwoPaneReviewProps) {
  const [activeId, setActiveId] = useState<string | null>(null)
  const clauseById = new Map(clauses.map((c) => [c.clause_id, c]))
  const rows = buildRows(document).map((r) => ({ ...r, clause: clauseById.get(r.clauseId) ?? null }))

  let currentPage = 0

  return (
    <div className="overflow-hidden rounded-lg border border-border">
      <div className="grid grid-cols-2 border-b border-border bg-muted/60 text-xs font-medium tracking-wide text-muted-foreground uppercase">
        <div className="border-r border-border px-4 py-2">Japanese source</div>
        <div className="px-4 py-2">English translation</div>
      </div>
      <div className="divide-y divide-border">
        {rows.map((row) => {
          const showPageHeader = row.page !== currentPage
          currentPage = row.page
          const isActive = activeId === row.clauseId
          return (
            <div key={row.clauseId}>
              {showPageHeader && (
                <div className="bg-muted/30 px-4 py-1 text-[11px] font-medium tracking-wide text-muted-foreground uppercase">
                  Page {row.page}
                </div>
              )}
              <div
                className={cn(
                  "grid grid-cols-2 transition-colors",
                  isActive && "bg-accent"
                )}
                onMouseEnter={() => setActiveId(row.clauseId)}
                onMouseLeave={() => setActiveId(null)}
              >
                <div className="border-r border-border px-4 py-3 text-sm whitespace-pre-wrap text-foreground">
                  {row.sourceJa || <span className="text-muted-foreground italic">—</span>}
                </div>
                <div className="px-4 py-3">
                  {row.clause ? (
                    <div className="space-y-1.5">
                      <p className="text-sm whitespace-pre-wrap text-foreground">
                        {row.clause.translation_en}
                      </p>
                      <div className="flex flex-wrap items-center gap-2">
                        <ConfidenceBadge status={row.clause.status} confidence={row.clause.confidence} compact />
                        {row.clause.notes && (
                          <span className="text-[11px] text-muted-foreground">{row.clause.notes}</span>
                        )}
                      </div>
                    </div>
                  ) : isTranslating ? (
                    <p className="text-sm text-muted-foreground italic">Translating…</p>
                  ) : (
                    <p className="text-sm text-muted-foreground italic">—</p>
                  )}
                </div>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
