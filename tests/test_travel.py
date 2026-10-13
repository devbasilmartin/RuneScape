"""F2P travel: places by world coordinate, the world map's scale, stairs."""
import json

import pytest

from skillbot.game import BotError
from skillbot.navigation import Destinations, Navigator
from skillbot.places import Move, Place, load_places, map_offset, measure_scale

from fakes import BANK, BG, LAYOUT, TREE, config, make_game, outline

PATH = (255, 0, 128)
STAIRS = (192, 0, 192)
SCALE = 2.0

PLACES = {
    "cows": Place("cows", (3258, 3275)),
    "trees": Place("trees", (3195, 3235)),
    "far": Place("far", (3058, 3375)),
    "bank": Place("bank", (3206, 3209),
                  arrive=[Move(STAIRS), Move(STAIRS, key="1")],
                  leave=[Move(STAIRS), Move(STAIRS, key="2")]),
}


class World:
    """The world map (centred on you, draggable), "Set target", a path on the minimap
    that shortens with each click, and the castle stairs up to the bank."""

    def __init__(self, fake, at="cows", strides=3):
        self.fake, self.at, self.strides = fake, at, strides
        self.map_open, self.shift, self.menu_at = False, (0, 0), None
        self.target, self.left, self.floor, self.dialog = None, 0, 0, False
        self.right_clicked = []
        fake.on_click.append(self.click)
        fake.on_drag = [self.drag]
        fake.on_key.append(self.key)
        orig = fake.click

        def click(pt, button="left"):
            if button == "right" and self.map_open:
                self.menu_at = tuple(pt)
                self.right_clicked.append(tuple(pt))
            orig(pt, button)
        fake.click = click
        self.draw()

    def draw(self):
        img = self.fake.img
        v = LAYOUT.viewport
        img[v.y:v.y + v.h, v.x:v.x + v.w] = BG
        mx, my = LAYOUT.minimap_center
        img[my - 70:my + 70, mx - 70:mx + 70] = BG
        if self.left > 0:
            for t in range(min(10 + 12 * self.left, 120)):
                img[my - t // 2, mx + t // 2] = PATH
        if self.at == "trees":
            outline(img, 240, 150, 40, 30, TREE)
        if self.at == "bank" and self.floor < 2:
            outline(img, 200, 120, 30, 30, STAIRS)
        if self.at == "bank" and self.floor == 2:
            outline(img, 200, 120, 30, 30, STAIRS)
            outline(img, 300, 150, 30, 30, BANK)

    def key(self, fake, k):
        if k == "esc":
            self.map_open = False
        if self.dialog and k in ("1", "2"):
            self.floor += 1 if k == "1" else -1
            self.dialog = False
            if self.floor == 0:
                self.at = "bank floor 0"
            self.draw()

    def drag(self, fake, start, end):
        assert self.map_open
        self.shift = (self.shift[0] + end[0] - start[0], self.shift[1] + end[1] - start[1])

    def click(self, fake, pt):
        lay = LAYOUT
        if tuple(pt) == lay.world_map_button:
            self.map_open, self.shift = True, (0, 0)
            return
        if self.map_open and self.menu_at:
            if tuple(pt) == (self.menu_at[0], self.menu_at[1] + lay.menu_header
                             + lay.menu_row // 2):
                cx, cy = lay.world_map_center
                here = PLACES[self.at.split(" floor")[0]]
                tx = here.tile[0] + (self.menu_at[0] - self.shift[0] - cx) / SCALE
                ty = here.tile[1] - (self.menu_at[1] - self.shift[1] - cy) / SCALE
                self.target = min(PLACES.values(), key=lambda p: abs(p.tile[0] - tx)
                                  + abs(p.tile[1] - ty)).name
                self.left = self.strides
                self.draw()
            self.menu_at = None
            return
        mx, my = lay.minimap_center
        if self.left and abs(pt[0] - mx) < 70 and abs(pt[1] - my) < 70:
            self.left -= 1
            if self.left == 0:
                self.at, self.floor = self.target, 0
            self.draw()
            return
        x, y = pt
        if self.at.startswith("bank") and 200 <= x < 230 and 120 <= y < 150:
            if self.floor == 0:
                self.floor, self.at = 1, "bank"
            elif self.floor == 2:
                self.floor = 1
            else:
                self.dialog = True
            self.draw()


def setup(at="cows", strides=3, scale=SCALE):
    game, fake = make_game(config())
    world = World(fake, at, strides)
    game.nav = Navigator(game, {}, Destinations(None), PATH, stride_wait=(3, 3),
                         places=PLACES, scale=scale)
    return game, fake, world


def test_walks_from_where_it_is_to_a_place():
    game, fake, world = setup(at="cows")
    game.nav.here = "cows"
    game.nav.travel("trees", TREE)
    assert world.at == "trees" and game.nav.here == "trees"
    assert not getattr(fake, "drags", [])               # close enough: no dragging


def test_drags_the_map_when_the_place_is_off_it():
    game, fake, world = setup(at="cows")
    game.nav.here = "cows"
    game.nav.travel("far", None)
    assert world.target == "far" and fake.drags
    view = LAYOUT.world_map_view
    x, y = world.right_clicked[-1]
    assert view.x <= x < view.x + view.w and view.y <= y < view.y + view.h


def test_climbs_the_stairs_to_the_bank_and_back_down():
    game, fake, world = setup(at="cows")
    game.nav.here = "cows"
    game.nav.travel("bank", BANK)
    assert world.at == "bank" and world.floor == 2 and game.nav.here == "bank"
    game.nav.travel("cows", None)
    assert world.target == "cows" and world.at == "cows"


def test_an_unknown_start_is_assumed_to_be_the_activity():
    """The run was started at the activity; everything there is just gone for now."""
    game, fake, world = setup(at="cows")
    game.nav.travel("cows", (255, 128, 255))
    assert game.nav.here == "cows" and fake.clicks == []


def test_already_in_sight_sets_where_we_are():
    game, fake, world = setup(at="trees")
    game.nav.travel("trees", TREE)
    assert game.nav.here == "trees" and fake.clicks == []


def test_unmeasured_map_says_what_to_do():
    game, fake, world = setup(scale=None)
    game.nav.here = "cows"
    with pytest.raises(BotError, match="Calibrate map"):
        game.nav.travel("trees", TREE)


def test_arriving_somewhere_else_is_an_error_and_forgets_where_we_are():
    game, fake, world = setup(at="cows")
    game.nav.here = "cows"
    with pytest.raises(BotError, match="isn't in sight"):
        game.nav.travel("trees", (1, 2, 3))
    assert game.nav.here == "?"


def test_map_offset_and_scale():
    a, b = PLACES["cows"], PLACES["trees"]
    assert map_offset(a, b, 2.0) == (-126, 80)            # west and south: left and down
    scale, off = measure_scale(a, b, (-126, 80))
    assert scale == pytest.approx(2.0) and off < 1
    _, off = measure_scale(a, b, (126, 80))
    assert off > 15
    with pytest.raises(ValueError, match="too close"):
        measure_scale(a, Place("near", (3260, 3270)), (4, 10))


def test_every_f2p_activity_and_bank_is_a_place():
    from pathlib import Path

    import yaml

    from skillbot.colors import Registry
    places = load_places(Registry.load(Path(__file__).parent.parent / "colors.yaml").resolve)
    lib = yaml.safe_load((Path(__file__).parent.parent / "library" / "f2p.yaml").read_text())
    for mid, m in lib.items():
        for name in (m.get("location"), m["step"].get("bank_location")):
            if name and not m.get("requires", {}).get("levels"):
                assert name in places, f"{mid}: {name!r} isn't in library/places/f2p.yaml"
    assert places["lumbridge bank"].arrive[1].key == "1"


def test_after_a_failed_walk_it_knows_it_is_lost():
    game, fake, world = setup(at="cows")
    game.nav.here = "cows"
    with pytest.raises(BotError):
        game.nav.travel("trees", (1, 2, 3))
    with pytest.raises(BotError, match="don't know where I am"):
        game.nav.travel("cows", (9, 9, 9))


def test_a_recorded_teleport_destination_wins_over_a_place():
    game, fake, world = setup(at="cows")
    game.nav.destinations.data["trees"] = {"hub": "varrock", "offset": [10, 10]}
    calls = []
    game.nav.teleport = lambda hub: calls.append(hub)
    game.nav.set_target = lambda dest: calls.append(dest)
    game.nav.follow = lambda until: calls.append("follow")
    game.nav.travel("trees", TREE)
    assert calls == ["varrock", "trees", "follow"] and game.nav.here == "trees"


def test_point_at_reads_the_mouse_after_the_countdown(monkeypatch):
    """Pressing Enter in the panel puts the mouse on the panel: read it after a countdown."""
    from skillbot.__main__ import point_at
    moves = iter([(100, 100), (300, 200)])
    controls = type("C", (), {"pos": (100, 100), "position": lambda self: self.pos})()
    monkeypatch.setattr("builtins.input", lambda prompt: None)

    def sleep(s):
        controls.pos = next(moves, controls.pos)
    assert point_at(controls, "the cows", seconds=2, sleep=sleep) == (300, 200)


def test_the_world_maps_area_is_where_the_picture_moved_when_dragged():
    import numpy as np
    from skillbot.layout import Rect
    from skillbot.places import MARGIN, measure_view
    rng = np.random.default_rng(1)
    before = np.full((503, 765, 3), 70, np.uint8)
    terrain = rng.integers(0, 255, (400, 600, 3), np.uint8)
    before[50:350, 30:480] = terrain[:300, :450]
    after = before.copy()
    after[50:350, 30:480] = terrain[30:330, 40:490]           # dragged
    after[60:80, 440:470] = before[60:80, 440:470]            # a button that stays put
    assert measure_view(before, after) == Rect(30 + MARGIN, 50 + MARGIN, 449 - 2 * MARGIN,
                                               299 - 2 * MARGIN)
    assert measure_view(before, before) is None
