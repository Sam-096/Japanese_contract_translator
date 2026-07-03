"""Column-aware spatial sort — prevents multi-column/split-table interlacing.

The problem this solves
------------------------
A naive reading-order sort (top-to-bottom, then left-to-right within a row's
y-band) corrupts any page with side-by-side independent content: a
landscape table split across two column groups, or a bilingual document with
a Japanese column and a Vietnamese column at the same y-coordinates. Sorting
by y first interlaces rows from both columns into one stream — row 1 of
column A followed by row 1 of column B, then row 2 of column A, etc. — which
downstream code (translation, layout) then treats as one broken paragraph.

Algorithm
---------
1. Project every box's horizontal span (x0, x1) onto the x-axis.
2. Sort spans by x0 and merge adjacent/overlapping ones into column *bands*:
   two spans merge if the gap between them is <= `gap_threshold` (normalized
   width). This is a single left-to-right sweep, O(n log n) for the sort
   plus O(n) for the merge — it does not need a 2D grid.
3. Assign each original box to the column band whose x-range contains the
   box's horizontal center (ties broken by nearest band center). A box is
   assigned once, even if it happens to straddle a column boundary — using
   its center rather than its full span avoids a wide box in one column
   falsely bridging two bands together after the fact.
4. Within each band, sort boxes top-to-bottom (y0), then left-to-right (x0)
   for ties on the same line.
5. Concatenate bands left-to-right. Column 0's content — fully sorted top to
   bottom — precedes all of Column 1's content, etc.

`gap_threshold` is the minimum normalized horizontal whitespace (relative to
page width) that counts as a column boundary. Too small and a single column
with ragged left edges gets fragmented into many fake columns; too large and
two genuinely separate columns get merged back into one, reintroducing the
interlacing bug. 0.03 (3% of page width) is a reasonable default for A4/US
Letter contracts; documents with narrow multi-column grids (e.g. dense
forms) may need a smaller value.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TypeVar

from .schema import BoundingBox

T = TypeVar("T")

_DEFAULT_GAP_THRESHOLD = 0.03


@dataclass
class _Band:
    x0: float
    x1: float
    indices: list[int]

    @property
    def center(self) -> float:
        return (self.x0 + self.x1) / 2.0


def _merge_into_bands(boxes: list[BoundingBox], gap_threshold: float) -> list[_Band]:
    order = sorted(range(len(boxes)), key=lambda i: boxes[i].x0)
    bands: list[_Band] = []
    for i in order:
        box = boxes[i]
        if bands and box.x0 <= bands[-1].x1 + gap_threshold:
            bands[-1].x1 = max(bands[-1].x1, box.x1)
            bands[-1].indices.append(i)
        else:
            bands.append(_Band(x0=box.x0, x1=box.x1, indices=[i]))
    return bands


def _assign_to_nearest_band(boxes: list[BoundingBox], bands: list[_Band]) -> list[int]:
    """Return, per box index, which band index (0..len(bands)-1) it belongs to."""
    assignment = [0] * len(boxes)
    for band_idx, band in enumerate(bands):
        for i in band.indices:
            assignment[i] = band_idx
    # Re-check by center distance in case the merge-sweep placed a box in a
    # band via its span overlap but a later, wider box shifted that band's
    # range far from this box's own center.
    for i, box in enumerate(boxes):
        c = box.center_x
        if bands[assignment[i]].x0 - 1e-9 <= c <= bands[assignment[i]].x1 + 1e-9:
            continue
        nearest = min(range(len(bands)), key=lambda b: abs(bands[b].center - c))
        assignment[i] = nearest
    return assignment


def assign_columns(
    boxes: list[BoundingBox], gap_threshold: float = _DEFAULT_GAP_THRESHOLD
) -> list[int]:
    """Return, per input box, the 0-indexed column band it falls in
    (0 = leftmost column). Does not reorder `boxes`.
    """
    if not boxes:
        return []
    bands = _merge_into_bands(boxes, gap_threshold)
    bands.sort(key=lambda b: b.x0)
    return _assign_to_nearest_band(boxes, bands)


def spatial_sort(
    items: list[T],
    box_getter,
    gap_threshold: float = _DEFAULT_GAP_THRESHOLD,
) -> list[T]:
    """Sort arbitrary items by column (left-to-right), then top-to-bottom
    within each column, then left-to-right for ties on the same line.

    `box_getter(item) -> BoundingBox` decouples this from any specific
    payload type (raw dicts, TextBlock, PyMuPDF word tuples, ...).
    """
    boxes = [box_getter(item) for item in items]
    column_of = assign_columns(boxes, gap_threshold)

    indexed = list(range(len(items)))
    indexed.sort(key=lambda i: (column_of[i], boxes[i].y0, boxes[i].x0))
    return [items[i] for i in indexed]
