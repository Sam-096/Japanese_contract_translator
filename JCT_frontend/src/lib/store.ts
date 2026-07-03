import { create } from "zustand"

interface AppState {
  documentId: string | null
  jobId: string | null
  filename: string | null
  setDocument: (args: { documentId: string; jobId: string; filename: string }) => void
  reset: () => void
}

export const useAppStore = create<AppState>((set) => ({
  documentId: null,
  jobId: null,
  filename: null,
  setDocument: ({ documentId, jobId, filename }) => set({ documentId, jobId, filename }),
  reset: () => set({ documentId: null, jobId: null, filename: null }),
}))
