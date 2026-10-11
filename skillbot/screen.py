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


# fixed mode: the 3D view is 512x334 at (4, 4), framed by the stone interface
VIEW_X, VIEW_Y, VIEW_W, VIEW_H = 4, 4, 512, 334


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


# ---- matching the fixed-mode frame's artwork --------------------------------------------
# The stone border around the 3D view is the same picture every time. fixed_frame.json
# holds points sampled from it on a real client: [dx, dy, r, g, b] relative to the canvas
# origin. `calibrate --origin X Y` re-samples them from your screen (data/frame.json).
FRAME_FILE = Path(__file__).resolve().parent / "fixed_frame.json"
FRAME_TOL = 12           # per channel
FRAME_MIN = 0.85         # share of points that must match


def frame_points(data_dir: Path | None = None) -> np.ndarray:
    own = Path(data_dir) / "frame.json" if data_dir else None
    path = own if own and own.exists() else FRAME_FILE
    return np.array(json.loads(path.read_text()), dtype=np.int32)


def sample_frame(canvas: np.ndarray) -> list:
    """Points on the 3D view's stone border, from a canvas grabbed at the right origin."""
    pts = []
    x1, y1 = VIEW_X + VIEW_W, VIEW_Y + VIEW_H
    for dy in range(VIEW_Y, y1, 3):
        for dx in (0, 1, 2, 3, x1, x1 + 1, x1 + 2, x1 + 3):
            pts.append([dx, dy, *map(int, canvas[dy, dx, :3])])
    for dx in range(VIEW_X, x1, 6):
        for dy in (0, 1, 2, 3, y1, y1 + 1, y1 + 2, y1 + 3):
            pts.append([dx, dy, *map(int, canvas[dy, dx, :3])])
    return pts


def match_frame(rgb: np.ndarray, pts: np.ndarray, within: tuple | None = None,
                sample: int = 300) -> tuple[tuple[int, int] | None, float]:
    """The canvas origin where the frame's points match best, and the share matched.
    ``within`` limits the search to canvases inside that rectangle (x, y, w, h)."""
    H, W = rgb.shape[:2]
    span_x, span_y = int(pts[:, 0].max()) + 1, int(pts[:, 1].max()) + 1
    x0, y0, x1, y1 = 0, 0, W - span_x, H - span_y
    if within is not None:
        wx, wy, ww, wh = within
        x0, y0 = max(x0, wx), max(y0, wy)
        x1, y1 = min(x1, wx + ww - CANVAS_W), min(y1, wy + wh - CANVAS_H)
    if x1 < x0 or y1 < y0:
        return None, 0.0
    img = rgb[..., :3].astype(np.int16)

    def counts(points):
        hits = np.zeros((y1 - y0 + 1, x1 - x0 + 1), np.int32)
        for dx, dy, r, g, b in points:
            win = img[y0 + dy:y1 + dy + 1, x0 + dx:x1 + dx + 1]
            hits += ((np.abs(win[..., 0] - r) <= FRAME_TOL) & (np.abs(win[..., 1] - g) <= FRAME_TOL)
                     & (np.abs(win[..., 2] - b) <= FRAME_TOL))
        return hits

    step = max(1, len(pts) // sample)
    coarse = counts(pts[::step]) / len(pts[::step])
    # check the promising origins with every point
    best, best_share = None, 0.0
    for y, x in zip(*np.nonzero(coarse >= coarse.max() - 0.1)):
        ys, xs = y0 + y + pts[:, 1], x0 + x + pts[:, 0]
        share = float((np.abs(img[ys, xs] - pts[:, 2:].astype(np.int16)) <= FRAME_TOL)
                      .all(axis=1).mean())
        if share > best_share:
            best, best_share = (int(x0 + x), int(y0 + y)), share
    return best, best_share
