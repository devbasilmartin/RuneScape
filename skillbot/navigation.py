"""Travel between places: set the Shortest Path target on the world map, follow the
drawn path.

F2P (docs/travel.md): places have world coordinates (library/places/f2p.yaml) and the bot
remembers which one it's at (the activity it's doing, the bank it just used). The map
opens centred on you, so the target is the centre plus the tile difference times the
map's scale; if that's off the map, the map is dragged first.

With teleports (docs/navigation.md):
Hubs (config.yaml) are teleport arrival points. After a teleport you stand on a known
tile, so the world map opens centred on a known spot and every destination is a fixed
pixel offset from the map's centre. Offsets are recorded once per destination with
`python -m skillbot add-destination NAME --hub HUB` (data/destinations.json).

Shortest Path (Plugin Hub) draws the route on the scene and the minimap in its path
color; the bot clicks the far end of what's drawn, on the minimap when possible (longer
strides), until the place it's going to is on screen.
"""
import json
import logging
import math
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from .game import BotError
from .layout import Rect
from .places import map_offset
from .vision import color_mask

log = logging.getLogger("skillbot")

LOST = "?"      # nav.here after a failed walk or a teleport: somewhere, but not a known place


@dataclass
class Hub:
    name: str
    teleport: dict                    # {spell: [x, y]} or {item: name, option: "2"}
    wait: float = 5.0                 # seconds for the teleport animation
    marker: tuple | None = None       # highlight seen on arrival (a Ground Marker)

    @classmethod
    def from_dict(cls, name: str, d: dict) -> "Hub":
        tele = dict(d.get("teleport") or {})
        if "spell" in tele:
            tele["spell"] = tuple(tele["spell"])
        elif "item" not in tele:
            raise ValueError(f"hub {name!r}: teleport needs a spell position or an item")
        marker = d.get("marker")
        return cls(name, tele, float(d.get("wait", 5.0)), tuple(marker) if marker else None)


@dataclass
class Destinations:
    path: Path | None
    data: dict = field(default_factory=dict)      # name -> {"hub": str, "offset": [dx, dy]}

    @classmethod
    def load(cls, path: Path) -> "Destinations":
        path = Path(path)
        return cls(path, json.loads(path.read_text()) if path.exists() else {})

    def add(self, name: str, hub: str, offset) -> None:
        self.data[name] = {"hub": hub, "offset": [int(offset[0]), int(offset[1])]}
        if self.path:
            self.path.write_text(json.dumps(self.data, indent=1))


class Navigator:
    def __init__(self, game, hubs: dict[str, Hub], destinations: Destinations,
                 path_color, menu_option: int = 1, stride_wait=(2.5, 3.5), places=None,
                 scale: float | None = None):
        self.game = game
        self.places = places or {}      # F2P places by world coordinate
        self.scale = scale              # world map pixels per tile (calibrate-map)
        self.here = None                # the place we're at; None: not moved yet this run
        self.hubs = hubs
        self.destinations = destinations
        self.path_color = tuple(path_color)
        self.menu_option = menu_option
        self.stride_wait = stride_wait

    # ---- teleports ---------------------------------------------------------------------
    def teleport(self, hub_name: str) -> None:
        g = self.game
        hub = self.hubs.get(hub_name)
        if hub is None:
            raise BotError(f"unknown hub {hub_name!r}; add it under hubs: in config.yaml")
        t = hub.teleport
        log.info("teleporting to %s", hub_name)
        if "spell" in t:
            g.open_tab("magic")
            g.controls.click(t["spell"])
            g.wait(hub.wait, hub.wait + 1)
            g.open_tab("inventory")
        else:
            slots = g.inv.slots_with(g.grab(), t["item"])
            if not slots:
                g.out_of_stock(f"teleport to {hub_name}", [t["item"]])
                raise BotError(f"no {t['item']} to teleport to {hub_name}")
            g.controls.click_rect(g.layout.slot(min(slots)))
            if t.get("option"):
                g.wait(0.8, 1.2)                 # jewelry: "Rub" opens a list of places
                g.controls.press(str(t["option"]))
            g.wait(hub.wait, hub.wait + 1)
        self.here = LOST
        if hub.marker and not g.wait_until(lambda img: bool(g.blobs(img, hub.marker)), 10):
            raise BotError(f"teleport to {hub_name} didn't arrive (no hub marker in sight)")

    # ---- world map ---------------------------------------------------------------------
    def menu_point(self, point, option: int):
        lay = self.game.layout
        return point[0], point[1] + lay.menu_header + lay.menu_row * (option - 1) + lay.menu_row // 2

    def set_target(self, dest: str) -> None:
        self.set_target_at(self.destinations.data[dest]["offset"], drag=False)

    def set_target_at(self, offset, drag: bool = True) -> None:
        """Open the world map and "Set target" ``offset`` pixels from its centre (you),
        dragging the map first when that's outside the part we can click."""
        g, lay = self.game, self.game.layout
        g.controls.click(lay.world_map_button)
        g.wait(1.5, 2.0)
        cx, cy = lay.world_map_center
        view = lay.world_map_view
        x, y = cx + offset[0], cy + offset[1]
        for _ in range(12):
            inside = view.x <= x < view.x + view.w and view.y <= y < view.y + view.h
            if inside or not drag:
                break
            # drag the map so the target moves towards the centre (the map follows the mouse)
            step_x = max(-view.w // 2 + 10, min(view.w // 2 - 10, cx - x))
            step_y = max(-view.h // 2 + 10, min(view.h // 2 - 10, cy - y))
            start = (cx - step_x // 2, cy - step_y // 2)
            g.controls.drag(start, (start[0] + step_x, start[1] + step_y))
            g.wait(0.3, 0.5)
            x, y = x + step_x, y + step_y
        if drag and not (view.x <= x < view.x + view.w and view.y <= y < view.y + view.h):
            g.close_interfaces()
            raise BotError("the destination is too far across the world map")
        point = (x, y)
        g.choose(point, "Set target", self.menu_option)
        g.wait(0.4, 0.7)
        g.close_interfaces()

    # ---- following the path ------------------------------------------------------------
    def far_end(self, img):
        """The drawn path pixel farthest from the player: minimap first (canvas coords),
        else in the game view. None when no path is drawn."""
        lay = self.game.layout
        mx, my = lay.minimap_center
        r = lay.minimap_radius - 6                  # stay off the minimap's rim
        box = Rect(mx - r, my - r, 2 * r, 2 * r)
        ys, xs = np.nonzero(color_mask(box.crop(img), self.path_color, self.game.cfg.color_tolerance))
        if len(xs):
            xs, ys = xs + box.x, ys + box.y
            d = (xs - mx) ** 2 + (ys - my) ** 2
            inside = d <= r * r
            if inside.any():
                i = int(np.argmax(np.where(inside, d, -1)))
                return int(xs[i]), int(ys[i])
        vp = lay.viewport
        ys, xs = np.nonzero(color_mask(vp.crop(img), self.path_color, self.game.cfg.color_tolerance))
        if not len(xs):
            return None
        px, py = self.game.player
        xs, ys = xs + vp.x, ys + vp.y
        i = int(np.argmax((xs - px) ** 2 + (ys - py) ** 2))
        return int(xs[i]), int(ys[i])

    def follow(self, until_color, max_strides: int = 60) -> None:
        g = self.game
        last, same = None, 0
        for _ in range(max_strides):
            img = g.grab()
            if until_color is not None and g.blobs(img, until_color):
                return
            end = self.far_end(img)
            if end is None:
                if until_color is None:
                    return                         # no path left: arrived
                raise BotError("no Shortest Path route drawn, and the destination isn't in "
                               "sight (is the plugin on, with this path color?)")
            if last is not None and math.dist(end, last) < 4:
                same += 1
                if same >= 4:
                    raise BotError("stuck while walking: the path isn't getting shorter "
                                   "(a door or obstacle?)")
            else:
                same = 0
            last = end
            g.keep_running()
            g.controls.click(end)
            g.wait(*self.stride_wait)
        raise BotError("walked too long without arriving")

    def travel(self, dest: str, until_color) -> None:
        """Get to ``dest`` unless ``until_color`` is already in sight."""
        g = self.game
        if until_color is not None and g.blobs(g.grab(), until_color):
            self.here = dest
            return
        if dest in self.places and dest not in self.destinations.data:
            return self.walk_to(dest, until_color)
        if dest.startswith("hub:"):                 # e.g. your house: the teleport is the trip
            self.teleport(dest[4:])
            if until_color is not None and not g.wait_until(
                    lambda img: bool(g.blobs(img, until_color)), timeout=10):
                raise BotError(f"teleported to {dest[4:]} but {until_color} isn't in sight")
            return
        spot = self.destinations.data.get(dest)
        if spot is None:
            raise BotError(f"unknown destination {dest!r}; record it with "
                           f"`python -m skillbot add-destination {dest} --hub HUB`")
        log.info("travelling to %s via %s", dest, spot["hub"])
        self.teleport(spot["hub"])
        self.set_target(dest)
        self.follow(until_color)
        self.here = dest

    # ---- F2P: walking between known places ---------------------------------------------
    def walk_to(self, dest: str, until_color) -> None:
        g = self.game
        if self.here is None or self.here == dest:
            # Not moved yet this run (it was started here), or it's where we already are and
            # the highlight is just gone for a moment (everything chopped, cows dead).
            self.here = dest
            return
        if self.here == LOST:
            raise BotError(f"can't walk to {dest}: I don't know where I am (after a failed "
                           "walk or a teleport). Walk me back and restart the run")
        if self.here not in self.places:
            raise BotError(f"don't know where {self.here!r} is (not in library/places/f2p.yaml)")
        if self.scale is None:
            raise BotError("the world map's scale isn't measured: run Calibrate map "
                           "(`python -m skillbot calibrate-map`, docs/travel.md)")
        here, there = self.places[self.here], self.places[dest]
        log.info("walking from %s to %s", here.name, dest)
        self.moves(here.leave)
        self.here = LOST                    # on the way: if it fails, we don't know
        self.set_target_at(map_offset(here, there, self.scale))
        g.wait(1.0, 1.5)                    # Shortest Path needs a moment to draw
        self.follow(None if there.arrive else until_color)
        self.moves(there.arrive)
        if until_color is not None and not g.wait_until(
                lambda img: bool(g.blobs(img, until_color)), timeout=10):
            raise BotError(f"walked to {dest} but {until_color} isn't in sight (is "
                           "everything marked there, and its tile in library/places/f2p.yaml right?)")
        self.here = dest

    def moves(self, moves) -> None:
        """Click the stairs (and pick a dialog option) for places upstairs."""
        g = self.game
        for m in moves:
            if not g.wait_until(lambda img: bool(g.blobs(img, m.click)), timeout=10):
                raise BotError(f"can't see {m.click} (the stairs: mark them with Object "
                               "Markers on every floor)")
            g.click_nearest(g.grab(), m.click)
            if m.key:
                g.wait(1.5, 2.0)
                g.controls.press(m.key)
            g.wait(m.wait, m.wait + 1)
