import numpy as np

from skillbot.layout import CANVAS_H, CANVAS_W
from skillbot.screen import find_canvas

from fakes import TREE, blank, put_item


def desktop(origin=(212, 61), seed=0):
    """A 1280x800 Ubuntu desktop with a RuneLite window: title bar, the fixed-mode canvas
    (world, interface lines, items) and the sidebar."""
    rng = np.random.default_rng(seed)
    img = np.full((800, 1280, 3), (48, 10, 36), np.uint8)             # Ubuntu purple
    x, y = origin
    img[y - 30:y + CANVAS_H + 2, x - 2:x + CANVAS_W + 240] = (30, 30, 30)  # RuneLite frame
    img[y - 30:y - 2, x - 2:x + CANVAS_W + 240] = (55, 55, 55)            # title bar
    canvas = blank()
    canvas[4:338, 4:512] = rng.integers(40, 160, (334, 508, 3))          # the world
    canvas[:, 512:516] = (20, 20, 20)                                    # interface lines
    canvas[338:342, :512] = (20, 20, 20)
    canvas[100:140, 200:260] = TREE
    for i in range(0, 28, 3):
        put_item(canvas, i, "logs")
    img[y:y + CANVAS_H, x:x + CANVAS_W] = canvas
    img[y:y + CANVAS_H, x + CANVAS_W + 10:x + CANVAS_W + 230] = (70, 70, 75)  # sidebar
    return img


def test_finds_the_canvas_anywhere():
    for origin in ((212, 61), (3, 31), (480, 250)):
        assert find_canvas(desktop(origin)) == origin


def test_near_a_rough_guess_and_nothing_without_a_game():
    img = desktop((212, 61))
    assert find_canvas(img, near=(230, 50)) == (212, 61)
    assert find_canvas(np.full((800, 1280, 3), 90, np.uint8)) is None
    assert find_canvas(np.zeros((400, 600, 3), np.uint8)) is None         # screen too small


def test_window_origin_from_xdotool():
    import subprocess

    from skillbot.screen import window_rect

    def run(cmd, **kw):
        if cmd[1] == "search":
            out = "11\n22\n"
        elif cmd[-1] == "11":          # a small window that also matches the name
            out = ("  Absolute upper-left X:  5\n  Absolute upper-left Y:  5\n"
                   "  Relative upper-left X:  0\n  Width: 300\n  Height: 200\n")
        else:
            out = ("xwininfo: Window id: 0x22 \"RuneLite - megaman19999\"\n\n"
                   "  Absolute upper-left X:  212\n  Absolute upper-left Y:  61\n"
                   "  Relative upper-left X:  0\n  Relative upper-left Y:  0\n"
                   "  Width: 1010\n  Height: 503\n")
        return subprocess.CompletedProcess(cmd, 0, stdout=out)

    assert window_rect(run=run) == (212, 61, 1010, 503)
    assert window_rect(run=lambda *a, **k: subprocess.CompletedProcess(a, 0, stdout="")) \
        is None


def test_inside_the_window_the_top_left_canvas_wins():
    """As on the real client: the canvas's right edge meets the dark sidebar (weak), the
    sidebar's outer edge meets the desktop (sharp); the window rect includes the title bar
    and frame."""
    img = desktop((212, 61))
    img[61:61 + CANVAS_H, 212 + CANVAS_W:212 + CANVAS_W + 22] = (30, 30, 30)
    img[61:61 + CANVAS_H, 212 + CANVAS_W + 22] = (200, 0, 200)
    assert find_canvas(img, within=(170, 0, 1010, 620)) == (212, 61)
