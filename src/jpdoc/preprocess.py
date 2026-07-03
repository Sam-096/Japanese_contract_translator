"""Stage 2b — image preprocessing for scanned/photo input.

Deskew, denoise, binarize, and suppress watermark/seal (monsho) bleed so the OCR
models see clean black text. Better input = fewer OCR errors = fewer escalations
to the heavy tier = lower token/compute cost downstream.
"""
from __future__ import annotations

import cv2
import numpy as np


def to_gray(img: np.ndarray) -> np.ndarray:
    if img.ndim == 3:
        return cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    return img


def deskew(gray: np.ndarray) -> np.ndarray:
    """Estimate skew from text pixels and rotate upright."""
    inv = cv2.bitwise_not(gray)
    coords = np.column_stack(np.where(inv > 0))
    if coords.size == 0:
        return gray
    angle = cv2.minAreaRect(coords)[-1]
    angle = -(90 + angle) if angle < -45 else -angle
    if abs(angle) < 0.3:
        return gray
    h, w = gray.shape
    m = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
    return cv2.warpAffine(
        gray, m, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE
    )


def suppress_background(gray: np.ndarray) -> np.ndarray:
    """Remove low-contrast watermark/seal background via morphological division."""
    bg = cv2.morphologyEx(
        gray, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (15, 15))
    )
    norm = cv2.divide(gray, bg, scale=255)
    return norm


def binarize(gray: np.ndarray) -> np.ndarray:
    den = cv2.fastNlMeansDenoising(gray, None, h=10, templateWindowSize=7, searchWindowSize=21)
    return cv2.adaptiveThreshold(
        den, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 11
    )


def clean(img_bgr: np.ndarray) -> np.ndarray:
    """Full preprocessing chain; returns a clean binarized image."""
    g = to_gray(img_bgr)
    g = deskew(g)
    g = suppress_background(g)
    return binarize(g)
