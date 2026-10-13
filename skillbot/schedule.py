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
      - method: auto              # the best method for the skill at your level right now
        skill: mining             # (moves up the ladder as you level; tries the next best
        minutes: 45               #  when one can't run: out of supplies, not trusted yet)

Rules: the method's own upper level is ignored (manual: keep doing it), its lower level
is enforced. An entry that can't start or runs out early is skipped with a notification
and the schedule moves on. Repeat `once` logs out after the last entry; `{hours: N}`
cycles until the time is up (finishing the current inventory), then logs out.
"""
import json
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
AUTO = "auto"
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
            if e.method == AUTO:
                if e.skill not in SKILLS:
                    raise ValueError(f"entry {i}: method auto needs a skill")
                e.minutes = float(e.minutes or 0)
                if e.until_level is not None and not 2 <= int(e.until_level) <= 99:
                    raise ValueError(f"entry {i}: until_level must be 2-99")
                if e.when_full not in (None, "bank", "drop"):
                    raise ValueError(f"entry {i}: when_full must be bank or drop")
                entries.append(e)
                continue
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


BUILTIN = Path(__file__).resolve().parent.parent / "library" / "schedules"


class Store:
    """Saved schedules: one YAML file per name in schedules/, shared by all accounts.
    ``builtin`` holds the ones that come with the bot (library/schedules); saving one
    under the same name makes your own copy, which wins."""

    def __init__(self, folder: Path, builtin: Path | None = None):
        self.folder = Path(folder)
        self.builtin = Path(builtin) if builtin else None

    def path(self, name: str) -> Path:
        if not NAME.match(name or ""):
            raise ValueError("schedule names: letters, digits, spaces, - and _ (up to 40)")
        return self.folder / f"{name}.yaml"

    def find(self, name: str) -> Path:
        path = self.path(name)
        if not path.exists() and self.builtin is not None \
                and (self.builtin / path.name).exists():
            return self.builtin / path.name
        return path

    def names(self) -> list[str]:
        names = set()
        for folder in (self.folder, self.builtin):
            if folder is not None and folder.is_dir():
                names |= {p.stem for p in folder.glob("*.yaml")}
        return sorted(names)

    def load(self, name: str, library: dict) -> Schedule:
        path = self.find(name)
        if not path.exists():
            raise ValueError(f"no schedule {name!r} (have: {', '.join(self.names()) or 'none'})")
        return Schedule.from_dict(yaml.safe_load(path.read_text()), library)

    def raw(self, name: str) -> dict:
        return yaml.safe_load(self.find(name).read_text()) or {}

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
                 label: str = "schedule", resume: Path | None = None) -> None:
    """Run the entries in order (and again, per ``repeat``); log out at the end.

    With ``resume`` (a file), the entry being run is remembered, so a run stopped part way
    (an account handover, a restart) starts again at that entry instead of the first."""
    g = planner.game
    skills = {e.skill or library[e.method].skills[0] for e in schedule.entries}
    planner._guard(lambda: planner.resync(sorted(skills, key=SKILLS.index)))
    end = g.now() + schedule.hours * 3600 if schedule.repeat == "hours" else None
    key = json.dumps(schedule.to_dict(), sort_keys=True)
    start = _resume_at(resume, key, len(schedule.entries))
    if start:
        log.info("%s: carrying on at entry %d", label, start + 1)
    passes = 0
    while True:
        passes += 1
        worked = False
        for i, entry in enumerate(schedule.entries, 1):
            if i <= start:
                continue
            _remember(resume, key, i - 1, label, len(schedule.entries))
            if end is not None and g.now() >= end:
                return _finish(planner, TIME_UP, resume)
            where = f"{label} {i}/{len(schedule.entries)}"
            if entry.method == AUTO:
                worked |= _run_auto(planner, entry, library, registry, spells, end, where)
            else:
                worked |= _run_entry(planner, entry, library[entry.method], registry, spells,
                                     end, where)
        if start:
            start, worked = 0, True        # the resumed pass was a partial one
        if schedule.repeat == "once":
            return _finish(planner, DONE, resume)
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
    why = method.blocked(g.cfg.account, planner.levels.levels)
    if why:
        planner.notify(f"{where}: skipping {method.name}: {why}")
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


def auto_candidates(library: dict, skill: str, levels: dict, account: str) -> list:
    """Methods for ``skill`` usable at these levels, best XP first: in their level range
    (the upper level is where the next one takes over), allowed for the account, and
    giving XP (tanning, essence mining are only supplies)."""
    level = levels.get(skill, 1)
    found = [m for m in library.values()
             if skill in m.skills and m.xp_per_hour > 0
             and m.levels[0] <= level < max(m.levels[1], m.levels[0] + 1)
             and not m.blocked(account, levels)]
    return sorted(found, key=lambda m: (-m.xp_per_hour, m.id))


def _run_auto(planner, entry: Entry, library, registry, spells, end, where) -> bool:
    """An auto entry: the best method that actually runs (out of supplies, not trusted
    yet or can't start: the next best)."""
    levels = planner.levels.levels
    if levels.get(entry.skill, 1) >= (entry.until_level or NEVER):
        return False
    tried = auto_candidates(library, entry.skill, levels, planner.game.cfg.account)
    if not tried:
        log.info("%s: no method for %s %d", where, entry.skill, levels.get(entry.skill, 1))
    for method in tried:
        until = min(entry.until_level or NEVER,
                    method.levels[1] if method.levels[1] < 99 else NEVER)
        e = Entry(method.id, entry.minutes, until,
                  entry.when_full if method.can_drop else None, entry.skill)
        try:
            if _run_entry(planner, e, method, registry, spells, end, where):
                return True
        except ValueError as err:          # e.g. a spell that hasn't been taught
            log.info("%s: %s can't run: %s", where, method.name, err)
    return False


def _resume_at(path: Path | None, key: str, n: int) -> int:
    """The entry (0-based) a stopped run of this same schedule was on, else 0."""
    try:
        saved = json.loads(Path(path).read_text()) if path else {}
    except (OSError, ValueError):
        return 0
    return saved.get("entry", 0) if saved.get("schedule") == key and saved.get("entry", 0) < n \
        else 0


def _remember(path: Path | None, key: str, entry: int, label: str = "", total: int = 0) -> None:
    if path:
        Path(path).write_text(json.dumps({"schedule": key, "entry": entry, "name": label,
                                          "total": total}))


def _finish(planner, reason: str, resume: Path | None = None) -> None:
    if resume:
        Path(resume).unlink(missing_ok=True)       # done: next time starts from the top
    log.info("%s: logging out", reason)
    if planner.session is not None and not planner.session.logout():
        log.warning("couldn't log out")
    raise StopBot(reason)
