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
