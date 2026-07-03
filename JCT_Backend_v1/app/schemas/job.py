from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel

JobStatusLiteral = Literal[
    "queued", "processing", "translating", "rendering", "completed", "failed"
]


class UploadResponse(BaseModel):
    document_id: str
    job_id: str
    filename: str


class JobStatusResponse(BaseModel):
    id: str
    document_id: str
    status: JobStatusLiteral
    progress_message: str
    error: Optional[dict] = None
