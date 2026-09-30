"""Pixel-level detection: highlight colors, blobs and templates. Images are RGB uint8."""
from dataclasses import dataclass

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
        blobs.append(Blob(int(x) + ox, int(y) + oy, int(w), int(h), area))
    blobs.sort(key=lambda b: b.area, reverse=True)
    return blobs


def nearest(blobs: list[Blob], point) -> Blob | None:
    if not blobs:
        return None
    px, py = point
    return min(blobs, key=lambda b: (b.center[0] - px) ** 2 + (b.center[1] - py) ** 2)


def match_score(img: np.ndarray, template: np.ndarray) -> tuple[float, tuple[int, int]]:
    """Best normalized-correlation match of ``template`` inside ``img``."""
    if img.shape[0] < template.shape[0] or img.shape[1] < template.shape[1]:
        return 0.0, (0, 0)
    res = cv2.matchTemplate(img[..., :3], template[..., :3], cv2.TM_CCOEFF_NORMED)
    _, score, _, loc = cv2.minMaxLoc(res)
    return float(score), loc


def load_png(path) -> np.ndarray:
    bgr = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if bgr is None:
        raise FileNotFoundError(path)
    return cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)


def save_png(path, img: np.ndarray) -> None:
    cv2.imwrite(str(path), cv2.cvtColor(img[..., :3], cv2.COLOR_RGB2BGR))
