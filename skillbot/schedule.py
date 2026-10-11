"""Schedules: run library methods in order, each for a time and/or to a level
(docs/schedules.md). A quick "one activity" run is a schedule with one entry.

schedules/<name>.yaml (shared by every account):

    repeat: once                  # once | forever | {hours: 4}
    entries:
      - method: oaks_draynor      # a method id from library/*.yaml
        minutes: 60               # optional: then the next entry
        until_level: 30           # optional: then the next entry (whichever comes first)
        when_full: bank           # optional, gathering/combat: bank | drop (default: the method's)
      - method: burn_willows
        minutes: 30

Rules: the method's own upper level is ignored (manual: keep doing it), its lower level
is enforced. An entry that can't start or runs out early is skipped with a notification
and the schedule moves on. Repeat `once` logs out after the last entry; `{hours: N}`
cycles until the time is up (finishing the current inventory), then logs out.
"""
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .game import StopBot
from .skills import SKILLS

log = logging.getLogger("skillbot")
NEVER = 100                     # until_level that no skill reaches: "keep doing it"
NAME = re.compile(r"^[A-Za-z0-9 _-]{1,40}$")
DONE = "schedule complete"
TIME_UP = "schedule time is up"


@dataclass
class Entry:
    method: str
    minutes: float = 0                  # 0: no time limit
    until_level: int | None = None
    when_full: str | None = None        # None: the method's own choice
    skill: str | None = None            # for methods training several skills (cows)

    def to_dict(self) -> dict:
        d = {"method": self.method}
        for key in ("minutes", "until_level", "when_full", "skill"):
            value = getattr(self, key)
            if value:
                d[key] = value
        return d


@dataclass
class Schedule:
    entries: list = field(default_factory=list)
    repeat: str = "once"                # once | forever | hours
    hours: float = 0

    @classmethod
    def from_dict(cls, d: dict, library: dict) -> "Schedule":
        d = dict(d or {})
        unknown = set(d) - {"repeat", "entries"}
        if unknown:
            raise ValueError(f"schedule: unknown keys {sorted(unknown)}")
        repeat, hours = d.get("repeat", "once"), 0.0
        if isinstance(repeat, dict):
            hours = float(repeat.get("hours", 0))
            if set(repeat) != {"hours"} or hours <= 0:
                raise ValueError("schedule: repeat must be once, forever or {hours: N}")
            repeat = "hours"
        elif repeat not in ("once", "forever"):
            raise ValueError("schedule: repeat must be once, forever or {hours: N}")
        entries = []
        for i, raw in enumerate(d.get("entries") or [], 1):
            raw = dict(raw)
            extra = set(raw) - {"method", "minutes", "until_level", "when_full", "skill"}
            if extra:
                raise ValueError(f"entry {i}: unknown keys {sorted(extra)}")
            e = Entry(**raw)
            m = library.get(e.method)
            if m is None:
                raise ValueError(f"entry {i}: no method {e.method!r} in the library")
            e.minutes = float(e.minutes or 0)
            if e.minutes < 0:
                raise ValueError(f"entry {i}: minutes can't be negative")
            if e.until_level is not None and not 2 <= int(e.until_level) <= 99:
                raise ValueError(f"entry {i}: until_level must be 2-99")
            if e.when_full is not None:
                if e.when_full not in ("bank", "drop"):
                    raise ValueError(f"entry {i}: when_full must be bank or drop")
                if not m.can_drop:
                    raise ValueError(f"entry {i}: {m.name} always banks (only gathering and "
                                     "combat can choose bank or drop)")
            if e.skill is not None and e.skill not in m.skills:
                raise ValueError(f"entry {i}: {m.name} trains {', '.join(m.skills)}")
            entries.append(e)
        if not entries:
            raise ValueError("schedule: add at least one entry")
        return cls(entries, repeat, hours)

    def to_dict(self) -> dict:
        repeat = {"hours": self.hours} if self.repeat == "hours" else self.repeat
        return {"repeat": repeat, "entries": [e.to_dict() for e in self.entries]}


class Store:
    """Saved schedules: one YAML file per name in schedules/, shared by all accounts."""

    def __init__(self, folder: Path):
        self.folder = Path(folder)

    def path(self, name: str) -> Path:
        if not NAME.match(name or ""):
            raise ValueError("schedule names: letters, digits, spaces, - and _ (up to 40)")
        return self.folder / f"{name}.yaml"

    def names(self) -> list[str]:
        return sorted(p.stem for p in self.folder.glob("*.yaml")) if self.folder.is_dir() else []

    def load(self, name: str, library: dict) -> Schedule:
        path = self.path(name)
        if not path.exists():
            raise ValueError(f"no schedule {name!r} (have: {', '.join(self.names()) or 'none'})")
        return Schedule.from_dict(yaml.safe_load(path.read_text()), library)

    def raw(self, name: str) -> dict:
        return yaml.safe_load(self.path(name).read_text()) or {}

    def save(self, name: str, schedule: Schedule) -> Path:
        path = self.path(name)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(yaml.safe_dump(schedule.to_dict(), sort_keys=False))
        return path

    def delete(self, name: str) -> None:
        self.path(name).unlink(missing_ok=True)


def step_name(method, skill: str, when_full: str | None) -> str:
    """The plan-step name an entry runs under (trust is kept per name)."""
    name = method.name + (f" ({skill})" if len(method.skills) > 1 else "")
    if when_full and when_full != method.step.get("when_full"):
        name += f" [{when_full}]"
    return name


def entry_step(entry: Entry, method, registry, spells):
    """The plan step for an entry. A bank/drop choice other than the method's own gets
    its own name, so its trust is earned separately (banking is new behaviour)."""
    skill = entry.skill or method.skills[0]
    overrides = {}
    if entry.when_full and entry.when_full != method.step.get("when_full"):
        overrides["when_full"] = entry.when_full
    if entry.when_full == "drop" and method.task == "combat":
        overrides["when_out_of_food"] = "stop"     # no bank trips: out of food ends it
    step = method.to_step(skill, entry.until_level or NEVER, entry.minutes, registry, spells,
                          overrides)
    step.name = step_name(method, skill, entry.when_full)
    return step


def run_schedule(planner, schedule: Schedule, library: dict, registry, spells,
                 label: str = "schedule") -> None:
    """Run the entries in order (and again, per ``repeat``); log out at the end."""
    g = planner.game
    skills = {e.skill or library[e.method].skills[0] for e in schedule.entries}
    planner._guard(lambda: planner.resync(sorted(skills, key=SKILLS.index)))
    end = g.now() + schedule.hours * 3600 if schedule.repeat == "hours" else None
    passes = 0
    while True:
        passes += 1
        worked = False
        for i, entry in enumerate(schedule.entries, 1):
            if end is not None and g.now() >= end:
                return _finish(planner, TIME_UP)
            worked |= _run_entry(planner, entry, library[entry.method], registry, spells,
                                 end, f"{label} {i}/{len(schedule.entries)}")
        if schedule.repeat == "once":
            return _finish(planner, DONE)
        if not worked:
            raise StopBot(f"nothing in the {label} could run (out of supplies everywhere?)")


def _run_entry(planner, entry: Entry, method, registry, spells, end, where) -> bool:
    """Run one entry; True if it got anything done. Skips (with a notification) when it
    can't start, and notes when it ran out before its time was up."""
    g = planner.game
    step = entry_step(entry, method, registry, spells)
    level, need = planner.levels.get(step.skill), method.levels[0]
    if level < need:
        planner.notify(f"{where}: skipping {method.name}: needs {step.skill} {need} "
                       f"(you have {level})")
        return False
    if planner.done(step):
        log.info("%s: %s already at %s %d", where, method.name, step.skill, step.until_level)
        return False
    if not planner.allowed(step):            # experimental and unattended: skipped (notified)
        return False
    log.info("%s: %s%s%s", where, method.name,
             f" for {entry.minutes:g} min" if entry.minutes else "",
             f" until {step.skill} {entry.until_level}" if entry.until_level else "")
    started = g.now()
    batches = planner.run_step(step, end)
    ran = (g.now() - started) / 60
    out_early = entry.minutes and ran < entry.minutes - 1 and not planner.done(step) \
        and not (end is not None and g.now() >= end)
    if batches == 0:
        planner.notify(f"{where}: {method.name} couldn't get started (supplies? setup?); "
                       "moving on")
    elif out_early:
        planner.notify(f"{where}: {method.name} ran out after {ran:.0f} of "
                       f"{entry.minutes:g} min; moving on")
    return batches > 0


def _finish(planner, reason: str) -> None:
    log.info("%s: logging out", reason)
    if planner.session is not None and not planner.session.logout():
        log.warning("couldn't log out")
    raise StopBot(reason)
