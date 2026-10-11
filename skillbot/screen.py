"""Screen capture of the fixed-mode game canvas, on any monitor."""
import json
from pathlib import Path

import numpy as np

from .layout import CANVAS_H, CANVAS_W


class Screen:
    def __init__(self, origin: tuple[int, int]):
        import mss
        self.origin = origin
        self._sct = mss.mss()
        self.heartbeat = None

    @classmethod
    def load(cls, data_dir: Path) -> "Screen":
        path = data_dir / "origin.json"
        if not path.exists():
            raise SystemExit("Not calibrated yet: run `python -m skillbot calibrate` first.")
        return cls(tuple(json.loads(path.read_text())["origin"]))

    def grab(self) -> np.ndarray:
        """Return the canvas as an RGB array of shape (503, 765, 3)."""
        if self.heartbeat:
            self.heartbeat.beat()
        box = {"left": self.origin[0], "top": self.origin[1], "width": CANVAS_W, "height": CANVAS_H}
        bgra = np.asarray(self._sct.grab(box))
        return bgra[..., 2::-1].copy()

    def to_screen(self, pt) -> tuple[int, int]:
        return self.origin[0] + int(pt[0]), self.origin[1] + int(pt[1])

    def to_canvas(self, pt) -> tuple[int, int]:
        return int(pt[0]) - self.origin[0], int(pt[1]) - self.origin[1]


def edge_scores(gray: np.ndarray, w: int = CANVAS_W, h: int = CANVAS_H) -> np.ndarray:
    """For every possible top-left (y, x) of a w x h rectangle, how sharp its weakest side
    is: the mean brightness jump across that side. The game canvas has a sharp edge on all
    four sides (RuneLite's frame, title bar and sidebar around it); the game's own
    interface lines are shorter than a full side, so they score lower."""
    g = gray.astype(np.int32)
    H, W = g.shape
    if H < h + 2 or W < w + 2:
        return np.zeros((0, 0))
    vert = np.zeros_like(g)                      # jump between column x-1 and x
    vert[:, 1:] = np.abs(g[:, 1:] - g[:, :-1])
    horiz = np.zeros_like(g)                     # jump between row y-1 and y
    horiz[1:, :] = np.abs(g[1:, :] - g[:-1, :])
    cv = np.vstack([np.zeros((1, W), np.int64), np.cumsum(vert, axis=0)])
    ch = np.hstack([np.zeros((H, 1), np.int64), np.cumsum(horiz, axis=1)])
    ys, xs = H - h, W - w                        # candidate origins: 1..ys-1, 1..xs-1
    y0 = np.arange(1, ys)[:, None]
    x0 = np.arange(1, xs)[None, :]
    left = (cv[y0 + h, x0] - cv[y0, x0]) / h
    right = (cv[y0 + h, x0 + w] - cv[y0, x0 + w]) / h
    top = (ch[y0, x0 + w] - ch[y0, x0]) / w
    bottom = (ch[y0 + h, x0 + w] - ch[y0 + h, x0]) / w
    out = np.zeros((ys, xs))
    out[1:, 1:] = np.minimum(np.minimum(left, right), np.minimum(top, bottom))
    return out


MIN_EDGE = 8     # mean brightness jump a real canvas edge has, at the least


def find_canvas(rgb: np.ndarray, near: tuple[int, int] | None = None,
                radius: int = 40, within: tuple | None = None) -> tuple[int, int] | None:
    """Top-left (x, y) of the fixed-mode game canvas in a screenshot, or None.
    With ``near``, only origins within ``radius`` pixels of it are considered. With
    ``within`` (a window's x, y, w, h), only canvases inside that window, and of the good
    ones the leftmost, then the lowest: in fixed mode the canvas fills the window's
    bottom-left, with the title bar above it and RuneLite's sidebar to its right, and a
    rectangle shifted onto either of those can score as high as the canvas."""
    gray = rgb[..., :3].astype(np.float32) @ np.array([0.299, 0.587, 0.114], np.float32)
    scores = edge_scores(gray)
    if scores.size == 0:
        return None
    if near is not None:
        mask = np.zeros_like(scores, bool)
        x, y = near
        mask[max(0, y - radius):y + radius + 1, max(0, x - radius):x + radius + 1] = True
        scores = np.where(mask, scores, 0)
    if within is not None:
        wx, wy, ww, wh = within
        mask = np.zeros_like(scores, bool)
        mask[max(0, wy):max(0, wy + wh - CANVAS_H + 1), max(0, wx):max(0, wx + ww - CANVAS_W + 1)] = True
        scores = np.where(mask, scores, 0)
        best = scores.max()
        if best < MIN_EDGE:
            return None
        ys, xs = np.nonzero(scores >= max(MIN_EDGE, 0.5 * best))
        i = int(np.lexsort((-ys, xs))[0])          # smallest x, then largest y
        return int(xs[i]), int(ys[i])
    y, x = np.unravel_index(int(np.argmax(scores)), scores.shape)
    return (int(x), int(y)) if scores[y, x] >= MIN_EDGE else None


def grab_desktop() -> tuple[np.ndarray, tuple[int, int]]:
    """The whole primary monitor as RGB, and its top-left in screen coordinates."""
    import mss
    with mss.mss() as sct:
        mon = sct.monitors[1] if len(sct.monitors) > 1 else sct.monitors[0]
        bgra = np.asarray(sct.grab(mon))
    return bgra[..., 2::-1].copy(), (mon["left"], mon["top"])


def window_rect(name: str = "RuneLite", run=None) -> tuple[int, int, int, int] | None:
    """The client window's content area (x, y, w, h), without the window manager's title
    bar, frame or shadow: xdotool finds the window, xwininfo gives its absolute position
    (xdotool's own geometry can be the frame's). The largest matching window wins."""
    import re
    import subprocess
    run = run or subprocess.run
    try:
        ids = run(["xdotool", "search", "--name", name], capture_output=True, text=True,
                  timeout=5).stdout.split()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    best = None
    for wid in ids:
        try:
            out = run(["xwininfo", "-id", wid], capture_output=True, text=True,
                      timeout=5).stdout
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return None
        vals = {}
        for key, pat in (("x", r"Absolute upper-left X:\s*(-?\d+)"),
                         ("y", r"Absolute upper-left Y:\s*(-?\d+)"),
                         ("w", r"Width:\s*(\d+)"), ("h", r"Height:\s*(\d+)")):
            m = re.search(pat, out)
            if m:
                vals[key] = int(m.group(1))
        if len(vals) < 4:
            continue
        x, y, w, h = vals["x"], vals["y"], vals["w"], vals["h"]
        if w >= CANVAS_W and h >= CANVAS_H and (best is None or w * h > best[2] * best[3]):
            best = (x, y, w, h)
    return best
