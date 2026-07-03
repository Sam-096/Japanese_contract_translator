# Backend image for cloud deployment (development.md §18). Build context is the
# REPO ROOT (not JCT_Backend_v1/) because the app imports the sibling src/jpdoc package.
#
# NOTE: this image is heavy — CPU torch + yomitoku + manga-ocr weights (~3-4GB).
# Use at least a "Standard" Render instance and expect a multi-minute cold build.
# Local Ollama is NOT available in this container; translation falls back to
# Groq automatically (see app/services/translate_service.py) as long as
# GROQ_API_KEY is set.
FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    poppler-utils \
    libgl1 \
    libglib2.0-0 \
    fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /srv

COPY pyproject.toml requirements.txt ./
COPY src ./src
COPY JCT_Backend_v1/requirements.txt ./backend-requirements.txt

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir torch torchvision --index-url https://download.pytorch.org/whl/cpu \
    && pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir -e . \
    && pip install --no-cache-dir -r backend-requirements.txt

COPY JCT_Backend_v1 ./JCT_Backend_v1
WORKDIR /srv/JCT_Backend_v1

ENV UPLOAD_DIR=/srv/JCT_Backend_v1/data/uploads \
    OUTPUT_DIR=/srv/JCT_Backend_v1/data/output \
    TEMP_DIR=/srv/JCT_Backend_v1/data/tmp \
    CACHE_DIR=/srv/JCT_Backend_v1/data/cache

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
