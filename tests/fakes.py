"""A fake game window: a synthetic canvas plus recorded clicks, with hooks to advance
the world as time passes."""
import random

import numpy as np

from skillbot.config import Config, Step
from skillbot.game import Game
from skillbot.inventory import Inventory
from skillbot.layout import CANVAS_H, CANVAS_W, Layout

LAYOUT = Layout()
BG = (62, 53, 41)
SPRITE = (140, 110, 90)
ITEMS = {"logs": (0, 255, 0), "raw_shrimps": (0, 128, 255), "shrimps": (255, 128, 0),
         "burnt_fish": (255, 0, 0), "copper_ore": (200, 100, 0), "bones": (255, 255, 255),
         "trout": (128, 0, 255), "cowhide": (100, 60, 20), "rune_essence": (200, 200, 60),
         "fire_rune": (255, 40, 200), "fire_talisman": (60, 200, 200), "tiara": (40, 40, 160),
         "fire_tiara": (160, 40, 40)}
TREE = (0, 255, 255)
BANK = (255, 0, 255)
RANGE = (255, 255, 0)


def blank():
    return np.full((CANVAS_H, CANVAS_W, 3), BG, np.uint8)


def outline(img, x, y, w, h, color):
    img[y:y + h, x] = color
    img[y:y + h, x + w - 1] = color
    img[y, x:x + w] = color
    img[y + h - 1, x:x + w] = color


def put_item(img, slot, name):
    r = LAYOUT.slot(slot)
    img[r.y:r.y + r.h, r.x:r.x + r.w] = BG
    if name:
        img[r.y + 6:r.y + r.h - 6, r.x + 6:r.x + r.w - 6] = SPRITE
        outline(img, r.x + 5, r.y + 5, r.w - 10, r.h - 10, ITEMS[name])


def slot_at(pt):
    for i in range(28):
        r = LAYOUT.slot(i)
        if r.x <= pt[0] < r.x + r.w and r.y <= pt[1] < r.y + r.h:
            return i
    return None


def config(steps=(), **kw):
    cfg = Config(items=dict(ITEMS), bank_color=BANK, **kw)
    cfg.plan = [Step.from_dict(s) for s in steps]
    cfg.validate()
    return cfg


class FakeClient:
    def __init__(self):
        self.t = 0.0
        self.img = blank()
        self.clicks, self.keys = [], []
        self.shift = False
        self.rng = random.Random(1)
        self.on_wait = []       # fn(fake) called on every wait
        self.on_click = []      # fn(fake, pt) called on every click
        self.on_key = []        # fn(fake, key)

    # Screen
    def grab(self):
        return self.img.copy()

    # Controls
    def click_rect(self, rect, button="left"):
        self.click(rect.center)

    def click(self, pt, button="left"):
        self.clicks.append((tuple(pt), self.shift))
        for fn in list(self.on_click):
            fn(self, pt)

    def key_down(self, k):
        if k == "shift":
            self.shift = True

    def key_up(self, k):
        if k == "shift":
            self.shift = False

    def hold(self, k, s):
        self.keys.append(k)

    def press(self, k, presses=1):
        self.keys.append(k)
        for fn in list(self.on_key):
            fn(self, k)

    def type_text(self, text):
        self.keys.append(("type", text))

    def wait(self, lo, hi=None):
        self.t += lo
        for fn in list(self.on_wait):
            fn(self)

    def items(self):
        inv = Inventory(LAYOUT, ITEMS)
        return inv.tags(self.img)


def make_game(cfg, fake=None):
    fake = fake or FakeClient()
    game = Game(cfg, fake, fake, Inventory(LAYOUT, cfg.items), now=lambda: fake.t)
    return game, fake
