"""Right-click menus, read by the option's word instead of guessed by row number.

A menu opens just below the mouse: a black header, then one row per option, each row's
option ("Talk-to", "Trade", "Tan All") in white and the thing's name in color. The
white text's pixel shape is the same every time, so it only has to be shown once:
`teach-menu "Talk-to,Trade,Teleport"` right-clicks what you hover and remembers each row's
word (data/menu_words.json, with the menu's own background color).

Picking "Teleport" then finds the row whose word looks like that one. A word nobody has
taught falls back to the row number given with it; the menu having fewer rows than that,
or no row with a taught word, closes the menu and fails instead of clicking blind.
"""
import json
import logging
from pathlib import Path

import numpy as np

log = logging.getLogger("skillbot")

FILL = (93, 84, 71)       # the menu's background in the plain client (teach-menu measures it)
FILL_TOL = 10
WHITE = 225               # every channel above this: the option word's white text
ROW_TEXT = 5              # rows of pixels above and below a row's middle to read
MATCH = 0.8               # how alike two words must be (shared white pixels / all)
SEARCH = 260              # how far left/right of the mouse a menu can reach


def first(option: str) -> str:
    """The key for an option: its words, lower case ("Tan All" and "Tan 5" differ)."""
    return " ".join(option.lower().split())


def signature(mask: np.ndarray) -> np.ndarray | None:
    """A row's white text, the option ("Tan All"), cropped tight; None if no white."""
    cols = np.flatnonzero(mask.any(axis=0))
    if not cols.size:
        return None
    word = mask[:, cols[0]:cols[-1] + 1]
    rows = np.flatnonzero(word.any(axis=1))
    return word[rows[0]:rows[-1] + 1]


def likeness(a: np.ndarray, b: np.ndarray) -> float:
    if abs(a.shape[0] - b.shape[0]) > 1 or abs(a.shape[1] - b.shape[1]) > 2:
        return 0.0
    h, w = max(a.shape[0], b.shape[0]), max(a.shape[1], b.shape[1])
    pa = np.zeros((h, w), bool)
    pb = np.zeros((h, w), bool)
    pa[:a.shape[0], :a.shape[1]] = a
    pb[:b.shape[0], :b.shape[1]] = b
    union = (pa | pb).sum()
    return float((pa & pb).sum() / union) if union else 0.0


class MenuBook:
    """Taught words (data/menu_words.json)."""

    def __init__(self, path: Path | None = None):
        self.path = path
        self.words: dict[str, list[np.ndarray]] = {}
        self.fill = FILL
        if path is not None and Path(path).exists():
            raw = json.loads(Path(path).read_text())
            self.fill = tuple(raw.get("fill", FILL))
            for word, shapes in raw.get("words", {}).items():
                self.words[word] = [np.array([[c == "#" for c in r] for r in s], bool)
                                    for s in shapes]

    def save(self) -> None:
        raw = {"fill": list(self.fill), "words": {
            w: [["".join("#" if v else "." for v in r) for r in s] for s in shapes]
            for w, shapes in self.words.items()}}
        Path(self.path).write_text(json.dumps(raw, indent=1))

    def knows(self, word: str) -> bool:
        return first(word) in self.words

    def learn(self, word: str, shape: np.ndarray) -> None:
        shapes = self.words.setdefault(first(word), [])
        if not any(likeness(shape, s) >= 0.98 for s in shapes):
            shapes.append(shape)

    def find(self, word: str, rows: list) -> int | None:
        """The 1-based row whose first word looks most like ``word`` (taught), or None."""
        shapes = self.words.get(first(word), [])
        best, best_row = MATCH, None
        for i, sig in enumerate(rows, 1):
            if sig is None:
                continue
            score = max((likeness(sig, s) for s in shapes), default=0.0)
            if score >= best:
                best, best_row = score, i
        return best_row


def fill_mask(img: np.ndarray, fill, tol: int = FILL_TOL) -> np.ndarray:
    return (np.abs(img.astype(int) - np.array(fill)).max(axis=2) <= tol)


def read_rows(img: np.ndarray, point, header: int, row: int, fill=FILL) -> list:
    """Each menu row's word signature, top to bottom; [] when no menu is open at point."""
    x, y = int(point[0]), int(point[1])
    h, w = img.shape[:2]
    fill_px = fill_mask(img, fill)
    out = []
    i = 0
    while True:
        mid = y + header + row * i + row // 2
        if mid + ROW_TEXT >= h:
            break
        line = fill_px[mid - ROW_TEXT:mid + ROW_TEXT + 1, max(0, x - SEARCH):min(w, x + SEARCH)]
        if line.mean(axis=0).max(initial=0) < 0.5 or not fill_px[mid - ROW_TEXT:mid + ROW_TEXT + 1,
                                                                 max(0, x - 3):x + 4].any():
            break
        left, right = _extent(fill_px[mid - ROW_TEXT:mid + ROW_TEXT + 1], x)
        band = img[mid - ROW_TEXT:mid + ROW_TEXT + 1, left:right + 1]
        out.append(signature((band >= WHITE).all(axis=2)))
        i += 1
    return out


def _extent(band: np.ndarray, x: int) -> tuple[int, int]:
    """Left and right of the menu in a row band: fill columns around x, bridging text."""
    filled = band.any(axis=0)
    w = filled.size
    left = right = x
    gap = 0
    while left - 1 >= 0 and gap < 12:
        left -= 1
        gap = 0 if filled[left] else gap + 1
    left += gap
    gap = 0
    while right + 1 < w and gap < 12:
        right += 1
        gap = 0 if filled[right] else gap + 1
    right -= gap
    return left, right
