import random

import numpy as np
import pytest

from fishbot import vision
from fishbot.bot import BotError, FishingBot
from fishbot.config import Config
from fishbot.inventory import Inventory
from fishbot.layout import CANVAS_H, CANVAS_W, Layout

LAYOUT = Layout()
BG = (62, 53, 41)


def blank():
    return np.full((CANVAS_H, CANVAS_W, 3), BG, np.uint8)


def draw_outline(img, x, y, w, h, color):
    img[y:y + h, x] = color
    img[y:y + h, x + w - 1] = color
    img[y, x:x + w] = color
    img[y + h - 1, x:x + w] = color


ITEMS = Config().items
SPRITE = (140, 110, 90)


def put_item(img, slot, name="raw_shrimps"):
    """Draw an item sprite; tagged items get an Inventory Tags style outline."""
    r = LAYOUT.slot(slot)
    img[r.y + 6:r.y + r.h - 6, r.x + 6:r.x + r.w - 6] = SPRITE
    if name:
        draw_outline(img, r.x + 5, r.y + 5, r.w - 10, r.h - 10, ITEMS[name])


def make_inventory():
    return Inventory(LAYOUT, ITEMS, tools=1)


def test_find_blobs_joins_outline_and_reports_box():
    img = blank()
    draw_outline(img, 100, 120, 40, 30, (0, 255, 255))
    draw_outline(img, 300, 50, 20, 20, (0, 250, 250))
    blobs = vision.find_blobs(img, (0, 255, 255), 25, region=LAYOUT.viewport)
    assert len(blobs) == 2
    big = blobs[0]
    assert (big.x, big.y) == (97, 117) and big.w == 46   # includes dilation margin
    assert vision.nearest(blobs, (310, 60)).center == blobs[1].center


def test_color_tolerance_rejects_other_colors():
    img = blank()
    draw_outline(img, 100, 120, 40, 30, (255, 0, 255))
    assert vision.find_blobs(img, (0, 255, 255), 25) == []


def test_inventory_reads_tags_and_ignores_untagged():
    inv = make_inventory()
    img = blank()
    put_item(img, 0, name=None)      # the net is untagged
    put_item(img, 5, "raw_shrimps")
    put_item(img, 6, "raw_anchovies")
    assert inv.tags(img) == {5: "raw_shrimps", 6: "raw_anchovies"}
    assert inv.slots_with(img, "raw_anchovies") == [6]
    assert not inv.is_full(img)
    for i in range(1, 28):
        put_item(img, i, "burnt_fish")
    assert inv.is_full(img)


def test_tile_route_walks_to_marked_tile():
    game = FakeGame()
    game.img = blank()
    draw_outline(game.img, 100, 60, 30, 20, (255, 128, 0))      # ground marker
    cfg = Config(mode="bank", routes={"to_spot": [(255, 128, 0)]})
    bot = FishingBot(cfg, game, game, make_inventory(), now=lambda: game.t)
    game.on_click = lambda pt: draw_outline(game.img, 240, 150, 40, 30, (0, 255, 255))
    bot.step_fish(game.grab())
    assert 100 <= game.clicks[0][0][0] <= 130
    assert bot.blobs(game.grab(), cfg.fishing_color)


class FakeGame:
    """Stands in for Screen + Controls; the world advances as the bot clicks."""

    def __init__(self):
        self.t = 0.0
        self.img = blank()
        draw_outline(self.img, 240, 150, 40, 30, (0, 255, 255))   # spot next to the player
        self.clicks, self.keys = [], []
        self.shift = False
        self.fish = 0
        self.rng = random.Random(1)
        self.on_click = None

    # Screen
    def grab(self):
        return self.img.copy()

    # Controls
    def click_rect(self, rect, button="left"):
        self.click(rect.center)

    def click(self, pt, button="left"):
        self.clicks.append((pt, self.shift))
        if self.on_click:
            self.on_click(pt)
        for i in range(28):
            r = LAYOUT.slot(i)
            if self.shift and r.x <= pt[0] < r.x + r.w and r.y <= pt[1] < r.y + r.h:
                self.img[r.y:r.y + r.h, r.x:r.x + r.w] = BG

    def key_down(self, k):
        self.shift = k == "shift" or self.shift

    def key_up(self, k):
        self.shift = False if k == "shift" else self.shift

    def hold(self, k, s):
        self.keys.append(k)

    def press(self, k):
        self.keys.append(k)

    def wait(self, lo, hi=None):
        self.t += lo
        # catch a fish every 3 seconds into the first free slot
        if int(self.t) % 3 == 0 and self.fish < 27:
            self.fish += 1
            put_item(self.img, self.fish)


def test_drop_mode_fills_and_drops():
    game = FakeGame()
    cfg = Config(mode="drop", max_runtime_minutes=3)
    bot = FishingBot(cfg, game, game, make_inventory(), now=lambda: game.t)
    bot.run()
    assert bot.stats["trips"] >= 1
    assert any(shift for _, shift in game.clicks)
    # the tool slot is never dropped
    tool = LAYOUT.slot(0)
    assert not any(s and tool.x <= p[0] < tool.x + tool.w and tool.y <= p[1] < tool.y + tool.h
                   for p, s in game.clicks)


def test_walk_fails_loudly_without_route():
    game = FakeGame()
    game.img = blank()
    bot = FishingBot(Config(mode="drop"), game, game, make_inventory(), now=lambda: game.t)
    with pytest.raises(BotError):
        bot.step_fish(game.grab())


def test_gives_up_when_catches_are_not_detected():
    game = FakeGame()
    game.wait = lambda lo, hi=None: setattr(game, "t", game.t + lo)   # nothing is ever caught
    bot = FishingBot(Config(mode="drop", max_runtime_minutes=30), game, game, make_inventory(),
                     now=lambda: game.t)
    with pytest.raises(BotError, match="without a catch"):
        bot.run()
