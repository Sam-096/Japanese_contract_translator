Below is a **production-grade starter spec** you can paste into Claude as the implementation brief. It keeps the system modular, privacy-aware, and scalable, with a polished Swiss-style UI on the frontend and a robust FastAPI backend. Groq uses `GROQ_API_KEY` from env and supports models like `llama-3.3-70b-versatile` for general use, with the API key loaded via environment variable. [docs.agno](https://docs.agno.com/models/providers/gateways/groq/overview)

***

# Japanese Document Translation Platform — Claude Build Spec

## 1. Product Goal

Build a private, high-trust document pipeline for Japanese contracts and policy files. The user uploads a PDF, image, or scanned document, sees a preview of the original and translated output, and downloads searchable English deliverables in PDF and Excel.

The app must feel like a premium Swiss digital product: calm, minimal, precise, whitespace-first, and never “AI-generated” in appearance.

***

## 2. Core User Flow

1. User opens the app.
2. User uploads one file.
3. System detects file type and starts processing.
4. UI shows live progress, page preview, extracted text, confidence flags, and translation status.
5. User reviews source and translated content side by side.
6. User downloads:
- English PDF.
- Excel clause table.
- Intermediate audit JSON if needed.

There is no login page in Phase 1.

***

## 3. Recommended Stack

### Frontend
- React + Vite.
- Shadcn UI.
- Tailwind CSS.
- Zustand for client state.
- React Query for server state and polling.
- Framer Motion only for subtle motion, not decoration.
- Optional PDF preview via `pdf.js`.

### Backend
- FastAPI.
- Pydantic v2.
- SQLModel or plain Pydantic + filesystem storage for Phase 1.
- Celery + Redis later if async jobs grow.
- `python-multipart` for upload handling.
- `pymupdf` for text PDFs.
- OCR/translation services behind interfaces.

### AI Providers
- Local OCR / translation paths where possible.
- Groq as cloud translation/verification fallback using `GROQ_API_KEY` from env. [pydantic](https://pydantic.dev/docs/ai/models/groq/)
- Model default for text translation: `llama-3.3-70b-versatile`. [console.groq](https://console.groq.com/docs/models)

***

## 4. Environment Variables

Use a single `.env` file in backend and expose only safe frontend vars.

```env
# backend/.env
GROQ_API_KEY=paste_here
GROQ_MODEL=llama-3.3-70b-versatile
GROQ_FALLBACK_MODEL=llama-3.1-8b-instant

APP_ENV=development
CORS_ORIGINS=https://jctai.netlify.app,http://localhost:5173
MAX_UPLOAD_MB=25
UPLOAD_DIR=./data/uploads
OUTPUT_DIR=./data/output
TEMP_DIR=./data/tmp
LOG_LEVEL=INFO
```

Frontend env:

```env
# frontend/.env
VITE_API_BASE_URL=https://your-render-backend.onrender.com
```

***

## 5. Backend Architecture

Use a strict service-based architecture, not a monolith. Keep each concern separate: upload, OCR, translation, verification, rendering, export, and logging.

### Suggested structure

```txt
backend/
├── app/
│   ├── api/
│   │   ├── routes_upload.py
│   │   ├── routes_jobs.py
│   │   ├── routes_preview.py
│   │   └── routes_export.py
│   ├── core/
│   │   ├── config.py
│   │   ├── logging.py
│   │   ├── security.py
│   │   └── exceptions.py
│   ├── services/
│   │   ├── ingest_service.py
│   │   ├── ocr_service.py
│   │   ├── translate_service.py
│   │   ├── verify_service.py
│   │   ├── render_service.py
│   │   └── export_service.py
│   ├── adapters/
│   │   ├── groq_client.py
│   │   ├── local_llm_client.py
│   │   ├── pdf_extract.py
│   │   └── ocr_clients.py
│   ├── schemas/
│   │   ├── job.py
│   │   ├── document.py
│   │   └── export.py
│   └── main.py
├── tests/
├── requirements.txt
└── .env
```

This is SOLID-friendly:
- Single Responsibility: each service does one thing.
- Open/Closed: add a new AI provider by adding an adapter.
- Liskov: Groq/local models implement the same interface.
- Interface Segregation: upload, translate, export are separate APIs.
- Dependency Inversion: services depend on interfaces, not vendor code.

***

## 6. Backend Behavior

### File handling
- Accept PDF, PNG, JPG, JPEG, TIFF.
- Reject unsupported files with clear error messages.
- Limit size and page count.
- Save uploaded files with UUID-based names.
- Never trust extension alone; inspect MIME type.

### Processing flow
1. Detect digital PDF vs scanned image.
2. Extract text directly if available.
3. Use OCR only where needed.
4. Normalize blocks into canonical JSON.
5. Translate clause-wise, not full-document blindly.
6. Verify low-confidence clauses.
7. Render final outputs.

### Error handling
Return structured errors:
- `UPLOAD_TOO_LARGE`
- `UNSUPPORTED_FILE_TYPE`
- `OCR_FAILED`
- `TRANSLATION_TIMEOUT`
- `GROQ_RATE_LIMITED`
- `EXPORT_FAILED`

Never crash the pipeline because one page failed. Mark that page as flagged and continue.

***

## 7. AI Strategy

Use tiered intelligence.

### Tier A
- PDF text extraction.
- OCR.
- Local translation for routine clauses.
- Basic confidence scoring.

### Tier B
- Groq for high-quality translation, adjudication, and difficult clauses.
- Use it only when:
  - OCR confidence is low.
  - Legal clause is high-risk.
  - Local translation disagrees with glossary rules.
  - Source contains handwriting or unusual layout.

### Suggested model policy
- Default translation: `llama-3.3-70b-versatile`.
- Faster fallback: `llama-3.1-8b-instant`.
- Always use glossary injection for legal terms.
- Never paraphrase legal roles or obligations.

Groq supports model usage through API key auth in `GROQ_API_KEY` and documented model IDs. [docs.agno](https://docs.agno.com/models/providers/gateways/groq/overview)

***

## 8. Verification Layer

Do not claim 100% accuracy. Instead, implement **confidence-gated verification**.

### Verification rules
- If translation confidence < threshold, flag row.
- If glossary terms are missing or changed, flag row.
- If back-translation diverges materially, flag row.
- If Groq and local model disagree, show warning badge.

### Output flags
- Green: high confidence.
- Amber: review recommended.
- Red: unreadable / manual intervention.

### Prompting
Use strict JSON output for translation steps:
- source text
- translated text
- glossary terms used
- confidence
- warnings

This improves machine parsing and reduces UI ambiguity.

***

## 9. Frontend UX Direction

Use a **Swiss modern system**:
- strong grid.
- generous whitespace.
- light neutral palette.
- crisp typography.
- restrained accent color.
- no flashy gradients.
- no heavy AI-style cards.

### Visual language
- Background: near-white or soft gray.
- Text: charcoal.
- Accent: one disciplined color, like deep blue or muted emerald.
- Borders: thin, subtle.
- Shadows: minimal.
- Motion: fast, precise, almost invisible.

### Layout
- Left: file upload + job status.
- Center: preview pane.
- Right: translation / confidence panel.
- Top: document title, status, download actions.

### Components
- Upload dropzone.
- File metadata card.
- Source preview.
- English preview.
- Confidence badges.
- Clause list.
- Download buttons.
- Error banner.
- Retry button.

***

## 10. UI State Management

Use a predictable state model.

### Client state
- selected file
- upload progress
- active job ID
- preview tabs
- filters
- download state

### Server state
- job status
- extracted blocks
- OCR progress
- translation result
- export links
- warning flags

Use React Query for polling job status and caching responses. Use Zustand only for ephemeral UI state. Keep the translated document in server state, not global client state.

***

## 11. API Design

### Endpoints
- `POST /upload`
- `GET /jobs/{id}`
- `GET /documents/{id}/preview`
- `GET /documents/{id}/translation`
- `GET /documents/{id}/export/pdf`
- `GET /documents/{id}/export/xlsx`

### Response style
Use consistent JSON envelopes:

```json
{
  "ok": true,
  "data": {},
  "error": null
}
```

Errors:

```json
{
  "ok": false,
  "data": null,
  "error": {
    "code": "OCR_FAILED",
    "message": "OCR could not process page 3",
    "details": {}
  }
}
```

***

## 12. Download Outputs

Generate:
- Searchable English PDF.
- Excel file with clause-by-clause rows.
- Optional bilingual review file.
- Optional canonical JSON.

Excel columns:
- clause_id
- source_jp
- translation_en
- confidence
- status
- notes

***

## 13. Edge Cases

Must handle:
- Empty upload.
- Corrupt PDF.
- Password-protected PDF.
- Vertical Japanese text.
- Mixed text and images.
- Tables.
- Hanko/seal noise.
- Handwriting.
- Partial OCR failure.
- Groq timeout.
- Groq rate limits.
- Large files.
- Duplicate uploads.
- Retry after interrupted processing.

For every edge case, fail gracefully and preserve partial output.

***

## 14. UX Error States

Show human-readable messages:
- “This file appears to be password protected.”
- “Page 4 is low confidence and needs review.”
- “Translation is still processing.”
- “Export failed, retrying.”
- “Cloud verification temporarily unavailable, using local fallback.”

Never show raw stack traces in UI.

***

## 15. Code Quality Rules

- Type hints everywhere.
- No business logic inside routes.
- No hardcoded keys.
- No magic constants without config.
- Add docstrings on public functions.
- Separate IO from logic.
- Add unit tests for services.
- Add integration tests for upload-to-export flow.
- Add timeout and retry handling.
- Add structured logging.

***

## 16. Minimal Brand Direction

Use a premium Swiss editorial feel:
- precision over ornament.
- clarity over novelty.
- balanced hierarchy.
- confident spacing.
- calm and reliable.

Think “industrial design for software,” not “AI demo page.”

***

## 17. Claude Implementation Prompt

Use this as the direct build instruction:

```md
Build a Japanese document translation platform with a React + Vite frontend, Shadcn UI, Tailwind, Zustand, React Query, and a FastAPI backend. The app must support direct file upload with no login, preview source and translated document side by side, and export English PDF and Excel files.

Frontend requirements:
- Swiss-modern design system.
- Minimal, high-trust, whitespace-first UI.
- No AI-generic gradients or loud effects.
- Upload panel, document preview, translation panel, download actions.
- Live job polling with clear progress and error states.
- Mobile-responsive but optimized for desktop.

Backend requirements:
- FastAPI with clean service-layer architecture.
- Strict file validation, secure uploads, and structured error responses.
- PDF text extraction first, OCR only where needed.
- AI translation pipeline with glossary enforcement and confidence scoring.
- Groq API integration using `GROQ_API_KEY` from env.
- Default Groq model: `llama-3.3-70b-versatile`.
- Fallback model: `llama-3.1-8b-instant`.
- Verification layer for low-confidence clauses.
- Export endpoints for searchable PDF and Excel.

Engineering rules:
- Follow SOLID principles.
- Use dependency injection and interfaces for AI providers.
- Add retries, timeouts, and graceful degradation.
- Add tests for upload, translation, verification, and export.
- Add structured JSON logging.
- Do not hardcode secrets.
- Do not promise 100% accuracy; expose confidence and warnings.

Data flow:
upload → detect → extract/OCR → normalize → translate → verify → render preview → export.

Design goal:
professional Swiss-style software, elegant and restrained, not visually noisy, with a premium enterprise feel.
```

## 18. Deployment Shape

- Frontend: Netlify.
- Backend: Render.
- Same Git repo, separate folders.
- Set environment variables in each platform.
- Use CORS allow-list for Netlify domain.
- Add an `.env.example` file.

***
