"""The HP guard: every activity, not just combat, keeps an eye on your HP.

Every screen grab is a chance to look at the Status Bars health bar (at most every
CHECK_EVERY seconds). Below the step's ``eat_below`` (50% by default):
- eat: the step's food, or any food in FOOD that's tagged in the inventory;
- no food, and HP is falling (something is hitting you) or below CRITICAL: get away (walk the step's bank route, if it has one), log out, tell you, and
  stop (the stop message tells you). The escape is remembered (data/danger.json); after DANGER_COUNT escapes the
  activity is skipped until your level is past the highest level it happened at.

An empty bar means it isn't on screen (logged out, a full-screen interface): no action.
"""
import json
import logging
import time
from pathlib import Path

from .game import BotError, StopBot

log = logging.getLogger("skillbot")

CHECK_EVERY = 2.0
EAT_BELOW = 0.5
FOOD = ("cooked_meat", "shrimps", "anchovies", "trout", "lobster", "swordfish")  # in colors.yaml
CRITICAL = 0.2           # with no food, flee below this even if nothing seems to hit you
FALLING_SECONDS = 60     # HP dropped this recently: something is hitting you
DANGER_COUNT = 2
DANGER_DAYS = 14
LOGOUT_ATTEMPTS = 12      # the game refuses for 10 s after combat; keep trying ~2 minutes


class DangerLog:
    """Escapes per step, and whether a step is too dangerous at a level."""

    def __init__(self, path: Path | None, clock=time.time):
        self.path, self.clock = path, clock
        try:
            self.data = json.loads(Path(path).read_text()) if path else {}
        except (OSError, ValueError):
            self.data = {}

    def add(self, step: str, level: int) -> int:
        self.data.setdefault(step, []).append({"time": self.clock(), "level": level})
        if self.path:
            Path(self.path).write_text(json.dumps(self.data, indent=1))
        return len(self.recent(step))

    def recent(self, step: str) -> list[dict]:
        since = self.clock() - DANGER_DAYS * 86400
        return [e for e in self.data.get(step, []) if e["time"] >= since]

    def dangerous_until(self, step: str) -> int | None:
        """The level to get past before the step is safe again, or None if it's fine."""
        recent = self.recent(step)
        if len(recent) < DANGER_COUNT:
            return None
        return max(e["level"] for e in recent)


class HPGuard:
    def __init__(self, game, session=None, danger: DangerLog | None = None,
                 level=lambda skill: 0):
        self.game, self.session = game, session
        self.danger = danger or DangerLog(None)
        self.level = level          # skill -> current level, for the danger log
        self.step = None            # the step running now (set by the planner)
        self.last = float("-inf")
        self.previous = None        # the last HP reading
        self.dropped_at = float("-inf")
        self.warned = False
        self.stats = {"eaten": 0, "escapes": 0}

    def hp(self, img) -> float:
        from .combat import CombatTask
        cfg = self.game.cfg
        return CombatTask.hp_fraction(img, cfg.layout.hp_bar, cfg.hp_bar_color,
                                      cfg.color_tolerance)

    def food_slots(self, img) -> list[int]:
        names = set(self.step.food) if self.step is not None and self.step.food else set(FOOD)
        return sorted(i for i, n in self.game.inv.tags(img).items() if n in names)

    def check(self, img) -> bool:
        """Eat or escape if HP is low. True when it did something (the screen changed)."""
        g = self.game
        if g.now() - self.last < CHECK_EVERY:
            return False
        self.last = g.now()
        hp = self.hp(img)
        if hp == 0:
            return False
        if self.previous is not None and hp < self.previous - 0.01:
            self.dropped_at = g.now()
        self.previous = hp
        limit = self.step.eat_below if self.step is not None else EAT_BELOW
        if hp >= limit:
            self.warned = False
            return False
        acted = False
        with g.guard_paused():
            slots = self.food_slots(img)
            falling = g.now() - self.dropped_at <= FALLING_SECONDS
            if not slots and (falling or hp < CRITICAL) and not g.inv.any_tag_visible(img):
                g.open_tab("inventory")         # another tab was open: look before fleeing
                slots, acted = self.food_slots(g.grab()), True
            if slots:
                g.controls.click_rect(g.layout.slot(slots[0]))
                self.stats["eaten"] += 1
                log.info("HP %.0f%%: eating (%d food left)", 100 * hp, len(slots) - 1)
                g.wait(1.8, 2.2)
                return True
            if self.restocks() and hp >= CRITICAL:
                return acted                    # the task banks for more food itself
            if hp >= CRITICAL and g.now() - self.dropped_at > FALLING_SECONDS:
                if not self.warned:             # low but steady (e.g. after combat)
                    log.info("HP %.0f%%, no food, nothing hitting you: carrying on", 100 * hp)
                    self.warned = True
                return acted
            self.escape(hp)

    def restocks(self) -> bool:
        """Steps with their own food and bank trips (combat, thieving) fetch more food
        themselves; the guard only steps in when HP gets critical."""
        s = self.step
        return s is not None and bool(s.food) and s.when_out_of_food == "bank"

    def escape(self, hp: float) -> None:
        g, step = self.game, self.step
        name = step.name if step is not None else "the bot"
        self.stats["escapes"] += 1
        log.warning("HP %.0f%% and no food: getting away and logging out", 100 * hp)
        if getattr(g, "blackbox", None) is not None:
            g.blackbox.save(f"{name}: HP {hp:.0%} and no food")
        route = step.walk.get("bank") if step is not None else None
        if route and g.cfg.bank_color is not None:
            try:
                g.walk(route, g.cfg.bank_color)
            except BotError as e:
                log.warning("couldn't walk to the bank: %s", e)
        out = self.session.logout(LOGOUT_ATTEMPTS) if self.session is not None else False
        text = (f"{name}: HP {hp:.0%} and no food left, so I "
                + ("logged out." if out else "tried to log out but the game refused: check on it!"))
        if step is not None:
            level = self.level(step.skill)
            if self.danger.add(step.name, level) >= DANGER_COUNT:
                text += (f" That's {DANGER_COUNT} times recently: {step.name} is skipped "
                         f"until {step.skill} is past {level}.")
        raise StopBot(text)          # the run stops and you get this as the reason
