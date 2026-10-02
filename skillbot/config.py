"""Configuration loaded from config.yaml (see config.example.yaml)."""
from dataclasses import dataclass, field, fields
from pathlib import Path

import yaml

from .colors import Registry, collisions, resolve_config
from .layout import Layout
from .skills import SKILLS

TASKS = ("gather", "process", "firemaking", "combat", "runecraft", "cast", "agility",
         "construction", "thieve", "routine", "quest", "slayer")


def _color(v):
    return None if v is None else tuple(v)


QUANTITIES = ("1", "5", "10", "x", "all")


@dataclass(frozen=True)
class Withdraw:
    """One withdrawal: click ``slot`` (in the open bank tab), after selecting
    ``quantity`` if given; ``item`` (an Inventory Tags name) is checked afterwards."""
    slot: int
    item: str | None = None
    quantity: str | None = None

    @classmethod
    def parse(cls, value) -> "Withdraw":
        if isinstance(value, int):
            return cls(value)
        value = dict(value)
        if "quantity" in value and value["quantity"] is not None:
            value["quantity"] = str(value["quantity"]).lower()
            if value["quantity"] not in QUANTITIES:
                raise ValueError(f"withdraw quantity must be one of {QUANTITIES}")
        return cls(**value)


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
    withdraw: tuple = ()               # Withdraw entries (or plain bank slot numbers), in order
    bank_tab: str | None = None        # Bank Tags tag whose tab holds this step's items
    with_item: str | None = None       # process: use `use_item` on this item (no station)
    location: str | None = None        # destination to travel to when the target isn't in sight
    gear: tuple = ()                   # tagged items to wear again after taking the grave

    # cast (Magic: teleports, alchemy)
    spell: tuple | None = None         # the spell's position in the magic tab
    on_item: str | None = None         # tagged item to cast it on (alchemy); None = no target
    runes: tuple = ()                  # tagged rune stacks the spell needs
    cast_delay: float = 3.0            # seconds per cast
    casts_per_batch: int = 50

    # agility
    obstacles: tuple = ()              # Object Marker colors in course order
    laps_per_batch: int = 5

    # construction (build mode in your house)
    build_key: str = "1"               # the furniture's number in the build menu
    remove_option: int = 2             # "Remove" row in the right-click menu on built furniture
    hotspot: tuple | None = None       # fixed screen point instead of a target color
    bank_location: str | None = None   # destination with a bank, for restocking
    builds_per_batch: int = 20

    # thieving
    pouch: str | None = None           # tagged coin pouch stack, opened every `open_every`
    open_every: int = 25
    attempts_per_batch: int = 100

    # routine (minigames and other scripted activities; see routine_spec.py)
    routine: tuple = ()
    vars: dict = field(default_factory=dict)   # values for {name} in a routine's type: text

    # combat while standing still (crabs)
    stand_on: tuple | None = None      # Ground Marker to stand on
    reset_spot: tuple | None = None    # Ground Marker far enough away to reset aggression
    reset_after: float = 60.0          # seconds without being attacked before resetting
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
    leave_spell: tuple | None = None   # teleport out instead of a portal (Ourania altar)

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
        if d.get("spell") is not None:
            d["spell"] = tuple(d["spell"])
        for key in ("hotspot", "stand_on", "reset_spot", "leave_spell"):
            if d.get(key) is not None:
                d[key] = tuple(d[key])
        if "build_key" in d:
            d["build_key"] = str(d["build_key"])
        if "obstacles" in d:
            d["obstacles"] = tuple(tuple(c) for c in d["obstacles"])
        if "routine" in d:
            d["routine"] = tuple(d["routine"])
        for key in ("items", "confirm", "withdraw", "food", "bury", "keep", "gear", "runes"):
            if key in d:
                d[key] = tuple(d[key])
        if "withdraw" in d:
            d["withdraw"] = tuple(Withdraw.parse(w) for w in d["withdraw"])
        step = cls(**d)
        if step.skill not in SKILLS:
            raise ValueError(f"step {step.name!r}: unknown skill {step.skill!r}")
        if step.task not in TASKS:
            raise ValueError(f"step {step.name!r}: task must be one of {TASKS}")
        if step.with_item and (step.task != "process" or not step.use_item):
            raise ValueError(f"step {step.name!r}: with_item needs task: process and a use_item")
        if step.task == "cast" and step.spell is None:
            raise ValueError(f"step {step.name!r}: cast needs the spell's position")
        if step.task == "agility" and len(step.obstacles) < 2:
            raise ValueError(f"step {step.name!r}: agility needs the obstacle colors in order")
        if step.task == "routine":
            from .routine_spec import check_routine
            check_routine(list(step.routine), step.name)
        if step.task == "construction" and step.target is None and step.hotspot is None:
            raise ValueError(f"step {step.name!r}: construction needs a target color or hotspot")
        if step.target is None and not step.with_item and step.task not in (
                "cast", "agility", "construction", "routine", "quest", "slayer"):
            raise ValueError(f"step {step.name!r}: needs a target highlight color")
        if step.when_full not in ("drop", "bank"):
            raise ValueError(f"step {step.name!r}: when_full must be drop or bank")
        if step.when_out_of_food not in ("bank", "stop"):
            raise ValueError(f"step {step.name!r}: when_out_of_food must be bank or stop")
        if step.task == "runecraft" and (step.ruins is None
                                         or (step.portal is None and step.leave_spell is None)):
            raise ValueError(f"step {step.name!r}: runecraft needs ruins and a portal color "
                             "(or a leave_spell)")
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
    danger_color: tuple | None = None   # NPC Indicators on random-event NPCs: never clicked
    genie_color: tuple | None = None    # NPC Indicators on the Genie (its lamp is claimed)
    respawn_color: tuple | None = None  # Ground Marker on your respawn tile (death detection)
    grave_color: tuple | None = None    # NPC Indicators on "Grave"
    other_player_color: tuple | None = None   # Player Indicators: other players (hopping)
    safety: dict = field(default_factory=dict)      # see safety.SafetyConfig
    colors_file: Path | None = None     # the color registry (default: colors.yaml in the repo)
    hubs: dict = field(default_factory=dict)        # name -> Hub (see navigation.py)
    spells: dict = field(default_factory=dict)      # spell name -> [x, y] in the magic tab
    path_color: tuple = (255, 0, 128)              # Shortest Path's path color
    map_menu_option: int = 1          # which right-click option on the world map is "Set target"
    items: dict = field(default_factory=dict)      # Inventory Tags: name -> RGB
    routes: dict = field(default_factory=dict)     # name -> Ground Marker colors in order
    plan: list = field(default_factory=list)       # list[Step]
    on_logout: str = "stop"                        # stop | relogin
    login_attempts: int = 0                        # 0 = keep trying (server restarts)
    max_consecutive_errors: int = 5
    max_runtime_hours: float = 0                   # 0 = run until the plan is done
    run: str = "always"                            # always | off
    run_min_energy: int = 50                       # switch run back on at this energy %
    run_retry_seconds: float = 60.0                # fallback wait when energy can't be read
    walk_timeout: float = 12.0
    bank_open_wait: float = 4.0
    layout: Layout = field(default_factory=Layout)
    supervisor: dict = field(default_factory=dict)   # see supervisor.SupervisorConfig
    discord: dict = field(default_factory=dict)      # summary_hour (local time, default 9)
    prices: dict = field(default_factory=dict)       # see prices.PriceConfig

    @classmethod
    def load(cls, path) -> "Config":
        raw = yaml.safe_load(Path(path).read_text()) or {}
        registry = Registry.load(raw.get("colors_file"))
        raw = resolve_config(raw, registry)
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
            elif key in ("data_dir", "colors_file"):
                setattr(cfg, key, Path(value))
            elif key in ("danger_color", "genie_color", "respawn_color", "grave_color",
                         "other_player_color"):
                setattr(cfg, key, tuple(value) if value else None)
            elif not hasattr(cfg, key):
                raise ValueError(f"unknown config key: {key}")
            elif key == "spells":
                cfg.spells = {n: tuple(v) for n, v in (value or {}).items()}
            elif key == "hubs":
                from .navigation import Hub
                cfg.hubs = {n: Hub.from_dict(n, h) for n, h in (value or {}).items()}
            elif key == "health_bar_colors":
                cfg.health_bar_colors = tuple(tuple(c) for c in value)
            elif isinstance(getattr(cfg, key), tuple):
                setattr(cfg, key, tuple(value))
            else:
                setattr(cfg, key, value)
        cfg.validate()
        return cfg

    def scene(self, step: Step) -> dict:
        """Every highlight color that can be on screen while ``step`` runs."""
        scene = {"target": step.target, "bank": self.bank_color, "loot": step.loot,
                 "ruins": step.ruins, "portal": step.portal, "danger": self.danger_color,
                 "genie": self.genie_color, "grave": self.grave_color,
                 "respawn": self.respawn_color, "other players": self.other_player_color,
                 "stand on": step.stand_on, "reset spot": step.reset_spot}
        if step.process and step.process.get("target"):
            scene["process target"] = tuple(step.process["target"])
        for i, color in enumerate(dict.fromkeys(step.obstacles)):
            scene[f"obstacle {i + 1}"] = color
        for role, route in step.walk.items():
            for i, tile in enumerate(self.routes.get(route, [])):
                scene[f"route {route} tile {i + 1}"] = tile
        # the same route tile used for two roles is one tile, not a clash
        seen, unique = {}, {}
        for label, color in scene.items():
            if color is None:
                continue
            key = tuple(color)
            if key in seen and seen[key].startswith("route") and label.startswith("route"):
                continue
            seen.setdefault(key, label)
            unique[label] = key
        return unique

    def validate(self) -> None:
        if self.run not in ("always", "off"):
            raise ValueError("run must be always or off")
        if not 1 <= self.run_min_energy <= 100:
            raise ValueError("run_min_energy must be 1-100")
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
            names += [step.with_item] if step.with_item else []
            names += [w.item for w in step.withdraw if w.item]
            names += list(step.gear) + list(step.runes)
            names += [step.on_item] if step.on_item else []
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
            scene = self.scene(step)
            clashes = collisions(scene, self.color_tolerance)
            if clashes:
                pairs = ", ".join(f"{a} / {b}" for a, b in clashes)
                raise ValueError(f"step {step.name!r}: colors on screen together are too "
                                 f"similar: {pairs}")
            for route in step.walk.values():
                if route not in self.routes:
                    raise ValueError(f"step {step.name!r}: unknown route {route!r}")
