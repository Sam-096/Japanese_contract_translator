"""Helpers to turn PDF pages / image files into BGR numpy arrays for OCR."""
from __future__ import annotations

from pathlib import Path

import cv2
import fitz
import numpy as np

from .config import RASTER_DPI


def image_file_to_bgr(path: Path) -> np.ndarray:
    img = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError(f"Could not read image: {path}")
    return img


def pdf_page_to_bgr(path: Path, page_number: int, dpi: int = RASTER_DPI) -> np.ndarray:
    """Rasterise a single 1-based PDF page to a BGR array (only pages that need OCR)."""
    with fitz.open(path) as pdf:
        page = pdf[page_number - 1]
        pix = page.get_pixmap(dpi=dpi)
        arr = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.h, pix.w, pix.n)
        if pix.n == 4:
            arr = cv2.cvtColor(arr, cv2.COLOR_RGBA2BGR)
        elif pix.n == 3:
            arr = cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)
        else:
            arr = cv2.cvtColor(arr, cv2.COLOR_GRAY2BGR)
        return arr
