import pytest

from skillbot.config import Step
from skillbot.game import BotError
from skillbot.planner import make_task

from fakes import BANK, LAYOUT, blank, config, make_game, outline, put_item, slot_at

RUINS, ALTAR, PORTAL = (255, 160, 0), (0, 200, 120), (120, 0, 200)
T1, T2, T3 = (255, 255, 255), (128, 128, 255), (255, 128, 255)
PLAYER = LAYOUT.viewport.center
ON_PLAYER = (PLAYER[0] - 15, PLAYER[1] - 10, 30, 20)
AHEAD = (380, 60, 30, 20)
BOX = (300, 100, 40, 40)


class World:
    """A line of places: bank, three route tiles, ruins; plus the altar room.
    From each place only the next thing along the line is visible."""

    PLACES = ["bank", "t1", "t2", "t3", "ruins"]

    def __init__(self, fake, tiara=False, essence_in_bank=28 * 3):
        self.fake, self.where, self.tiara = fake, "bank", tiara
        self.bank_open, self.essence_in_bank, self.selected = False, essence_in_bank, None
        self.trips = 0
        fake.on_click.append(self.click)
        fake.on_key.append(lambda f, k: setattr(self, "bank_open", False) if k == "esc" else None)
        self.draw()

    def draw(self):
        img = blank()
        inv = self.fake.img
        img[LAYOUT.inventory.y - 5:, LAYOUT.inventory.x - 5:] = inv[LAYOUT.inventory.y - 5:,
                                                                   LAYOUT.inventory.x - 5:]
        w = self.where
        if w == "altar":
            outline(img, *BOX, ALTAR)
            outline(img, 120, 250, 30, 30, PORTAL)
        else:
            i = self.PLACES.index(w)
            if w == "bank":
                outline(img, *BOX, BANK)
            else:
                outline(img, *ON_PLAYER, [T1, T2, T3, RUINS][i - 1] if w != "ruins" else RUINS)
            nxt = self.PLACES[i + 1] if i + 1 < len(self.PLACES) else None
            prev = self.PLACES[i - 1] if i else None
            for place, rect in ((nxt, AHEAD), (prev, (120, 250, 30, 20))):
                if place:
                    color = {"bank": BANK, "t1": T1, "t2": T2, "t3": T3, "ruins": RUINS}[place]
                    outline(img, *rect, color)
        self.fake.img = img

    def at(self, pt, rect):
        x, y, w, h = rect
        return x <= pt[0] < x + w and y <= pt[1] < y + h

    def click(self, fake, pt):
        items = fake.items()
        i = slot_at(pt)
        if self.bank_open:
            if i is not None and i in items and items[i] != "fire_talisman" or (
                    i is not None and self.tiara and i in items):
                name = items[i]
                for j, n in items.items():
                    if n == name:
                        put_item(fake.img, j, None)
            r = LAYOUT.bank_slot(0)
            if self.at(pt, (r.x, r.y, r.w, r.h)):
                free = [k for k in range(1, 28) if k not in fake.items()]
                n = min(len(free) // (2 if self.tiara else 1), self.essence_in_bank)
                for k in range(n):
                    put_item(fake.img, free[k], "tiara" if self.tiara else "rune_essence")
                    if self.tiara:
                        put_item(fake.img, free[n + k], "fire_talisman")
                self.essence_in_bank -= n
            return
        if i is not None:
            self.selected = items.get(i)
            return
        w = self.where
        if w == "altar":
            if self.at(pt, BOX):
                if self.tiara and self.selected == "tiara":
                    tiaras = sorted(k for k, n in items.items() if n == "tiara")
                    tals = sorted(k for k, n in items.items() if n == "fire_talisman")
                    put_item(fake.img, tiaras[0], "fire_tiara")
                    put_item(fake.img, tals[0], None)
                elif not self.tiara:
                    ess = [k for k, n in items.items() if n == "rune_essence"]
                    for k in ess:
                        put_item(fake.img, k, None)
                    put_item(fake.img, ess[0], "fire_rune")
                self.selected = None
            elif self.at(pt, (120, 250, 30, 30)):
                self.where = "ruins"
                self.trips += 1
                self.draw()
            return
        idx = self.PLACES.index(w)
        can_enter = self.tiara or self.selected == "fire_talisman"
        ruins_ahead = idx + 1 < len(self.PLACES) and self.PLACES[idx + 1] == "ruins"
        if self.at(pt, AHEAD) and ruins_ahead and can_enter:
            self.where = "altar"          # walks over and enters in one go
        elif self.at(pt, AHEAD) and idx + 1 < len(self.PLACES):
            self.where = self.PLACES[idx + 1]
        elif self.at(pt, (120, 250, 30, 20)) and idx:
            self.where = self.PLACES[idx - 1]
            if self.where == "bank":
                self.bank_open = True      # clicking a booth walks over and opens it
        elif w == "bank" and self.at(pt, BOX):
            self.bank_open = True
            return
        elif w == "ruins" and self.at(pt, ON_PLAYER) and can_enter:
            self.where = "altar"
        self.selected = None
        self.draw()


def rc_cfg():
    return config(routes={"to_ruins": [T1, T2, T3], "to_bank": [T3, T2, T1]})


def rc_step(**kw):
    base = dict(name="fire runes", skill="runecraft", task="runecraft", target=ALTAR,
                ruins=RUINS, portal=PORTAL, items=["rune_essence"], enter_with="fire_talisman",
                keep=["fire_talisman"], withdraw=[0], idle_timeout=5,
                walk={"bank": "to_bank", "target": "to_ruins"})
    base.update(kw)
    return Step.from_dict(base)


def test_rune_trip_end_to_end():
    game, fake = make_game(rc_cfg())
    world = World(fake)
    put_item(fake.img, 0, "fire_talisman")
    world.draw()
    task = make_task(game, rc_step())
    assert task.run_batch() == "ok"
    assert world.trips == 1 and world.where == "ruins"
    assert "fire_rune" in fake.items().values()
    assert task.run_batch() == "ok"              # banks the runes, keeps the talisman
    assert world.trips == 2
    assert list(fake.items().values()).count("fire_talisman") == 1


def test_resumes_from_inside_the_altar():
    game, fake = make_game(rc_cfg())
    world = World(fake)
    world.where = "altar"
    put_item(fake.img, 0, "fire_talisman")
    for i in range(1, 5):
        put_item(fake.img, i, "rune_essence")
    world.draw()
    task = make_task(game, rc_step())
    assert task.run_batch() == "ok"
    assert world.where == "ruins" and "fire_rune" in fake.items().values()


def test_out_of_essence():
    game, fake = make_game(rc_cfg())
    world = World(fake, essence_in_bank=0)
    put_item(fake.img, 0, "fire_talisman")
    world.draw()
    assert make_task(game, rc_step()).run_batch() == "exhausted"


def test_tiara_trip_binds_every_tiara():
    game, fake = make_game(rc_cfg())
    world = World(fake, tiara=True)
    task = make_task(game, rc_step(items=["tiara"], use_item="tiara", enter_with=None, keep=[]))
    assert task.run_batch() == "ok"
    values = list(fake.items().values())
    assert values.count("fire_tiara") == 13 and "tiara" not in values
    assert task.stats["items"] == 13
    assert world.trips == 1


def test_walk_starts_from_the_middle_of_a_route():
    game, fake = make_game(rc_cfg())
    world = World(fake)
    world.where = "t2"
    world.draw()
    game.walk("to_ruins", RUINS)
    assert world.where in ("t3", "ruins")
    clicked = [p for p, _ in fake.clicks]
    assert not any(world.at(p, (120, 250, 30, 20)) for p in clicked)   # never walked back


def test_walk_reports_a_gap_in_the_route():
    game, fake = make_game(config(routes={"r": [T1]}))
    fake.img = blank()
    outline(fake.img, *AHEAD, T1)

    def arrive(f, pt):
        f.img = blank()
        outline(f.img, *ON_PLAYER, T1)     # standing on the last tile, target not in sight
    fake.on_click.append(arrive)
    with pytest.raises(BotError, match="reached tile 1"):
        game.walk("r", RUINS)
