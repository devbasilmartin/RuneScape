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
