"""Combat training: Attack, Strength, Defence, Hitpoints, Ranged, Magic, and Prayer by
burying the bones it loots.

- Enemies: NPC Indicators color (``target``). NPCs already showing the game's health bar
  are fighting someone else and are skipped.
- Your HP: fill of the RuneLite Status Bars health bar (``layout.hp_bar``).
- Loot: Ground Items with "Highlight tiles" on, in the ``loot`` color.
- Food and bones: Inventory Tags.
"""
import logging

import numpy as np

from .game import BotError
from .layout import Rect
from .tasks import Task
from .vision import color_mask

log = logging.getLogger("skillbot")

FOLLOW_PX = 40        # how far a target may move between looks and still be "the same one"
LOOT_RADIUS_PX = 160  # only pick up loot this close to the player


class CombatTask(Task):
    def __init__(self, game, step):
        super().__init__(game, step)
        self.stats.update(kills=0, eaten=0, buried=0)
        self.style_set = False
        self.loot_misses = 0
        self.ignore_loot_until = 0.0

    # ---- reading the screen --------------------------------------------------------------
    @staticmethod
    def hp_fraction(img, bar: Rect, color, tolerance: int) -> float:
        """Fraction of the Status Bars health bar that is filled (it fills from the bottom)."""
        rows = color_mask(bar.crop(img), color, tolerance).any(axis=1)
        filled = np.flatnonzero(rows)
        return 0.0 if not len(filled) else (len(rows) - filled[0]) / len(rows)

    def hp(self, img) -> float:
        cfg = self.game.cfg
        return self.hp_fraction(img, cfg.layout.hp_bar, cfg.hp_bar_color, cfg.color_tolerance)

    def has_health_bar(self, img, blob) -> bool:
        """The game draws a green/red bar over anything that is in combat."""
        area = Rect(blob.x, max(blob.y - 25, 0), blob.w, 30).crop(img)
        tol = self.game.cfg.color_tolerance
        return sum(int(color_mask(area, c, tol).sum()) for c in self.game.cfg.health_bar_colors) >= 6

    def follow(self, img, pos):
        """The blob that is most likely our target now, or None if it's gone (dead)."""
        blobs = [b for b in self.game.blobs(img, self.step.target)
                 if (b.center[0] - pos[0]) ** 2 + (b.center[1] - pos[1]) ** 2 <= FOLLOW_PX ** 2]
        if not blobs:
            return None
        return min(blobs, key=lambda b: (b.center[0] - pos[0]) ** 2 + (b.center[1] - pos[1]) ** 2)

    # ---- actions -------------------------------------------------------------------------
    def select_style(self) -> None:
        g = self.game
        if self.step.style is not None and not self.style_set:
            g.open_tab("combat")
            g.controls.click(g.layout.combat_styles[self.step.style])
            g.wait(0.4, 0.7)
            g.open_tab("inventory")
        self.style_set = True

    def eat(self, img) -> bool:
        food = self.tagged(img, self.step.food)
        if not food:
            return False
        self.game.controls.click_rect(self.game.layout.slot(min(food)))
        self.stats["eaten"] += 1
        self.game.wait(1.8, 2.2)     # eating delay
        return True

    def bury_bones(self, img) -> bool:
        bones = sorted(self.tagged(img, self.step.bury))
        for i in bones:
            self.game.controls.click_rect(self.game.layout.slot(i))
            self.game.wait(1.2, 1.5)
            self.stats["buried"] += 1
            self.progressed(1)
        return bool(bones)

    def pick_up(self, img) -> bool:
        g = self.game
        if self.step.loot is None or g.now() < self.ignore_loot_until:
            return False
        px, py = g.player
        near = [b for b in g.blobs(img, self.step.loot)
                if (b.center[0] - px) ** 2 + (b.center[1] - py) ** 2 <= LOOT_RADIUS_PX ** 2]
        if not near:
            return False
        before = len(g.inv.tags(img))
        g.controls.click_rect(min(near, key=lambda b: (b.center[0] - px) ** 2
                                  + (b.center[1] - py) ** 2).rect)
        if g.wait_until(lambda im: len(g.inv.tags(im)) > before, timeout=6):
            self.loot_misses = 0
        else:
            # untagged loot is fine once, but a pile we can never pick up must not stall us
            self.loot_misses += 1
            if self.loot_misses >= 3:
                log.info("%s: ignoring loot for a minute", self.step.name)
                self.ignore_loot_until, self.loot_misses = g.now() + 60, 0
        return True

    def attack(self, img):
        """Click the nearest free enemy. Returns its position, or None if there is none."""
        g = self.game
        free = [b for b in g.blobs(img, self.step.target) if not self.has_health_bar(img, b)]
        if not free:
            return None
        px, py = g.player
        blob = min(free, key=lambda b: (b.center[0] - px) ** 2 + (b.center[1] - py) ** 2)
        if self.step.cast:
            g.open_tab("magic")
            g.controls.click(self.step.cast)
            g.wait(0.2, 0.4)
        g.controls.click_rect(blob.rect)
        if self.step.cast:
            g.wait(0.3, 0.5)
            g.open_tab("inventory")
        return blob.center

    def restock(self) -> bool:
        g = self.game
        g.bank(self.step.walk.get("bank"), self.step.withdraw)
        return bool(self.tagged(g.grab(), self.step.food))

    # ---- loop ----------------------------------------------------------------------------
    def run_batch(self) -> str:
        g, step = self.game, self.step
        self.select_style()
        kills, target, engaged_at, misses = 0, None, 0.0, 0
        while kills < step.kills_per_batch:
            img = g.grab()
            if self.hp(img) < step.eat_below and not self.eat(img):
                log.info("%s: out of food at %.0f%% HP", step.name, 100 * self.hp(img))
                if step.when_out_of_food == "stop" or not self.restock():
                    return "exhausted"
                continue
            if step.bury and self.bury_bones(img):
                continue
            if g.inv.is_full(img, step.tools + len(self.tagged(img, step.food))):
                self.full_inventory()
                break
            if target is not None:
                blob = self.follow(img, target)
                if blob is not None:
                    if self.has_health_bar(img, blob):
                        target, misses = blob.center, 0
                        g.wait(0.6, 1.0)
                        continue
                    if g.now() - engaged_at < step.idle_timeout:
                        g.wait(0.6, 1.0)      # still walking over / first hit pending
                        continue
                    misses += 1              # never got into a fight with it
                    if misses >= 4:
                        raise BotError(f"{step.name}: attacks aren't starting fights; is the "
                                       "enemy reachable and is the health bar color right?")
                else:
                    kills += 1
                    self.stats["kills"] += 1
                    self.progressed(1)
                    g.wait(1.0, 1.6)         # the drop appears a moment after death
                target = None
                continue
            if self.pick_up(img):
                continue
            g.walk(step.walk.get("target"), step.target)
            target = self.attack(g.grab())
            if target is None:
                g.wait(1.0, 2.0)             # every enemy is busy; wait for a free one
            engaged_at = g.now()
        self.stats["batches"] += 1
        return "ok"

    def full_inventory(self) -> None:
        g, step = self.game, self.step
        log.info("%s: inventory full of loot", step.name)
        if step.when_full == "drop":
            g.drop(names=set(step.items))
        else:
            g.bank(step.walk.get("bank"), step.withdraw)
