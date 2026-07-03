"""Pydantic data model for the JCT_Backend_v2 pipeline.

Coordinate convention
----------------------
`BoundingBox` coordinates are normalized to [0, 1], relative to the *page's*
width/height (x measured from the left edge, y from the top edge — matching
PyMuPDF's page coordinate space, not PDF's bottom-left origin). Normalizing
here — instead of storing raw points — means a `TextBlock` extracted from a
source page can be replayed onto any output canvas size (a different DPI
raster, an HTML page at a different CSS pixel size, etc.) by multiplying
through that canvas's own width/height at render time, without re-deriving
geometry from the original PDF.
"""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field, model_validator


class BoundingBox(BaseModel):
    """Axis-aligned box, normalized to [0, 1] against page width/height."""

    x0: float = Field(ge=0.0, le=1.0)
    y0: float = Field(ge=0.0, le=1.0)
    x1: float = Field(ge=0.0, le=1.0)
    y1: float = Field(ge=0.0, le=1.0)

    @model_validator(mode="after")
    def _check_ordering(self) -> "BoundingBox":
        if self.x1 <= self.x0 or self.y1 <= self.y0:
            raise ValueError(
                f"degenerate bounding box (x1<=x0 or y1<=y0): {self.x0},{self.y0},{self.x1},{self.y1}"
            )
        return self

    @property
    def width(self) -> float:
        return self.x1 - self.x0

    @property
    def height(self) -> float:
        return self.y1 - self.y0

    @property
    def center_x(self) -> float:
        return (self.x0 + self.x1) / 2.0

    @property
    def center_y(self) -> float:
        return (self.y0 + self.y1) / 2.0

    def to_points(self, page_width_pt: float, page_height_pt: float) -> tuple[float, float, float, float]:
        """Denormalize to absolute PDF points for a given page size."""
        return (
            self.x0 * page_width_pt,
            self.y0 * page_height_pt,
            self.x1 * page_width_pt,
            self.y1 * page_height_pt,
        )


class FontStyle(str, Enum):
    NORMAL = "normal"
    BOLD = "bold"
    ITALIC = "italic"
    BOLD_ITALIC = "bold_italic"


class TextBlock(BaseModel):
    """One extracted text element and everything the pipeline attaches to it
    as it moves through masking -> translation -> rendering. Fields beyond
    `id`/`raw_text`/`bounding_box` are populated progressively — a freshly
    extracted block has only those three set.
    """

    id: str
    raw_text: str
    masked_text: str | None = None
    translated_text: str | None = None
    token_map: dict[str, str] = Field(default_factory=dict)
    bounding_box: BoundingBox
    font_size: float = Field(gt=0)
    font_style: FontStyle = FontStyle.NORMAL
    column_index: int = 0


class DocumentCanvas(BaseModel):
    """One page's worth of positioned text, ready to compile onto a
    background. `width_pt`/`height_pt` are the canvas's own point dimensions
    (independent of whatever page size the source blocks were normalized
    against) — `TextBlock.bounding_box.to_points()` uses these to place text.
    """

    page_number: int = Field(ge=1)
    width_pt: float = Field(gt=0)
    height_pt: float = Field(gt=0)
    background_svg_path: str | None = None
    blocks: list[TextBlock] = Field(default_factory=list)
