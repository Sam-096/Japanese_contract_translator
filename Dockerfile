# Dockerfile — Hugging Face Spaces deployment (16GB RAM / 2 CPU on the free
# "cpu-basic" tier). This is the FULL-featured build: includes the OCR
# cascade (YomiToku + manga-ocr + CPU torch, ~3-4GB weights) so scanned
# PDFs and raw images work here even though they're rejected on the
# memory-constrained Render deployment — see Dockerfile.render,
# JCT_Backend_v1/app/services/ingest_service.py (LOW_MEMORY_MODE).
#
# Build context is the REPO ROOT (not JCT_Backend_v1/) because the app
# imports the sibling src/jpdoc package.
#
# HF Spaces platform requirements this file exists specifically to satisfy:
#   - must be named exactly `Dockerfile`, at the repo root
#   - the container must listen on 0.0.0.0:7860
#   - recommended (and what HF's own Docker Space templates use): run as a
#     non-root user, not root
FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/*

RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH

WORKDIR $HOME/app

COPY --chown=user pyproject.toml requirements.txt requirements-ocr.txt ./
COPY --chown=user src ./src
COPY --chown=user JCT_Backend_v1/requirements.txt ./backend-requirements.txt

RUN pip install --no-cache-dir --user --upgrade pip \
    && pip install --no-cache-dir --user torch torchvision --index-url https://download.pytorch.org/whl/cpu \
    && pip install --no-cache-dir --user -r requirements.txt \
    && pip install --no-cache-dir --user -r requirements-ocr.txt \
    && pip install --no-cache-dir --user -e . \
    && pip install --no-cache-dir --user -r backend-requirements.txt

COPY --chown=user JCT_Backend_v1 ./JCT_Backend_v1
WORKDIR $HOME/app/JCT_Backend_v1

ENV UPLOAD_DIR=$HOME/app/JCT_Backend_v1/data/uploads \
    OUTPUT_DIR=$HOME/app/JCT_Backend_v1/data/output \
    TEMP_DIR=$HOME/app/JCT_Backend_v1/data/tmp \
    CACHE_DIR=$HOME/app/JCT_Backend_v1/data/cache

EXPOSE 7860
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "7860"]
