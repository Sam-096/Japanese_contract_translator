import * as pdfjsLib from "pdfjs-dist"
import PdfWorkerUrl from "pdfjs-dist/build/pdf.worker.min.mjs?url"

pdfjsLib.GlobalWorkerOptions.workerSrc = PdfWorkerUrl

export { pdfjsLib }
