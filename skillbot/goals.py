"""Goals and the planner's choice of what to train next.

goals.yaml (next to config.yaml):

    unlocks_first:            # trained in this order, before anything else
      magic: 45
      agility: 50
    then: all_99              # afterwards: every skill to 99 (or a dict of targets)
    exclude: [sailing, farming]
    overrides: {woodcutting: willows_draynor}   # always use this method for a skill
    rotation_minutes: 120     # time slice per skill once the unlocks are done

Choosing: the first unmet unlock goal with a usable method; after that, the skill with
the most hours left to its target. For the chosen skill, the usable method that is most
reliable, then most profitable, then fastest. `python -m skillbot plan --explain` shows
the reasoning.
"""
import json
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .skills import SKILLS
from .xp import xp_between


@dataclass
class Goals:
    unlocks: dict = field(default_factory=dict)
    targets: dict = field(default_factory=dict)        # skill -> level after the unlocks
    exclude: set = field(default_factory=set)
    overrides: dict = field(default_factory=dict)
    rotation_minutes: float = 120

    @classmethod
    def load(cls, path: Path) -> "Goals":
        raw = yaml.safe_load(Path(path).read_text()) or {}
        unknown = set(raw) - {"unlocks_first", "then", "exclude", "overrides", "rotation_minutes"}
        if unknown:
            raise ValueError(f"goals.yaml: unknown keys {sorted(unknown)}")
        then = raw.get("then", "all_99")
        exclude = set(raw.get("exclude") or [])
        if then == "all_99":
            targets = {s: 99 for s in SKILLS if s not in exclude}
        elif isinstance(then, dict):
            targets = dict(then)
        else:
            raise ValueError("goals.yaml: then must be all_99 or a dict of skill: level")
        unlocks = dict(raw.get("unlocks_first") or {})
        for name in list(unlocks) + list(targets) + list(raw.get("overrides") or {}):
            if name not in SKILLS:
                raise ValueError(f"goals.yaml: unknown skill {name!r}")
        return cls(unlocks, targets, exclude, dict(raw.get("overrides") or {}),
                   float(raw.get("rotation_minutes", 120)))


def fmt_hours(hours: float) -> str:
    if hours == float("inf"):
        return "unknown time"
    return f"{hours * 60:.0f} min" if hours < 1 else f"{hours:.0f}h"


class QuestLog:
    def __init__(self, path: Path | None):
        self.path = Path(path) if path else None
        self.done = set(json.loads(self.path.read_text())) if self.path and self.path.exists() \
            else set()

    def add(self, name: str) -> None:
        self.done.add(name)
        if self.path:
            self.path.write_text(json.dumps(sorted(self.done), indent=1))

    def has(self, name: str) -> bool:
        return name.lower() in {q.lower() for q in self.done}


@dataclass
class Decision:
    skill: str
    method: object
    step: object
    phase: str
    target: int
    hours_left: float


class Chooser:
    def __init__(self, goals: Goals, library: dict, cfg, registry, quests: QuestLog,
                 trust=None, supervised: bool = False, clock=None, prices=None):
        self.goals = goals
        self.library = library
        self.cfg = cfg
        self.registry = registry
        self.quests = quests
        self.trust = trust
        self.supervised = supervised
        self.cooldown = {}            # method id -> time it may be tried again
        self.prices = prices          # Prices: live profit for methods with a trade
        self.clock = clock

    # ---- eligibility -------------------------------------------------------------------
    def check(self, method, skill: str, levels: dict, now: float = 0.0):
        """(step, None) if the method can be used now, else (None, reason)."""
        lvl = levels.get(skill, 1)
        lo, hi = method.levels
        if not lo <= lvl < hi:
            return None, f"for levels {lo}-{hi}"
        for s, need in method.requires_levels.items():
            if levels.get(s, 1) < need:
                return None, f"needs {s} {need}"
        for quest in method.requires_quests:
            if not self.quests.has(quest):
                return None, f"needs quest {quest!r} (`quest-done` once finished)"
        if self.cooldown.get(method.id, 0) > now:
            return None, "out of supplies recently"
        try:
            step = method.to_step(skill, hi, 0, self.registry)
        except ValueError as e:
            return None, f"not set up: {e}"
        missing = [n for n in list(step.items) + list(step.food) + list(step.bury)
                   + list(step.keep) + [w.item for w in step.withdraw if w.item]
                   + ([step.enter_with] if step.enter_with else [])
                   if n not in self.cfg.items]
        if missing:
            return None, f"Inventory Tags missing for {', '.join(sorted(set(missing)))}"
        if self.trust is not None and not self.supervised \
                and self.trust.level(step.name) == "experimental":
            return None, "experimental (run it supervised first)"
        return step, None

    def candidates(self, skill: str, levels: dict, now: float = 0.0):
        """[(method, step or None, reason or None)], best first."""
        methods = [m for m in self.library.values() if skill in m.skills]
        if skill in self.goals.overrides:
            methods = [m for m in methods if m.id == self.goals.overrides[skill]]
        methods.sort(key=lambda m: (-m.reliability, -self.profit(m), -m.xp_per_hour, m.id))
        return [(m, *self.check(m, skill, levels, now)) for m in methods]

    def profit(self, method) -> float:
        """Live profit per hour when prices and a trade are known, else the estimate."""
        if self.prices is not None and method.trade:
            live = self.prices.profit_per_hour(method.trade)
            if live is not None:
                return live
        return method.profit_per_hour

    def best(self, skill: str, levels: dict, now: float = 0.0):
        for method, step, reason in self.candidates(skill, levels, now):
            if step is not None:
                return method, step
        return None, None

    # ---- choosing ----------------------------------------------------------------------
    def next(self, levels: dict, now: float = 0.0) -> Decision | None:
        for skill, goal in self.goals.unlocks.items():
            if levels.get(skill, 1) >= goal:
                continue
            method, step = self.best(skill, levels, now)
            if method:
                return self._decide(skill, method, goal, "unlock", levels, slice_minutes=0)
        options = []
        for skill, goal in self.goals.targets.items():
            if skill in self.goals.exclude or levels.get(skill, 1) >= goal:
                continue
            method, step = self.best(skill, levels, now)
            if method and method.xp_per_hour > 0:
                hours = xp_between(levels.get(skill, 1), goal) / method.xp_per_hour
                options.append((hours, skill, method, goal))
        if not options:
            return None
        hours, skill, method, goal = max(options, key=lambda o: (o[0], o[1]))
        return self._decide(skill, method, goal, "rotation", levels,
                            slice_minutes=self.goals.rotation_minutes)

    def _decide(self, skill, method, goal, phase, levels, slice_minutes) -> Decision:
        until = min(goal, method.levels[1])
        step = method.to_step(skill, until, slice_minutes, self.registry)
        hours = xp_between(levels.get(skill, 1), until) / method.xp_per_hour \
            if method.xp_per_hour else float("inf")
        return Decision(skill, method, step, phase, until, hours)

    def rest(self, method_id: str, until: float) -> None:
        """Don't pick this method again before ``until`` (e.g. it ran out of supplies)."""
        self.cooldown[method_id] = until

    # ---- explaining --------------------------------------------------------------------
    def explain(self, levels: dict, now: float = 0.0) -> str:
        d = self.next(levels, now)
        lines = []
        if d is None:
            lines.append("Nothing to train right now with the methods available.")
            if self.trust is not None and not self.supervised:
                lines.append("  (methods only run unattended once trusted: try them first with "
                             "`run --supervised`, which also uses experimental methods)")
        else:
            lines.append(f"Next: {d.skill} {levels.get(d.skill, 1)} → {d.target} with "
                         f"{d.method.name!r} ({d.phase}"
                         + (f", {self.goals.rotation_minutes:.0f}-minute slice" if d.phase == "rotation" else "")
                         + f"), about {fmt_hours(d.hours_left)} of training")
            lines.append("  because: " + (
                "it's the first unmet unlock goal with a usable method" if d.phase == "unlock"
                else "all unlock goals are met (or blocked) and it has the most hours left"))
        lines.append("")
        lines.append("Unlock goals:")
        for skill, goal in self.goals.unlocks.items():
            mark = "✓" if levels.get(skill, 1) >= goal else "…"
            lines.append(f"  {mark} {skill} {levels.get(skill, 1)}/{goal}")
        lines.append("")
        lines.append("Skills:")
        for skill in SKILLS:
            if skill in self.goals.exclude:
                continue
            goal = self.goals.targets.get(skill)
            if goal is None and skill not in self.goals.unlocks:
                continue
            cands = self.candidates(skill, levels, now)
            if not cands:
                lines.append(f"  {skill} {levels.get(skill, 1)}: no method in the library yet")
                continue
            parts = []
            for m, step, reason in cands:
                tag = "✓" if step is not None else f"✗ {reason}"
                parts.append(f"{m.name} [{tag}; r{m.reliability}, {self.profit(m)/1000:+.0f}k gp/h, "
                             f"{m.xp_per_hour/1000:.0f}k xp/h]")
            lines.append(f"  {skill} {levels.get(skill, 1)}: " + "; ".join(parts))
        return "\n".join(lines)
