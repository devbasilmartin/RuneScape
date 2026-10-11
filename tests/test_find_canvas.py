import json
import subprocess
from pathlib import Path

import cv2
import numpy as np
import pytest

from skillbot.layout import CANVAS_H, CANVAS_W
from skillbot.screen import FRAME_MIN, frame_points, match_frame, sample_frame, window_rect

from fakes import TREE, blank, put_item

REAL = Path(__file__).parent / "data" / "fixed_canvas_real.png"


def desktop(origin=(212, 61), seed=0, canvas=None):
    """A 1280x800 Ubuntu desktop with a RuneLite window: title bar, the fixed-mode canvas
    and the sidebar."""
    rng = np.random.default_rng(seed)
    img = np.full((800, 1280, 3), (48, 10, 36), np.uint8)
    x, y = origin
    img[y - 40:y - 2, x - 2:x + CANVAS_W + 30] = (245, 245, 245)        # title bar
    if canvas is None:
        canvas = blank()
        canvas[4:338, 4:516] = rng.integers(40, 160, (334, 512, 3))      # the 3D view
        canvas[:, 516:520] = rng.integers(20, 60, (CANVAS_H, 4, 3))      # its stone border
        canvas[338:342, :520] = rng.integers(20, 60, (4, 520, 3))
        canvas[:4, :520] = rng.integers(20, 60, (4, 520, 3))
        canvas[:, :4] = rng.integers(20, 60, (CANVAS_H, 4, 3))
        canvas[100:140, 200:260] = TREE
        for i in range(0, 28, 3):
            put_item(canvas, i, "logs")
    img[y:y + CANVAS_H, x:x + CANVAS_W] = canvas
    img[y:y + CANVAS_H, x + CANVAS_W:x + CANVAS_W + 25] = (30, 30, 30)  # sidebar
    return img


def test_frame_match_finds_the_canvas_and_rejects_a_wrong_screen():
    img = desktop((400, 137))
    pts = np.array(sample_frame(img[137:137 + CANVAS_H, 400:400 + CANVAS_W]))
    assert match_frame(img, pts) == ((400, 137), 1.0)
    assert match_frame(img, pts, within=(383, 85, 824, 569))[0] == (400, 137)
    assert match_frame(desktop((100, 60), seed=1), pts)[1] < FRAME_MIN   # another frame
    assert match_frame(np.zeros((400, 600, 3), np.uint8), pts) == (None, 0.0)


@pytest.mark.skipif(not REAL.exists(), reason="no real capture")
def test_shipped_frame_finds_a_real_client():
    """fixed_frame.json against a real client's canvas (cut at the bottom as captured)."""
    canvas = cv2.imread(str(REAL))[..., ::-1]
    img = np.full((1080, 1920, 3), (88, 34, 63), np.uint8)
    img[134:134 + canvas.shape[0], 833:833 + canvas.shape[1]] = canvas
    pts = frame_points()
    assert match_frame(img, pts, within=(819, 85, 824, 569)) == ((833, 134), 1.0)
    origin, share = match_frame(img, pts)
    assert origin == (833, 134) and share == 1.0


def test_window_rect_from_xwininfo():
    def run(cmd, **kw):
        if cmd[1] == "search":
            out = "11\n22\n"
        elif cmd[-1] == "11":          # a small window that also matches the name
            out = ("  Absolute upper-left X:  5\n  Absolute upper-left Y:  5\n"
                   "  Width: 300\n  Height: 200\n")
        else:
            out = ("xwininfo: Window id: 0x22 \"RuneLite - megaman19999\"\n\n"
                   "  Absolute upper-left X:  819\n  Absolute upper-left Y:  85\n"
                   "  Relative upper-left X:  0\n  Relative upper-left Y:  0\n"
                   "  Width: 824\n  Height: 569\n")
        return subprocess.CompletedProcess(cmd, 0, stdout=out)

    assert window_rect(run=run) == (819, 85, 824, 569)
    assert window_rect(run=lambda *a, **k: subprocess.CompletedProcess(a, 0, stdout="")) \
        is None
