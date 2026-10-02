"""Runs `task: routine` steps (the language is described in routine_spec.py).

Colors may be registry names or [r, g, b]; items are Inventory Tags names. Eating
(the step's food / eat_below) is checked before every action.
"""
import logging

from .colors import Registry
from .combat import CombatTask
from .dialog import Dialog
from .game import BotError
from .routine_spec import ACTIONS

log = logging.getLogger("skillbot")
NEAR_PX = 60


def kind_of(action: dict) -> str:
    (kind,) = set(action) & ACTIONS
    return kind


class RoutineTask(CombatTask):
    def __init__(self, game, step):
        super().__init__(game, step)
        self.counters = {}
        self.snapshot = {}
        self._registry = None

    # ---- helpers -----------------------------------------------------------------------
    def color(self, value):
        if isinstance(value, str):
            if self._registry is None:
                self._registry = Registry.load(self.game.cfg.colors_file)
            return self._registry.resolve(value)
        return tuple(value)

    def counts(self, img) -> dict:
        out = {}
        for name in self.game.inv.tags(img).values():
            out[name] = out.get(name, 0) + 1
        return out

    @staticmethod
    def _names(v):
        return [v] if isinstance(v, str) else list(v)

    # ---- conditions --------------------------------------------------------------------
    def holds(self, cond: dict, img=None) -> bool:
        g, step = self.game, self.step
        img = g.grab() if img is None else img
        counts = self.counts(img)
        for key, v in cond.items():
            if key == "visible" and not g.blobs(img, self.color(v)):
                return False
            if key == "not_visible" and g.blobs(img, self.color(v)):
                return False
            if key == "near" and not g.highlight_near(img, self.color(v), g.player, NEAR_PX):
                return False
            if key == "has" and not all(counts.get(n) for n in self._names(v)):
                return False
            if key == "lacks" and any(counts.get(n) for n in self._names(v)):
                return False
            if key == "count_at_least" and any(counts.get(n, 0) < k for n, k in v.items()):
                return False
            if key == "full":
                food = len(self.tagged(img, step.food))
                if g.inv.is_full(img, step.tools + food) != bool(v):
                    return False
            if key == "hp_below" and not self.hp(img) < v:
                return False
            if key == "counter_at_least" and any(self.counters.get(n, 0) < k
                                                 for n, k in v.items()):
                return False
            if key == "gained" and not all(counts.get(n, 0) > self.snapshot.get(n, 0)
                                           for n in self._names(v)):
                return False
            if key == "lost" and not all(counts.get(n, 0) < self.snapshot.get(n, 0)
                                         for n in self._names(v)):
                return False
            if key == "any" and not any(self.holds(c, img) for c in v):
                return False
        return True

    # ---- actions -----------------------------------------------------------------------
    def click_target(self, target, action) -> bool:
        g = self.game
        if isinstance(target, dict) and "item" in target:
            slots = self.tagged(g.grab(), [target["item"]])
            if not slots:
                return False
            g.controls.click_rect(g.layout.slot(min(slots)))
            return True
        if isinstance(target, dict) and "point" in target:
            g.controls.click(tuple(target["point"]))
            return True
        img = g.grab()
        color = self.color(target)
        if action.get("right_option"):
            blob = g.nearest(img, color)
            if blob is None:
                return False
            point = blob.center
            g.controls.click(point, button="right")
            g.wait(0.4, 0.6)
            lay = g.layout
            g.controls.click((point[0], point[1] + lay.menu_header
                              + lay.menu_row * (action["right_option"] - 1) + lay.menu_row // 2))
            return True
        return g.click_nearest(img, color, avoid_danger=action.get("avoid_danger", True))

    def act(self, action: dict) -> bool:
        g, step = self.game, self.step
        kind = kind_of(action)
        v = action[kind]
        if kind == "click":
            ok = self.click_target(v, action)
            if ok:
                g.wait(0.6, 1.0)
            return ok
        if kind == "use":
            if not self.click_target({"item": v["item"]}, {}):
                return False
            g.wait(0.3, 0.5)
            ok = self.click_target(v["target"], {})
            g.wait(0.6, 1.0)
            return ok
        if kind == "key":
            g.controls.press(str(v))
            g.wait(0.3, 0.6)
            return True
        if kind == "type":
            try:
                text = str(v).format(**step.vars)
            except KeyError as e:
                raise BotError(f"{step.name}: set vars.{e.args[0]} for this step "
                               "(e.g. in goals overrides or the plan)") from e
            g.controls.type_text(text)
            g.wait(0.3, 0.6)
            return True
        if kind == "wait":
            lo, hi = (v, v) if isinstance(v, (int, float)) else v
            g.wait(lo, hi)
            return True
        if kind == "wait_for":
            return g.wait_until(lambda img: self.holds(v, img),
                                timeout=action.get("timeout", 20))
        if kind == "bank":
            return self.bank_and_restock()
        if kind == "drop":
            g.drop(names=set(self._names(v)))
            return True
        if kind == "travel":
            if g.nav is None:
                raise BotError("travel needs navigation (hubs) set up")
            g.nav.travel(v, self.color(action["until"]) if action.get("until") else None)
            return True
        if kind == "walk":
            g.walk(v, self.color(action["until"]))
            return True
        if kind == "cast":
            spell = v["spell"] if isinstance(v, dict) else v
            point = g.cfg.spells.get(spell) if isinstance(spell, str) else tuple(spell)
            if point is None:
                raise BotError(f"spell {spell!r} has no position (spells: in config.yaml)")
            g.open_tab("magic")
            g.controls.click(point)
            g.wait(0.3, 0.5)
            item = v.get("on_item") if isinstance(v, dict) else action.get("on_item")
            if item:
                return self.click_target({"item": item}, {})
            return True
        if kind == "dialog":
            Dialog(g).talk([int(o) for o in (v or [])])
            return True
        if kind == "tab":
            g.open_tab(v)
            return True
        if kind == "notify":
            from .notify import notify
            notify(f"{step.name}: {v}")
            return True
        if kind == "progress":
            self.progressed(int(v))
            return True
        raise BotError(f"unknown action {kind}")

    # ---- running -----------------------------------------------------------------------
    def run_do(self, block: dict, until_fail: bool) -> bool:
        g, step = self.game, self.step
        self.snapshot = self.counts(g.grab())
        for action in block["do"]:
            img = g.grab()
            if step.food and self.hp(img) < step.eat_below and not self.eat(img):
                raise BotError(f"{step.name}: out of food")
            if not self.act(action):
                if until_fail:
                    return False
                raise BotError(f"{step.name} / {block.get('name', 'block')}: "
                               f"{kind_of(action)} didn't work")
        return True

    def run_block(self, block: dict) -> str | None:
        if "when" in block and not self.holds(block["when"]):
            return None
        if "exhausted_if" in block and self.holds(block["exhausted_if"]):
            log.info("%s: %s says out of supplies", self.step.name, block.get("name", "block"))
            return "exhausted"
        until = block.get("repeat_until")
        until_fail = bool(block.get("until_fail"))
        limit = int(block.get("max", 50))
        for n in range(limit):
            if until is not None and self.holds(until):
                break
            ok = self.run_do(block, until_fail)
            if not ok or (until is None and not until_fail):
                break
        else:
            if until is not None and not self.holds(until):
                raise BotError(f"{self.step.name} / {block.get('name', 'block')}: still not done "
                               f"after {limit} tries")
        if block.get("count"):
            self.counters[block["count"]] = self.counters.get(block["count"], 0) + 1
        for name in block.get("reset", []):
            self.counters[name] = 0
        return None

    def run_batch(self) -> str:
        routine = self.step.routine
        explicit = any("progress" in a for b in routine for a in b["do"])
        for block in routine:
            if self.run_block(block) == "exhausted":
                return "exhausted"
        if not explicit:
            self.progressed(1)
        self.stats["batches"] += 1
        return "ok"
