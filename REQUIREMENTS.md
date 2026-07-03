# Reliable Japanese → English Document Pipeline — Requirements & Architecture

**Status:** Phase 1 design locked · **Date:** 2026-06-27
**Author role:** AI architecture spec for a privacy-conscious Japanese contract/policy transcription + translation pipeline.

---

## 0. Executive summary

Take Japanese **documents, scanned images, and PDFs** (contracts and policy material,
including tables, seals/hanko, and some handwriting) and produce a **reliable, searchable,
human-readable English output file**. Phase 2 adds a Q&A dialogue over the processed document.

Everything uses **open-source models** runnable locally. The system is deliberately split
into two tiers because of the host hardware (see §2):

- **Tier A (local, CPU, ships now):** ingestion → OCR/transcription cascade → confidence
  flagging → structured intermediate → light translation → searchable output file.
- **Tier B (heavy, GPU, designed-now/wired-later):** VLM handwriting recovery, 12–14B
  legal-grade reasoning/translation, and Phase-2 RAG Q&A. Implemented as a **stable
  interface** that Tier A calls; the implementation is filled in when GPU is available.

**Primary constraints:** accuracy first, then token/compute efficiency. See §7 for the
explicit token-reduction measures.

---

## 1. Goals & non-goals

### In scope (Phase 1)
- Accept: digital PDFs (text layer), scanned PDFs / photos, handwritten content, and
  layout elements (tables, stamps/seals/hanko).
- Produce: one **searchable, understandable English output file** per input
  (Markdown + optional searchable PDF), preserving structure and flagging uncertainty.
- Run the OCR/transcription pipeline **locally on the current laptop (CPU-only)**.

### In scope (Phase 2)
- Dialogue box to ask questions about an uploaded/processed document, answered in English.
- **Vector-less RAG** (see §6) — no embedding database required.

### Non-goals (for now)
- A polished web UI (the Next.js split-view in the appended external plan is a later app phase).
- Legally binding certified translation (output is decision-support, always human-reviewed).
- Running 12–14B models or vLLM on the current laptop (physically not feasible — see §2).

---

## 2. Hardware reality (verified on host, 2026-06-27)

| Resource | Measured | Implication |
|---|---|---|
| GPU | NVIDIA MX130, **2 GB** + Intel UHD | **Not usable** for LLM/VLM inference |
| RAM | 23.8 GB total, ~10 GB free | OK for CPU OCR + a 3B quantized LLM, **not** 12B |
| CPU | i5-10210U, 4C/8T @ 1.6 GHz | CPU inference is slow: plan around it |
| Disk free | ~43 GB | Tight — keep model footprint small; one LLM at a time |
| Python | 3.11.2 + pip | Good |

**Consequence (this is the key architectural decision):** The appended external plan
(PLaMo-2.1-VL, Shisa 12–14B, vLLM, dual RTX 4090) **cannot run on this machine.** vLLM
requires CUDA GPUs; a 12B model in 4-bit needs ~7–8 GB just for weights and would produce
~1–3 tokens/sec on this CPU (minutes per page). We therefore adopt the **two-tier split**.
Decision (user, 2026-06-27): **build Tier A now; Tier B is a documented interface wired up
later when GPU access exists.** Privacy: cloud GPU acceptable during dev with sample docs;
air-gapped self-hosting for production.

---

## 3. Pipeline architecture (Tier A — local)

```
                 ┌─────────────────────────────────────────────────────────┐
  input file ──▶ │ 1. INGEST & CLASSIFY                                     │
 (pdf/img)       │    detect: digital-PDF? scanned? image? → route          │
                 └───────────────┬─────────────────────────────────────────┘
                                 │
              digital text layer │                 image / scanned
                 ┌───────────────▼──────┐      ┌────────────▼─────────────────┐
                 │ 2a. PDF TEXT EXTRACT │      │ 2b. PREPROCESS               │
                 │     (PyMuPDF)        │      │  deskew, denoise, binarize,  │
                 │  100% accurate, free │      │  watermark/seal suppression  │
                 └───────────┬──────────┘      └────────────┬─────────────────┘
                             │                              │
                             │              ┌───────────────▼───────────────┐
                             │              │ 3. OCR CASCADE (accuracy-ord.) │
                             │              │  (i)   YomiToku  (primary, JP, │
                             │              │        layout+tables)          │
                             │              │  (ii)  manga-ocr (fallback /   │
                             │              │        hard lines)             │
                             │              │  (iii) per-line confidence;    │
                             │              │        low → [?]/[UNREADABLE]  │
                             │              │  (iv)  HANDWRITING → Tier B VLM │
                             │              │        stub (flag for later)   │
                             │              └───────────────┬───────────────┘
                             │                              │
                 ┌───────────▼──────────────────────────────▼───────────────┐
                 │ 4. STRUCTURED INTERMEDIATE (canonical JSON)               │
                 │    blocks, reading order, tables, seals, bbox, conf, lang │
                 │    — single source of truth, medium-independent           │
                 └───────────────┬──────────────────────────────────────────┘
                                 │
                 ┌───────────────▼──────────────────────────────────────────┐
                 │ 5. TRANSLATE (JP→EN), glossary-driven                     │
                 │    Tier A: small local LLM (Ollama qwen2.5:3b) +          │
                 │            legal glossary injection (甲/乙=Party A/B, etc.)│
                 │    Tier B (later): 12–14B Shisa/ELYZA, multi-pass audit   │
                 └───────────────┬──────────────────────────────────────────┘
                                 │
                 ┌───────────────▼──────────────────────────────────────────┐
                 │ 6. RENDER OUTPUT                                          │
                 │    • <name>.en.md   (searchable, structured)             │
                 │    • <name>.bilingual.md (JP|EN side-by-side, review)    │
                 │    • <name>.intermediate.json (audit trail)              │
                 │    • optional searchable PDF                             │
                 └──────────────────────────────────────────────────────────┘
```

### Reliability is enforced by, in order:
1. **Never OCR extractable text** (PDF text layer first).
2. **Japanese-specific OCR** (YomiToku) instead of generic Tesseract — handles vertical
   text, tables, layout, mixed kanji/kana.
3. **Cascade with confidence**: hard lines fall back to manga-ocr; still-low-confidence
   lines are explicitly marked `[?]`/`[UNREADABLE_KANJI]` (adopted from the external plan's
   defensive design) rather than silently guessed.
4. **Glossary-locked translation** so legal terms (甲/乙 = Party A / Party B, 甲方/乙方,
   印鑑/実印, 連帯保証 = joint & several guarantee, 自動更新 = automatic renewal) are never
   paraphrased away.
5. **Human-in-the-loop**: bilingual review file + amber-flag rows for `[?]`.

---

## 4. Recommended models

### Tier A — runs on THIS laptop (CPU), ships now
| Stage | Model / tool | Why | Footprint |
|---|---|---|---|
| PDF text | **PyMuPDF (fitz)** | exact, zero-cost extraction | tiny |
| Primary OCR | **YomiToku** | JP-native OCR: detection+recognition+layout+tables, CPU-capable | ~hundreds MB |
| Fallback OCR | **manga-ocr** | robust on stylized/handwritten-ish lines | ~400 MB |
| Generic fallback | **Tesseract `jpn`/`jpn_vert`** (optional) | last-resort, vertical text | small |
| Local translate/reason | **Ollama → `qwen2.5:3b-instruct`** | strong multilingual incl. JP, runs in ~3–4 GB on CPU | ~2–3 GB |

### Tier B — designed now, wired later (GPU: HF Endpoints / RunPod / on-prem)
| Stage | Model | Why |
|---|---|---|
| VLM handwriting / hard pages | **Qwen2.5-VL-7B** (or PLaMo-2.1-VL per external plan) | reads handwriting + layout + suppresses watermark/seal noise |
| Legal reasoning & translation | **Shisa V2.1 (12B/14B)** or **ELYZA-Llama-3-JP** | JP legal fluency; multi-pass indemnity/renewal audit |
| Phase-2 Q&A | same reasoning model + **vector-less RAG** (§6) | answer questions in English over the doc |

> The external-LLM plan (appended in §9) targets Tier B. We keep its model picks as the
> Tier-B recommendation and its defensive `[?]` flagging, but reject vLLM/dual-4090 as the
> *current* baseline because it does not run on the host.

---

## 5. Output contract (the deliverable file)

For input `doc.pdf` the pipeline writes to `output/doc/`:
- `doc.en.md` — primary English output, structured & searchable (headings, tables, lists).
- `doc.bilingual.md` — JP source ‖ EN, for review; `[?]` rows flagged.
- `doc.intermediate.json` — canonical structured data (blocks, bbox, confidence, lang, seals).
- `doc.en.pdf` *(optional)* — searchable PDF with text layer.

All English output is **searchable** (plain-text-backed) and **understandable**
(structure + glossary-consistent terminology + uncertainty flags).

---

## 6. Phase 2 — Vector-less RAG (per your preference)

No embedding store. Because contracts are bounded documents, we use **structure-aware
retrieval over the intermediate JSON**:
1. The document is already segmented into labeled blocks/sections (clauses, tables, parties).
2. Retrieval = **BM25 / keyword + section-heading match** (e.g. `rank_bm25`) over those blocks,
   optionally re-ranked by the LLM. No vector DB, no GPU embedding step.
3. The question + only the **top-k relevant blocks** (not the whole doc) are sent to the
   reasoning model → answer in English with clause citations.

This keeps Phase 2 (a) open-source, (b) light, (c) **token-efficient** (we never stuff the
whole contract into the prompt), and (d) explainable (answers cite block IDs).

---

## 7. Constraints & token/compute-efficiency measures

**Accuracy is the first constraint; efficiency is the second.** Concrete measures:

1. **Skip OCR on digital PDFs** — the single biggest savings; no model tokens at all.
2. **Page/region gating** — only send *low-confidence* regions to the heavier OCR/VLM, never
   whole pages by default.
3. **Translate the structured intermediate, not raw OCR dumps** — deduplicated, no repeated
   boilerplate, stable ordering.
4. **Chunk by clause with overlap caps** — bounded prompt size; never feed an entire contract
   to the LLM in one call.
5. **Glossary as a fixed system preamble + prompt caching** — the legal term map is sent once
   and cached, not re-paid per clause.
6. **Vector-less RAG retrieves top-k blocks only** (§6) — Phase-2 queries touch a fraction of
   the document.
7. **Cache by content hash** — identical page/clause already processed ⇒ reuse, zero new tokens.
8. **Local small model for routine translation**, escalate to Tier-B 12–14B only for
   flagged/high-risk clauses (indemnity, auto-renewal, guarantees).
9. **Batch & stream**: process pages concurrently where CPU allows; stream output so long jobs
   are observable (SSE later).

> **Measure you should take now:** keep one Ollama model resident at a time (disk + RAM are
> tight), and prefer the digital-PDF path for any document that has a text layer — instruct
> document owners to provide native PDFs when they exist.

---

## 8. Build phases (reconciled with host reality)

- **Phase 1a (now):** ingest + classify + PDF extract + YomiToku/manga-ocr cascade +
  intermediate JSON + confidence flagging. *Deliverable: reliable JP transcription file.*
- **Phase 1b:** glossary-driven local translation (Ollama qwen2.5:3b) → English output file.
- **Phase 1c:** searchable PDF render + bilingual review file.
- **Phase 2:** vector-less RAG Q&A interface.
- **Tier B integration (when GPU available):** swap the VLM and reasoning stubs for real
  Qwen2.5-VL-7B + Shisa/ELYZA; optional multi-pass legal audit.
- **App phase (later):** FastAPI + Celery/Redis backend and the Next.js split-view UI from §9.

---

## 9. Appendix — External LLM plan (captured verbatim, scoped as Tier B / app phase)

The following strategic plan was provided by another model. It is **retained as the Tier-B
and product/app vision**, with the explicit caveat that its infrastructure (vLLM,
PLaMo-2.1-VL, Shisa 12–14B, dual RTX 4090) is **not runnable on the current laptop** and is
deferred to the GPU/heavy tier. Its strongest reusable ideas — JP-native VLM for handwriting,
watermark/seal suppression via prompt, `[?]`/`[UNREADABLE_KANJI]` defensive flagging,
multi-pass legal audit, and air-gapped Docker deployment for production — are adopted above.

### Part 1 — Strategic context
- **Vision:** enterprise-grade, privacy-first document workspace for multinationals, law
  firms, and real-estate investors in Japan; convert messy handwritten Japanese agreements
  into accurate, legally sound English with zero data leaks.
- **Problem:** (1) much JP business contracting is still paper with cursive/handwritten kanji
  revisions; (2) traditional vision models fail on low-contrast JP text over textured security
  paper / watermark (monshō) seals; (3) Western-centric MT misreads JP legal terms
  (甲/乙 relationships, hanko contexts) → legal liability; (4) data sovereignty: JP financial/
  legal institutions can't send confidential contracts to foreign-hosted APIs.
- **Core solution:** self-hosted, air-gapped web platform combining JP-designed
  vision-language models with domestic reasoning models in a real-time side-by-side workspace.

### Part 2 — Roadmap (6-week MVP, as provided)
- **Wk 1–2 — Core AI & backend:** FastAPI + Celery + Redis loops; local deploy of PLaMo-2.1-VL
  & Shisa V2.1 via Ollama/vLLM.
- **Wk 3–4 — Split-view frontend:** Next.js 15 + Tailwind + shadcn/ui; real-time upload canvas
  with SSE status streaming.
- **Wk 5–6 — Edge-case hardening & launch:** multi-pass JP legal audit prompt validation;
  Dockerize for air-gapped deployment in Japan.

  - *Phase 1 (Wk1–2):* FastAPI uploads → Celery worker; vLLM running PLaMo-2.1-VL & Shisa V2.1
    on one GPU node (FP16/INT4); prompt template for background-noise suppression.
  - *Phase 2 (Wk3–4):* Next.js dashboard, drag-and-drop ingestion; HTML5 canvas zoom/pan
    preview with handwriting highlights; SSE progress tickers.
  - *Phase 3 (Wk5–6):* multi-pass legal auditing with warning panels (indemnity, auto-renewal);
    PostgreSQL audit logs + side-by-side editing; Docker Compose (Next.js, FastAPI, Celery,
    Redis, vLLM) for AWS/GCP Tokyo or on-prem.

### Part 3 — Risk register (as provided)
- **High GPU cost** → run smaller optimized models (Shisa V2.1 12B/14B) or 4-bit quantized
  large models on consumer hardware (e.g. dual RTX 4090) during prototyping.
- **Unreadable handwriting** → design defensively: prompt the vision model to inject visible
  `[?]` / `[UNREADABLE_KANJI]` into the text layout; frontend highlights that row in amber for
  manual review/patch.
