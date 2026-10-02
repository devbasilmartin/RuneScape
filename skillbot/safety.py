"""Things that can happen during any step: random events, deaths, crowded worlds.

- Random events: NPCs highlighted in the danger color are never clicked (see
  Game.click_nearest). The Genie (its own color) is talked to, and its lamp used on the
  skill you chose.
- Death: you respawn on a tile marked with the respawn color. The bot tells you, walks
  back to the step's location, takes the grave, re-equips and continues; a second death
  on the same step within an hour stops it.
- Crowding: other players (Player Indicators) near your target for a while → hop to the
  next world with World Hopper's hotkey, between inventories only, with a cooldown.
"""
import logging
from dataclasses import dataclass, field, fields

from .dialog import Dialog
from .game import BotError, StopBot

log = logging.getLogger("skillbot")


@dataclass
class SafetyConfig:
    genie_skill_point: tuple | None = None    # where your chosen skill is in the lamp window
    lamp_confirm: tuple | None = None         # the lamp window's confirm button
    lamp_item: str | None = "lamp"            # Inventory Tags name of the XP lamp
    grave_take: tuple | None = None           # "take all" in the grave window
    death_window_minutes: float = 60
    hop: bool = True
    hop_crowd: int = 3                        # other players near the target...
    hop_minutes: float = 2                    # ...for this long
    hop_cooldown_minutes: float = 5
    hop_hotkey: tuple = ("ctrl", "shift", "right")
    hop_max_in_a_row: int = 5                 # then stay: probably just a busy time of day
    crowd_radius_px: int = 120

    @classmethod
    def from_dict(cls, d: dict | None) -> "SafetyConfig":
        d = dict(d or {})
        unknown = set(d) - {f.name for f in fields(cls)}
        if unknown:
            raise ValueError(f"unknown safety keys: {sorted(unknown)}")
        for k in ("genie_skill_point", "lamp_confirm", "grave_take", "hop_hotkey"):
            if d.get(k) is not None:
                d[k] = tuple(d[k])
        return cls(**d)


@dataclass
class Safety:
    game: object
    cfg: SafetyConfig
    genie_color: tuple | None = None
    respawn_color: tuple | None = None
    grave_color: tuple | None = None
    player_color: tuple | None = None
    notify: object = None
    deaths: dict = field(default_factory=dict)     # step name -> [times]
    crowded_since: float | None = None
    last_hop: float = float("-inf")
    hops_in_a_row: int = 0

    def _notify(self, msg: str) -> None:
        if self.notify:
            self.notify(msg)

    # ---- every action ------------------------------------------------------------------
    def check(self, step) -> None:
        """Called before each action: handles a Genie and a death."""
        g = self.game
        img = g.grab()
        if self.respawn_color and g.blobs(img, self.respawn_color) and step is not None:
            self.died(step)
            return
        if self.genie_color and g.highlight_near(img, self.genie_color, g.player, 120):
            self.claim_lamp()

    # ---- Genie ------------------------------------------------------------------------
    def claim_lamp(self) -> None:
        g, c = self.game, self.cfg
        log.info("Genie: claiming the lamp")
        if not g.click_nearest(g.grab(), self.genie_color, avoid_danger=False):
            return
        g.wait(1.5, 2.0)
        Dialog(g).advance()
        if not (c.lamp_item and c.genie_skill_point and c.lamp_confirm):
            self._notify("a Genie gave you a lamp; set safety.genie_skill_point to use it "
                         "automatically")
            return
        slots = g.inv.slots_with(g.grab(), c.lamp_item)
        if not slots:
            return
        g.controls.click_rect(g.layout.slot(min(slots)))
        g.wait(1.0, 1.5)
        g.controls.click(c.genie_skill_point)
        g.wait(0.4, 0.7)
        g.controls.click(c.lamp_confirm)
        g.wait(1.0, 1.5)
        Dialog(g).advance()

    # ---- death ------------------------------------------------------------------------
    def died(self, step) -> None:
        g, now = self.game, self.game.now()
        window = self.cfg.death_window_minutes * 60
        recent = [t for t in self.deaths.get(step.name, []) if t > now - window] + [now]
        self.deaths[step.name] = recent
        self._notify(f"died during {step.name!r} ({len(recent)} in the last "
                     f"{self.cfg.death_window_minutes:.0f} min)")
        if len(recent) >= 2:
            raise StopBot(f"died twice on {step.name!r} within "
                          f"{self.cfg.death_window_minutes:.0f} min; this step is too dangerous")
        if not step.location or g.nav is None:
            raise StopBot(f"died during {step.name!r} and it has no location to walk back to")
        g.nav.travel(step.location, self.grave_color)
        self.take_grave()
        self.wear(step.gear)

    def wear(self, names) -> None:
        """Left-click each gear item in the inventory (Wield / Wear)."""
        g = self.game
        for name in names:
            slots = g.inv.slots_with(g.grab(), name)
            if slots:
                g.controls.click_rect(g.layout.slot(min(slots)))
                g.wait(0.6, 0.9)

    def take_grave(self) -> None:
        g = self.game
        if not self.grave_color or not g.click_nearest(g.grab(), self.grave_color,
                                                       avoid_danger=False):
            raise BotError("couldn't find the grave")
        g.wait(1.5, 2.5)
        if self.cfg.grave_take:
            g.controls.click(self.cfg.grave_take)
            g.wait(1.0, 1.5)
        g.close_interfaces()
        if g.blobs(g.grab(), self.grave_color):
            self._notify("the grave is still there after trying to take it: check it soon")

    # ---- world hopping -----------------------------------------------------------------
    def crowded(self, img, target) -> bool:
        g = self.game
        if not self.player_color or target is None:
            return False
        anchor = g.nearest(img, target)
        point = anchor.center if anchor else g.player
        r2 = self.cfg.crowd_radius_px ** 2
        others = [b for b in g.blobs(img, self.player_color)
                  if (b.center[0] - point[0]) ** 2 + (b.center[1] - point[1]) ** 2 <= r2]
        return len(others) >= self.cfg.hop_crowd

    def between_batches(self, step) -> bool:
        """Hop worlds if the step's spot has been crowded long enough. True if it hopped."""
        g, c = self.game, self.cfg
        if not c.hop or step is None:
            return False
        now = g.now()
        if not self.crowded(g.grab(), step.target):
            self.crowded_since = None
            self.hops_in_a_row = 0
            return False
        if self.crowded_since is None:
            self.crowded_since = now
        if now - self.crowded_since < c.hop_minutes * 60:
            return False
        if now - self.last_hop < c.hop_cooldown_minutes * 60:
            return False
        if self.hops_in_a_row >= c.hop_max_in_a_row:
            return False
        log.info("crowded: hopping worlds")
        g.controls.hotkey(*c.hop_hotkey)
        g.wait(8, 12)                      # world switch and load
        self.last_hop, self.crowded_since = g.now(), None
        self.hops_in_a_row += 1
        return True
