# Installation — Tier A (local, this laptop)

Windows 11 · Python 3.11 · CPU-only. Run these in **PowerShell** from the project root.

> Disk is tight (~43 GB free). Keep **one** Ollama model resident at a time.

## 1. Create & activate a virtual environment
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
```
If activation is blocked: `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` then retry.

## 2. Install CPU-only PyTorch FIRST (avoids pulling huge CUDA wheels)
```powershell
pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
```

## 3. Install the Tier-A Python dependencies
```powershell
pip install -r requirements.txt
pip install -r requirements-ocr.txt   # YomiToku + manga-ocr — needed to test scanned PDFs/images locally
```

## 4. System binaries (not pip-installable)
- **Poppler**: listed as needed by `pdf2image` for scanned PDFs, but as of the current
  ingest pipeline (`src/jpdoc/raster.py`) rasterization goes through PyMuPDF + OpenCV
  directly — `pdf2image`/Poppler are not actually imported anywhere in the code. Skip
  this unless you've added a code path that uses them.
- **Tesseract** *(optional, only if you enable the generic fallback)*:
  install the UB-Mannheim build, tick the **Japanese** + **Japanese (vertical)** language
  data during setup, then `pip install pytesseract`.

## 5. Install Ollama + pull the small local model (Tier-A translation)
```powershell
# Install Ollama for Windows from https://ollama.com/download , then:
ollama pull qwen2.5:3b-instruct
ollama run qwen2.5:3b-instruct "こんにちは"   # smoke test
```
> `qwen2.5:3b` runs in ~3-4 GB RAM on CPU. Expect modest speed — fine for routine
> translation; escalate hard/legal clauses to Tier B later. Do **not** pull a 12B model here.

## 6. Verify the install
```powershell
python -c "import fitz, cv2, numpy, pydantic, rank_bm25; print('core ok')"
python -c "import manga_ocr; print('manga-ocr ok')"
python -c "import yomitoku; print('yomitoku ok')"
ollama list
```
First run of `manga-ocr` / `yomitoku` downloads model weights (a few hundred MB each) — this
is a one-time download, then it works offline (supports the air-gap requirement).

---

# Installation — Tier B (GPU host ONLY — do NOT run on this laptop)

On a CUDA machine (HF Endpoint / RunPod / Colab / on-prem Tokyo node):
```bash
python -m venv .venv && source .venv/bin/activate
pip install --upgrade pip
# CUDA torch (pick the index matching the host's CUDA, e.g. cu121):
pip install torch --index-url https://download.pytorch.org/whl/cu121
pip install -r requirements-tierB.txt
# then pull models, e.g.:
#   huggingface-cli download Qwen/Qwen2.5-VL-7B-Instruct
#   huggingface-cli download elyza/Llama-3-ELYZA-JP-8B
```

---

# Token / compute efficiency — measures to apply (see REQUIREMENTS.md §7)
1. Always try the **digital-PDF text layer first** — zero OCR/LLM cost.
2. Send only **low-confidence regions** to heavy OCR/VLM, never whole pages by default.
3. Translate the **deduplicated structured JSON**, not raw OCR dumps.
4. **Chunk by clause**; never feed a whole contract in one prompt.
5. Put the **legal glossary in a cached system preamble**, not per-clause.
6. Phase-2 RAG retrieves **top-k blocks only** (vector-less / BM25).
7. **Cache by content hash** — reuse already-processed pages/clauses.
8. Use the **local 3B model for routine** translation; escalate only flagged clauses to Tier B.
