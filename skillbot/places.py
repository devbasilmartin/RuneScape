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


def save_scale(data_dir: Path, scale: float) -> None:
    (Path(data_dir) / "map.json").write_text(json.dumps({"px_per_tile": round(scale, 4)}))
