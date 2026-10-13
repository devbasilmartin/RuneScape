"""F2P places by world coordinate (library/places/f2p.yaml) and the world map's scale.

The world map opens centred on you. Knowing the tile you're near and the tile you want,
the place to click is the centre plus the difference in tiles times the map's pixels per
tile (y flipped: the map has north up). The scale is measured once with
`calibrate-map` (data/map.json); it holds as long as you don't zoom the map.
"""
import json
import math
from dataclasses import dataclass, field
from pathlib import Path

import yaml

PLACES_FILE = Path(__file__).resolve().parent.parent / "library" / "places" / "f2p.yaml"


@dataclass
class Move:
    """One click on a highlight (stairs), an optional key (a dialog choice), a wait."""
    click: tuple
    key: str | None = None
    wait: float = 3.0


@dataclass
class Place:
    name: str
    tile: tuple[int, int]
    arrive: list[Move] = field(default_factory=list)
    leave: list[Move] = field(default_factory=list)


def load_places(resolve, path: Path = PLACES_FILE) -> dict[str, Place]:
    """``resolve`` turns a colors.yaml name into [r, g, b] (Registry.resolve)."""
    raw = yaml.safe_load(Path(path).read_text()) or {}
    places = {}
    for name, d in raw.items():
        tile = d.get("tile")
        if not (isinstance(tile, list) and len(tile) == 2):
            raise ValueError(f"library/places/f2p.yaml: {name!r} needs tile: [x, y]")
        moves = {k: [Move(tuple(resolve(m["click"])), m.get("key"), float(m.get("wait", 3)))
                     for m in d.get(k) or []] for k in ("arrive", "leave")}
        places[name] = Place(name, (int(tile[0]), int(tile[1])), **moves)
    return places


def map_offset(here: Place, there: Place, scale: float) -> tuple[int, int]:
    """Pixels from the map's centre (you, at ``here``) to ``there``."""
    return (round((there.tile[0] - here.tile[0]) * scale),
            round(-(there.tile[1] - here.tile[1]) * scale))


def measure_scale(here: Place, there: Place, offset) -> tuple[float, float]:
    """Pixels per tile from two hovers on the map (``offset`` = second minus first), and
    how many degrees that is off the expected direction (big: wrong place hovered)."""
    dx, dy = there.tile[0] - here.tile[0], there.tile[1] - here.tile[1]
    tiles = math.hypot(dx, dy)
    if tiles < 20:
        raise ValueError(f"{here.name} and {there.name} are too close to measure; pick a "
                         "place further away")
    px = math.hypot(*offset)
    off = math.degrees(abs(math.atan2(-offset[1], offset[0]) - math.atan2(dy, dx)))
    return px / tiles, min(off, 360 - off)


def load_scale(data_dir: Path) -> float | None:
    try:
        return float(json.loads((Path(data_dir) / "map.json").read_text())["px_per_tile"])
    except (OSError, ValueError, KeyError):
        return None


def load_map(data_dir: Path) -> dict:
    try:
        return json.loads((Path(data_dir) / "map.json").read_text())
    except (OSError, ValueError):
        return {}


def save_scale(data_dir: Path, scale: float, view=None) -> None:
    data = {"px_per_tile": round(scale, 4)}
    if view is not None:
        data["view"] = [view.x, view.y, view.w, view.h]
    (Path(data_dir) / "map.json").write_text(json.dumps(data))


MARGIN = 12


def measure_view(before, after, moved: float = 0.4):
    """The world map's own area, from two screens either side of dragging it: the map
    moves, the frame and buttons around it don't. Rows and columns where at least ``moved``
    of the pixels changed, less a margin; None when hardly anything moved."""
    from .layout import Rect
    changed = (abs(before.astype(int) - after.astype(int)).max(axis=2) > 12)
    rows = [i for i, f in enumerate(changed.mean(axis=1)) if f >= moved]
    cols = [i for i, f in enumerate(changed.mean(axis=0)) if f >= moved]
    if len(rows) < 60 or len(cols) < 60:
        return None
    # the longest unbroken run (a button inside the map breaks only a few lines)
    def run(idx):
        best, start = (idx[0], idx[0]), idx[0]
        for a, b in zip(idx, idx[1:] + [None]):
            if b is None or b - a > 8:
                if a - start > best[1] - best[0]:
                    best = (start, a)
                start = b
        return best
    (y0, y1), (x0, x1) = run(rows), run(cols)
    return Rect(x0 + MARGIN, y0 + MARGIN, x1 - x0 - 2 * MARGIN, y1 - y0 - 2 * MARGIN)
