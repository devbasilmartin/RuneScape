"""Configuration loaded from config.yaml (see config.example.yaml)."""
from dataclasses import dataclass, field, fields
from pathlib import Path

import yaml

from .layout import Layout
from .skills import SKILLS

TASKS = ("gather", "process", "firemaking", "combat", "runecraft")


def _color(v):
    return None if v is None else tuple(v)


@dataclass
class Step:
    """One entry of the plan: train ``skill`` with one method until ``until_level``."""
    name: str
    skill: str
    task: str
    until_level: int = 99
    max_minutes: float = 0             # 0 = no time limit; otherwise rotate to the next step
    target: tuple | None = None        # highlight color: resource, station, or start tile
    items: tuple = ()                  # gather: products; process/firemaking: inputs used up
    when_full: str = "bank"            # gather: drop | bank
    use_item: str | None = None        # process: click this item before the station
    confirm: tuple = ({"key": "space"},)   # process: keys/clicks after the menu opens
    withdraw: tuple = ()               # bank slot indices to left-click, in order
    process: dict | None = None        # gather: process the load before dropping/banking
    tools: int = 1                     # untagged slots always carried
    tool_slot: int = 0                 # firemaking: tinderbox slot
    idle_timeout: float = 20.0         # seconds without progress before clicking again
    walk: dict = field(default_factory=dict)   # "bank"/"target"/"start" -> route name

    # combat
    food: tuple = ()                   # tagged food, eaten when HP drops below eat_below
    eat_below: float = 0.5             # fraction of max HP (Status Bars health bar)
    when_out_of_food: str = "bank"     # bank (restock with `withdraw`) | stop
    loot: tuple | None = None          # Ground Items tile highlight color; None = no looting
    bury: tuple = ()                   # tagged bones to bury (Prayer)
    style: int | None = None           # attack style button 0-3 to select at the start
    cast: tuple | None = None          # spell position in the magic tab, cast on every attack
    kills_per_batch: int = 10          # check levels after this many kills

    # runecraft
    ruins: tuple | None = None         # Object Markers: the Mysterious ruins
    portal: tuple | None = None        # Object Markers: the exit portal inside the altar
    enter_with: str | None = None      # tagged talisman to use on the ruins (None: wear a tiara)
    keep: tuple = ()                   # tagged items never deposited (e.g. that talisman)

    @classmethod
    def from_dict(cls, d: dict) -> "Step":
        names = {f.name for f in fields(cls)}
        unknown = set(d) - names
        if unknown:
            raise ValueError(f"step {d.get('name')!r}: unknown keys {sorted(unknown)}")
        d = dict(d)
        d["target"] = _color(d.get("target"))
        d["loot"] = _color(d.get("loot"))
        d["cast"] = _color(d.get("cast"))
        d["ruins"] = _color(d.get("ruins"))
        d["portal"] = _color(d.get("portal"))
        for key in ("items", "confirm", "withdraw", "food", "bury", "keep"):
            if key in d:
                d[key] = tuple(d[key])
        step = cls(**d)
        if step.skill not in SKILLS:
            raise ValueError(f"step {step.name!r}: unknown skill {step.skill!r}")
        if step.task not in TASKS:
            raise ValueError(f"step {step.name!r}: task must be one of {TASKS}")
        if step.target is None:
            raise ValueError(f"step {step.name!r}: needs a target highlight color")
        if step.when_full not in ("drop", "bank"):
            raise ValueError(f"step {step.name!r}: when_full must be drop or bank")
        if step.when_out_of_food not in ("bank", "stop"):
            raise ValueError(f"step {step.name!r}: when_out_of_food must be bank or stop")
        if step.task == "runecraft" and (step.ruins is None or step.portal is None):
            raise ValueError(f"step {step.name!r}: runecraft needs ruins and portal colors")
        if step.style is not None and step.style not in range(4):
            raise ValueError(f"step {step.name!r}: style must be 0-3")
        return step


@dataclass
class Config:
    data_dir: Path = Path("data")
    color_tolerance: int = 25
    bank_color: tuple = (255, 0, 255)
    health_bar_colors: tuple = ((0, 255, 0), (255, 0, 0))   # the game's own bars over NPCs
    hp_bar_color: tuple = (255, 0, 0)                        # Status Bars health fill
    items: dict = field(default_factory=dict)      # Inventory Tags: name -> RGB
    routes: dict = field(default_factory=dict)     # name -> Ground Marker colors in order
    plan: list = field(default_factory=list)       # list[Step]
    on_logout: str = "stop"                        # stop | relogin
    login_attempts: int = 0                        # 0 = keep trying (server restarts)
    max_consecutive_errors: int = 5
    max_runtime_hours: float = 0                   # 0 = run until the plan is done
    walk_timeout: float = 12.0
    bank_open_wait: float = 4.0
    layout: Layout = field(default_factory=Layout)

    @classmethod
    def load(cls, path) -> "Config":
        raw = yaml.safe_load(Path(path).read_text()) or {}
        cfg = cls()
        for key, value in raw.items():
            if key == "layout":
                cfg.layout = Layout.from_dict(value)
            elif key == "plan":
                cfg.plan = [Step.from_dict(s) for s in value]
            elif key == "items":
                cfg.items = {n: tuple(rgb) for n, rgb in value.items()}
            elif key == "routes":
                cfg.routes = {n: [tuple(c) for c in cs] for n, cs in value.items()}
            elif key == "data_dir":
                cfg.data_dir = Path(value)
            elif not hasattr(cfg, key):
                raise ValueError(f"unknown config key: {key}")
            elif key == "health_bar_colors":
                cfg.health_bar_colors = tuple(tuple(c) for c in value)
            elif isinstance(getattr(cfg, key), tuple):
                setattr(cfg, key, tuple(value))
            else:
                setattr(cfg, key, value)
        cfg.validate()
        return cfg

    def validate(self) -> None:
        if self.on_logout not in ("stop", "relogin"):
            raise ValueError("on_logout must be stop or relogin")
        names = list(self.items)
        for i, a in enumerate(names):
            for b in names[i + 1:]:
                gap = max(abs(x - y) for x, y in zip(self.items[a], self.items[b]))
                if gap <= 2 * self.color_tolerance:
                    raise ValueError(f"item colors for {a} and {b} are too similar; make them "
                                     f"differ by more than {2 * self.color_tolerance} on a channel")
        for step in self.plan:
            names = list(step.items) + list(step.food) + list(step.bury) + list(step.keep)
            names += [step.enter_with] if step.enter_with else []
            names += [step.use_item] if step.use_item not in (None, "any") else []
            names += list((step.process or {}).get("items", []))
            missing = [n for n in names if n not in self.items]
            if missing:
                raise ValueError(f"step {step.name!r}: items {missing} have no tag color")
            if step.task == "combat":
                for color in (step.target, step.loot):
                    if color and any(max(abs(x - y) for x, y in zip(color, bar))
                                     <= 2 * self.color_tolerance
                                     for bar in self.health_bar_colors):
                        raise ValueError(f"step {step.name!r}: {color} is too close to the "
                                         "game's green/red health bars")
            for route in step.walk.values():
                if route not in self.routes:
                    raise ValueError(f"step {step.name!r}: unknown route {route!r}")
