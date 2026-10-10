"""Pixel-level detection: highlight colors and blobs. Images are RGB uint8."""
from dataclasses import dataclass, field

import cv2
import numpy as np

from .layout import Rect


@dataclass(frozen=True)
class Blob:
    x: int
    y: int
    w: int
    h: int
    area: int
    # The highlight's outline as one closed polygon in canvas coordinates (even-odd rule:
    # holes are joined to the outside by a zero-width cut). Empty if not computed.
    polygon: tuple = field(default=(), compare=False)

    @property
    def center(self) -> tuple[int, int]:
        return self.x + self.w // 2, self.y + self.h // 2

    @property
    def rect(self) -> Rect:
        return Rect(self.x, self.y, self.w, self.h)


def color_mask(img: np.ndarray, rgb, tol: int) -> np.ndarray:
    diff = np.abs(img[..., :3].astype(np.int16) - np.asarray(rgb, dtype=np.int16))
    return np.all(diff <= tol, axis=-1)


def find_blobs(img: np.ndarray, rgb, tol: int, region: Rect | None = None,
               min_area: int = 15) -> list[Blob]:
    """Find groups of pixels matching ``rgb``, largest first.

    RuneLite highlights are thin outlines, so the mask is dilated first to join an
    outline into a single blob whose bounding box covers the whole object.
    """
    ox, oy = (region.x, region.y) if region else (0, 0)
    sub = region.crop(img) if region else img
    mask = color_mask(sub, rgb, tol).astype(np.uint8)
    pixel_counts = mask.copy()
    mask = cv2.dilate(mask, np.ones((7, 7), np.uint8))
    n, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    blobs = []
    for i in range(1, n):
        area = int(pixel_counts[labels == i].sum())
        if area < min_area:
            continue
        x, y, w, h, _ = stats[i]
        pixels = (labels[y:y + h, x:x + w] == i) & (pixel_counts[y:y + h, x:x + w] > 0)
        poly = tuple((px + int(x) + ox, py + int(y) + oy) for px, py in outline_polygon(pixels))
        blobs.append(Blob(int(x) + ox, int(y) + oy, int(w), int(h), area, poly))
    blobs.sort(key=lambda b: b.area, reverse=True)
    return blobs


OUTLINE_STROKE_PX = 3      # thicker than this (half-width) and a highlight counts as filled
MAX_POLYGON_POINTS = 40


def _simplify(contour) -> list:
    """Fewer points, same shape: Douglas-Peucker with a growing tolerance."""
    eps = 1.0
    while True:
        approx = cv2.approxPolyDP(contour, eps, True).reshape(-1, 2)
        if len(approx) <= MAX_POLYGON_POINTS or eps > 8:
            return [tuple(map(int, p)) for p in approx]
        eps *= 1.5


def outline_polygon(pixels: np.ndarray) -> list:
    """One highlight's pixels (a boolean mask) → a polygon of the clickable shape.

    - A thin outline (NPC Indicators / Object Markers outline or hull mode) traces the
      model's silhouette: its outer edge is the shape, the inside counts as filled. Gaps in
      the stroke are closed first; if it still doesn't enclose anything, the convex hull.
    - A filled highlight keeps its shape, holes included, so an aim point never lands in
      a hole or in the notch of an L.
    """
    mask = pixels.astype(np.uint8)
    if not mask.any():
        return []
    pad = 4
    mask = cv2.copyMakeBorder(mask, pad, pad, pad, pad, cv2.BORDER_CONSTANT, value=0)
    thickness = cv2.distanceTransform(mask, cv2.DIST_L2, 3).max()
    if thickness <= OUTLINE_STROKE_PX:
        closed = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
        contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        outer = max(contours, key=cv2.contourArea)
        filled = np.zeros_like(mask)
        cv2.drawContours(filled, [outer], -1, 1, thickness=cv2.FILLED)
        inside = int((filled & (1 - closed)).sum())
        if inside < 0.2 * int(filled.sum()):               # an open stroke: no inside
            outer = cv2.convexHull(cv2.findNonZero(mask))
        points = _simplify(outer)
    else:
        contours, hierarchy = cv2.findContours(mask, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
        outer_i = max((i for i in range(len(contours)) if hierarchy[0][i][3] < 0),
                      key=lambda i: cv2.contourArea(contours[i]))
        points = _simplify(contours[outer_i])
        for i in range(len(contours)):
            if hierarchy[0][i][3] == outer_i and cv2.contourArea(contours[i]) >= 4:
                hole = _simplify(contours[i])
                if len(hole) >= 3:
                    # cut in from the outer start point and back out along the same line
                    points = points + [points[0]] + hole + [hole[0]]
    if len(points) < 3:
        return []
    return [(int(px) - pad, int(py) - pad) for px, py in points]


def nearest(blobs: list[Blob], point) -> Blob | None:
    if not blobs:
        return None
    px, py = point
    return min(blobs, key=lambda b: (b.center[0] - px) ** 2 + (b.center[1] - py) ** 2)


def load_png(path) -> np.ndarray:
    bgr = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if bgr is None:
        raise FileNotFoundError(path)
    return cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)


def save_png(path, img: np.ndarray) -> None:
    cv2.imwrite(str(path), cv2.cvtColor(img[..., :3], cv2.COLOR_RGB2BGR))
