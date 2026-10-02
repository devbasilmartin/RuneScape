"""The color registry: every highlight color has one name and one meaning.

colors.yaml (at the top of the repo, shared by all accounts because they share the
RuneLite `bot` profile) maps names to RGB and a category. Anywhere config.yaml takes a
color you can write a registry name instead of [r, g, b]. Config validation then checks
that colors which can appear on screen together are far enough apart.

`python -m skillbot colors` lists the registry and the free palette colors that are
safe to add.
"""
from dataclasses import dataclass
from itertools import combinations, product
from pathlib import Path

import yaml

REPO_DIR = Path(__file__).resolve().parent.parent
DEFAULT_FILE = REPO_DIR / "colors.yaml"
CATEGORIES = ("resource", "station", "bank", "enemy", "loot", "danger", "route", "portal",
              "item", "other")
HEALTH_BARS = ((0, 255, 0), (255, 0, 0))


def gap(a, b) -> int:
    return max(abs(int(x) - int(y)) for x, y in zip(a, b))


def distinct(a, b, tolerance: int) -> bool:
    """Two colors can't be confused if some channel differs by more than 2x tolerance."""
    return gap(a, b) > 2 * tolerance


def collisions(colors: dict, tolerance: int) -> list[tuple[str, str]]:
    """Pairs of labels whose colors are too similar (identical colors under two labels
    are reported too: one color must mean one thing in a scene)."""
    items = [(k, tuple(v)) for k, v in colors.items() if v is not None]
    return [(a, b) for (a, ca), (b, cb) in combinations(items, 2) if not distinct(ca, cb, tolerance)]


def palette(tolerance: int = 25) -> list[tuple[int, int, int]]:
    """Colors safe as highlights: saturated (not grey, which the game's interface uses),
    not dark (shadows), and away from the game's own health bars."""
    levels = (0, 64, 128, 192, 255)
    out = []
    for c in product(levels, repeat=3):
        if max(c) < 192 or max(c) - min(c) < 128:
            continue
        if any(not distinct(c, bar, tolerance) for bar in HEALTH_BARS):
            continue
        out.append(c)
    return out


@dataclass(frozen=True)
class Entry:
    name: str
    rgb: tuple
    category: str


class Registry:
    def __init__(self, entries: dict[str, Entry] | None = None, path: Path | None = None):
        self.entries = dict(entries or {})
        self.path = path

    @classmethod
    def load(cls, path: Path | None = None) -> "Registry":
        path = Path(path or DEFAULT_FILE)
        if not path.exists():
            return cls(path=path)
        raw = yaml.safe_load(path.read_text()) or {}
        entries = {}
        for name, spec in raw.items():
            if isinstance(spec, list):
                spec = {"rgb": spec}
            category = spec.get("category", "other")
            if category not in CATEGORIES:
                raise ValueError(f"colors.yaml: {name}: unknown category {category!r}")
            rgb = tuple(spec["rgb"])
            if len(rgb) != 3 or not all(0 <= v <= 255 for v in rgb):
                raise ValueError(f"colors.yaml: {name}: rgb must be three numbers 0-255")
            entries[name] = Entry(name, rgb, category)
        return cls(entries, path)

    def resolve(self, value):
        """A config color value: [r, g, b] or a registry name. None stays None."""
        if value is None:
            return None
        if isinstance(value, str):
            if value not in self.entries:
                raise ValueError(f"unknown color name {value!r}; add it to colors.yaml "
                                 "(`python -m skillbot colors` lists free colors)")
            return self.entries[value].rgb
        return tuple(value)

    def name_of(self, rgb, item: bool = False) -> str | None:
        """The registry name for a color, preferring item names for Inventory Tags and
        world-highlight names otherwise (the two may reuse a color)."""
        matches = [e for e in self.entries.values() if e.rgb == tuple(rgb)]
        matches.sort(key=lambda e: (e.category == "item") != item)
        return matches[0].name if matches else None

    def free_color(self, category: str, tolerance: int = 25):
        """A color not confusable with any registry color it could meet."""
        in_inventory = category == "item"
        taken = [e.rgb for e in self.entries.values() if (e.category == "item") == in_inventory]
        if in_inventory:
            levels = (0, 64, 128, 192, 255)
            options = [c for c in product(levels, repeat=3) if max(c) >= 128]
        else:
            options = palette(tolerance)
        for c in options:
            if all(distinct(c, t, tolerance) for t in taken):
                return c
        return None

    def add(self, name: str, category: str, tolerance: int = 25) -> tuple:
        """Append a new name with a free color to colors.yaml."""
        if name in self.entries:
            raise ValueError(f"{name} is already in the registry")
        if category not in CATEGORIES:
            raise ValueError(f"category must be one of {CATEGORIES}")
        rgb = self.free_color(category, tolerance)
        if rgb is None:
            raise ValueError(f"no free {category} colors left")
        self.entries[name] = Entry(name, rgb, category)
        if self.path:
            with open(self.path, "a") as f:
                f.write(f"{name + ':':<16} {{rgb: [{rgb[0]}, {rgb[1]}, {rgb[2]}], "
                        f"category: {category}}}\n")
        return rgb

    def check(self, tolerance: int) -> list[str]:
        """Problems within the registry itself (two names for confusable colors)."""
        problems = []
        # Inventory Tags colors only meet each other in the inventory; everything else
        # (highlights in the game world) only meets other world highlights.
        for in_inventory in (True, False):
            group = {n: e.rgb for n, e in self.entries.items()
                     if (e.category == "item") == in_inventory}
            for a, b in collisions(group, tolerance):
                problems.append(f"{a} and {b} are too similar")
        return problems


STEP_COLOR_KEYS = ("target", "loot", "ruins", "portal", "stand_on", "reset_spot")


def resolve_config(raw: dict, registry: Registry) -> dict:
    """Replace registry names in a raw config dict with RGB lists."""
    raw = dict(raw)
    r = registry.resolve
    for key in ("bank_color", "hp_bar_color", "danger_color", "path_color", "genie_color",
                "respawn_color", "grave_color", "other_player_color"):
        if key in raw:
            raw[key] = r(raw[key])
    if "health_bar_colors" in raw:
        raw["health_bar_colors"] = [r(c) for c in raw["health_bar_colors"]]
    if "items" in raw:
        items = raw["items"] or {}
        if isinstance(items, list):            # just names: each is its own registry color
            items = {n: n for n in items}
        raw["items"] = {n: r(c) for n, c in items.items()}
    if "routes" in raw:
        raw["routes"] = {n: [r(c) for c in cs] for n, cs in (raw["routes"] or {}).items()}
    if isinstance(raw.get("hubs"), dict):
        raw["hubs"] = {n: {**h, "marker": r(h.get("marker"))} if isinstance(h, dict) else h
                       for n, h in raw["hubs"].items()}
    steps = []
    for step in raw.get("plan") or []:
        step = dict(step)
        for key in STEP_COLOR_KEYS:
            if key in step:
                step[key] = r(step[key])
        if "obstacles" in step:
            step["obstacles"] = [r(c) for c in step["obstacles"]]
        if isinstance(step.get("process"), dict) and "target" in step["process"]:
            step["process"] = {**step["process"], "target": r(step["process"]["target"])}
        steps.append(step)
    if "plan" in raw:
        raw["plan"] = steps
    return raw
