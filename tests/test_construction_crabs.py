import pytest

from skillbot.config import Step
from skillbot.game import BotError
from skillbot.planner import make_task

import fakes
from fakes import BG, LAYOUT, config, make_game, outline

EXTRA = {"oak_plank": (0, 128, 128), "trout": (128, 0, 255)}
SPOT = (0, 192, 255)


@pytest.fixture(autouse=True)
def extra_items():
    before = dict(fakes.ITEMS)
    fakes.ITEMS.update(EXTRA)
    yield
    fakes.ITEMS.clear()
    fakes.ITEMS.update(before)


class House:
    """Build mode: click spot → menu; key → furniture built (8 planks used); right-click →
    menu; remove row → confirm; '1' → removed."""

    def __init__(self, fake, planks_per_build=8, remove_option=2):
        self.fake, self.per, self.remove_option = fake, planks_per_build, remove_option
        self.state, self.built, self.removed, self.menu_at = "idle", 0, 0, None
        outline(fake.img, 240, 150, 40, 30, SPOT)
        fake.on_click.append(self.click)
        fake.on_key.append(self.key)
        orig = fake.click

        def click(pt, button="left"):
            if button == "right" and self.state == "built":
                self.menu_at = tuple(pt)
            orig(pt, button)
        fake.click = click

    def on_spot(self, pt):
        return 240 <= pt[0] < 280 and 150 <= pt[1] < 180

    def click(self, f, pt):
        if self.state == "idle" and self.on_spot(pt):
            self.state = "menu"
        elif self.menu_at is not None:
            lay = LAYOUT
            row = (self.menu_at[1] + lay.menu_header + lay.menu_row * (self.remove_option - 1)
                   + lay.menu_row // 2)
            if tuple(pt) == (self.menu_at[0], row):
                self.state = "confirm"
            self.menu_at = None

    def key(self, f, k):
        if self.state == "menu" and k == "4":
            planks = sorted(i for i, n in f.items().items() if n == "oak_plank")
            if len(planks) >= self.per:
                for i in planks[:self.per]:
                    fakes.put_item(f.img, i, None)
                self.state, self.built = "built", self.built + 1
            else:
                self.state = "idle"
        elif self.state == "confirm" and k == "1":
            self.state, self.removed = "idle", self.removed + 1
        elif k == "esc":
            self.state = "idle"


def larder_step(**kw):
    base = dict(name="larders", skill="construction", task="construction", target=SPOT,
                items=["oak_plank"], build_key="4", remove_option=2, builds_per_batch=10,
                idle_timeout=4)
    return Step.from_dict({**base, **kw})


def test_build_remove_until_planks_run_out():
    game, fake = make_game(config(extra_items=EXTRA))
    for i in range(1, 25):
        fakes.put_item(fake.img, i, "oak_plank")
    house = House(fake)
    task = make_task(game, larder_step())
    assert task.run_batch() == "ok"
    assert house.built == 3 and house.removed == 3 and task.stats["items"] == 3
    assert task.run_batch() == "exhausted"                 # no planks, no bank location


def test_wrong_build_key_is_reported():
    game, fake = make_game(config(extra_items=EXTRA))
    for i in range(1, 9):
        fakes.put_item(fake.img, i, "oak_plank")
    House(fake)
    task = make_task(game, larder_step(build_key="9"))
    with pytest.raises(BotError, match="build_key"):
        task.run_batch()


def test_construction_needs_a_spot():
    with pytest.raises(ValueError, match="hotspot"):
        Step.from_dict(dict(name="x", skill="construction", task="construction",
                            items=["oak_plank"]))
    assert Step.from_dict(dict(name="x", skill="construction", task="construction",
                               items=["oak_plank"], hotspot=[200, 150])).hotspot == (200, 150)


# ---- crabs -------------------------------------------------------------------------------

CRAB, STAND, RESET = (255, 128, 128), (0, 192, 64), (64, 0, 192)


def test_crabs_stand_fight_and_reset_aggression():
    game, fake = make_game(config(extra_items=EXTRA))
    fakes.put_item(fake.img, 1, "trout")
    state = {"where": "stand", "aggro_until": 120.0, "resets": 0}

    def draw():
        img = fake.img
        img[:LAYOUT.viewport.y + LAYOUT.viewport.h, :LAYOUT.viewport.x + LAYOUT.viewport.w] = BG
        px, py = LAYOUT.viewport.center
        if state["where"] == "stand":
            outline(img, px - 10, py - 8, 20, 16, STAND)
            outline(img, 380, 60, 25, 20, RESET)
            outline(img, px + 30, py - 10, 30, 25, CRAB)
            if fake.t < state["aggro_until"]:
                img[py - 30:py - 27, px + 30:px + 60] = (0, 255, 0)     # crab's health bar
        else:
            outline(img, px - 10, py - 8, 20, 16, RESET)
            outline(img, 60, 300, 20, 16, STAND)
    draw()

    def click(f, pt):
        if state["where"] == "stand" and 380 <= pt[0] < 405 and 60 <= pt[1] < 80:
            state["where"] = "reset"
        elif state["where"] == "reset" and 60 <= pt[0] < 80 and 300 <= pt[1] < 316:
            state["where"] = "stand"
            state["resets"] += 1
            state["aggro_until"] = f.t + 120
        draw()
    fake.on_click.append(click)
    fake.on_wait.append(lambda f: draw())
    step = Step.from_dict(dict(name="crabs", skill="strength", task="combat", target=CRAB,
                               stand_on=STAND, reset_spot=RESET, reset_after=60,
                               items=["trout"], food=["trout"], eat_below=0.0))
    task = make_task(game, step)
    assert type(task).__name__ == "StandingCombatTask"
    assert task.run_batch() == "ok"                      # a 10-minute batch
    assert state["resets"] >= 2 and task.stats["items"] >= 2
