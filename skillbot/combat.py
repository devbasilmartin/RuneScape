"""Combat training: Attack, Strength, Defence, Hitpoints, Ranged, Magic, and Prayer by
burying the bones it loots.

- Enemies: NPC Indicators color (``target``). NPCs already showing the game's health bar
  are fighting someone else and are skipped.
- Your HP: fill of the RuneLite Status Bars health bar (``layout.hp_bar``).
- Loot: Ground Items with "Highlight tiles" on, in the ``loot`` color.
- Food and bones: Inventory Tags.
"""
import logging
import math

import numpy as np

from .game import BotError
from .layout import Rect
from .tasks import Task
from .vision import color_mask

log = logging.getLogger("skillbot")

FOLLOW_PX = 40        # how far a target may move between looks and still be "the same one"
LOOT_RADIUS_PX = 160  # only pick up loot this close to the player
UNDER_ATTACK_WAIT = 30  # then attack anyway (the bar may be someone else's fight nearby)
RESPAWN_WAIT = 90     # seconds to wait for an enemy to (re)appear before giving up


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
        """Fraction of the Status Bars health bar that is filled (it fills from the bottom).
        RuneLite draws the fill half see-through, so besides ``color`` any clearly red
        pixel counts (red over the stone panel comes out darker than the color itself)."""
        crop = bar.crop(img)
        rgb = crop[..., :3].astype(np.int16)
        red = (rgb[..., 0] >= 90) & (rgb[..., 0] - np.maximum(rgb[..., 1], rgb[..., 2]) >= 50)
        rows = (red | color_mask(crop, color, tolerance)).any(axis=1)
        # the fill grows from the bottom; the heart icon at the top is red too, so only
        # the unbroken run from the bottom counts (a gap of a few rows is a tick line)
        top, gap = len(rows), 0
        for i in range(len(rows) - 1, -1, -1):
            if rows[i]:
                top, gap = i, 0
            else:
                gap += 1
                if gap > 3:
                    break
        return (len(rows) - top) / len(rows)

    def hp(self, img) -> float:
        cfg = self.game.cfg
        return self.hp_fraction(img, cfg.layout.hp_bar, cfg.hp_bar_color, cfg.color_tolerance)

    def bar_in(self, img, rect: Rect) -> bool:
        """The game draws a green/red bar over anything that is in combat."""
        area = rect.crop(img)
        tol = self.game.cfg.color_tolerance
        return sum(int(color_mask(area, c, tol).sum()) for c in self.game.cfg.health_bar_colors) >= 6

    def has_health_bar(self, img, blob) -> bool:
        return self.bar_in(img, Rect(blob.x, max(blob.y - 25, 0), blob.w, 30))

    def under_attack(self, img) -> bool:
        """A health bar right around the player: yours (you were hit) or that of an enemy
        next to you. Attacking another one then only gives "already under attack"."""
        px, py = self.game.player
        return self.bar_in(img, Rect(px - 60, py - 70, 120, 110))

    def follow(self, img, pos):
        """The blob that is most likely our target now, or None if it's gone (dead)."""
        blobs = [b for b in self.game.blobs(img, self.step.target)
                 if (b.center[0] - pos[0]) ** 2 + (b.center[1] - pos[1]) ** 2 <= FOLLOW_PX ** 2]
        if not blobs:
            return None
        return min(blobs, key=lambda b: (b.center[0] - pos[0]) ** 2 + (b.center[1] - pos[1]) ** 2)

    # ---- actions -------------------------------------------------------------------------
    def select_style(self) -> None:
        """Pick the step's attack style, but only once the combat tab is really open: the
        style buttons sit where inventory slots are, so a missed tab click would click an
        item instead (and use it on the next thing clicked)."""
        g = self.game
        if self.step.style is not None and not self.style_set:
            lay = g.layout
            first, last = lay.slot(0), lay.slot(27)
            panel = Rect(first.x, first.y, last.x + last.w - first.x, last.y + last.h - first.y)
            before = panel.crop(g.grab()).astype(np.int16)
            g.open_tab("combat")
            after = panel.crop(g.grab()).astype(np.int16)
            if np.abs(after - before).mean() < 4:
                log.warning("%s: the combat tab didn't open; leaving the attack style as it "
                            "is", self.step.name)
            else:
                g.controls.click(lay.combat_styles[self.step.style])
                g.wait(0.4, 0.7)
            g.open_tab("inventory")
        self.style_set = True

    def check_hp_bar(self, img) -> None:
        """An empty bar means it isn't there (you'd be dead): don't eat everything."""
        if self.hp(img) == 0:
            raise BotError(f"{self.step.name}: can't see your HP: turn on RuneLite's Status "
                           "Bars plugin (Hitpoints on the left; the bot profile does this) "
                           "and check the hp box in debug.png")

    def eat(self, img) -> bool:
        food = self.tagged(img, self.step.food)
        if not food:
            return False
        self.game.controls.click_rect(self.game.layout.slot(min(food)))
        self.stats["eaten"] += 1
        self.game.wait(1.8, 2.2)     # eating delay
        return True

    def wield(self, img) -> bool:
        """Picked-up arrows land in the inventory: wield them back into the quiver."""
        slots = sorted(self.tagged(img, self.step.wield))
        if not slots:
            return False
        self.game.controls.click_rect(self.game.layout.slot(slots[0]))
        self.game.wait(0.6, 0.9)
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
        before, room = len(g.inv.tags(img)), g.inv.empty_slots(img)
        if not g.click_blob(img, min(near, key=lambda b: (b.center[0] - px) ** 2
                                     + (b.center[1] - py) ** 2)):
            return False
        # picked up: a new tagged item, or any item (untagged) in a slot that was empty
        if g.wait_until(lambda im: len(g.inv.tags(im)) > before
                        or g.inv.empty_slots(im) < room, timeout=6):
            g.click_outcome(True)
            self.loot_misses = 0
        else:
            g.click_outcome(False)
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
        if not g.click_moving(img, blob, self.step.target,
                              still_free=lambda im, b: not self.has_health_bar(im, b)):
            return None                  # it walked off, or a random event is standing on it
        if self.step.cast:
            g.wait(0.3, 0.5)
            g.open_tab("inventory")
        return blob.center

    def wait_for_respawn(self) -> None:
        """Every enemy is dead or out of view: they respawn, so wait rather than stop."""
        g, step = self.game, self.step
        log.info("%s: no enemies in view; waiting for them to respawn", step.name)
        if not g.wait_until(lambda im: g.blobs(im, step.target), timeout=RESPAWN_WAIT):
            raise BotError(f"{step.name}: no enemies in view for {RESPAWN_WAIT} s (did the "
                           "player walk away from them, or the camera turn?)")

    def restock(self) -> bool:
        return self.bank_and_restock() and bool(self.tagged(self.game.grab(), self.step.food))

    # ---- loop ----------------------------------------------------------------------------
    def run_batch(self) -> str:
        g, step = self.game, self.step
        self.select_style()
        kills, target, engaged_at, misses, fight_since = 0, None, 0.0, 0, None
        while kills < step.kills_per_batch:
            img = g.grab()
            self.check_hp_bar(img)
            if step.cast and step.runes and not all(self.tagged(img, [r]) for r in step.runes):
                log.info("%s: out of runes", step.name)     # else it would attack by hand
                return "exhausted"
            if target is None and self.wield(img):
                continue
            if self.hp(img) < step.eat_below and not self.eat(img):
                log.info("%s: out of food at %.0f%% HP", step.name, 100 * self.hp(img))
                if step.when_out_of_food == "stop" or not self.restock():
                    return "exhausted"
                continue
            if step.bury and self.bury_bones(img):
                continue
            full = g.inv.is_full(img, step.tools)
            if full and self.tagged(img, step.items):
                self.full_inventory()
                break
            # full of food (nothing to drop or bank): keep fighting, just don't loot
            if target is not None:
                blob = self.follow(img, target)
                if blob is not None:
                    if self.has_health_bar(img, blob):
                        g.click_outcome(True)    # the attack started a fight
                        target, misses = blob.center, 0
                        g.wait(0.6, 1.0)
                        continue
                    if g.now() - engaged_at < step.idle_timeout:
                        g.wait(0.6, 1.0)      # still walking over / first hit pending
                        continue
                    misses += 1              # never got into a fight with it
                    g.click_outcome(False)
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
            if not full and self.pick_up(img):
                continue
            if self.under_attack(img):
                fight_since = fight_since if fight_since is not None else g.now()
                if g.now() - fight_since < UNDER_ATTACK_WAIT:
                    g.wait(0.6, 1.0)        # let this fight finish first
                    continue
            else:
                fight_since = None
            if not step.walk.get("target") and not g.blobs(img, step.target):
                self.wait_for_respawn()
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
            self.bank_and_restock()


class StandingCombatTask(CombatTask):
    """Crabs and other aggressive monsters: stand on a marked tile and let them come.
    Eats as usual. When nothing has fought you for `reset_after` seconds, walks to the
    reset tile and back so they become aggressive again."""

    STAND_PX = 25
    BATCH_MINUTES = 10

    def in_combat(self, img) -> bool:
        g = self.game
        return any(self.has_health_bar(img, b) for b in g.blobs(img, self.step.target)
                   if math.dist(b.center, g.player) <= 120)

    def go(self, color, timeout: float = 25) -> bool:
        g = self.game
        img = g.grab()
        if g.highlight_near(img, color, g.player, self.STAND_PX):
            return True
        if not g.click_nearest(img, color):
            return False
        return g.wait_until(lambda im: g.highlight_near(im, color, g.player, self.STAND_PX),
                            timeout=timeout)

    def reset(self) -> None:
        log.info("%s: resetting aggression", self.step.name)
        if not self.go(self.step.reset_spot):
            raise BotError(f"{self.step.name}: reset tile not reachable")
        self.game.wait(2, 3)
        if not self.go(self.step.stand_on):
            raise BotError(f"{self.step.name}: can't get back to the standing tile")
        self.stats["resets"] = self.stats.get("resets", 0) + 1

    def run_batch(self) -> str:
        g, step = self.game, self.step
        self.select_style()
        if step.stand_on and not self.go(step.stand_on):
            g.walk(step.walk.get("target"), step.stand_on)
            if not self.go(step.stand_on):
                raise BotError(f"{step.name}: standing tile not reachable")
        start = last_fight = g.now()
        fighting = False
        while g.now() - start < self.BATCH_MINUTES * 60:
            img = g.grab()
            self.check_hp_bar(img)
            if self.hp(img) < step.eat_below and not self.eat(img):
                if step.when_out_of_food == "stop" or not self.restock():
                    return "exhausted"
                continue
            if self.in_combat(img):
                if not fighting:
                    self.progressed(1)
                fighting, last_fight = True, g.now()
            else:
                fighting = False
                if step.reset_spot and g.now() - last_fight > step.reset_after:
                    self.reset()
                    last_fight = g.now()
            g.wait(1.5, 2.5)
        self.stats["batches"] += 1
        return "ok"
