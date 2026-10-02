import pytest

from skillbot.config import Step
from skillbot.game import BotError
from skillbot.planner import make_task

import fakes
from fakes import BANK, BG, LAYOUT, config, make_game, outline, slot_at

EXTRA = {"paydirt": (0, 64, 255), "ore": (0, 128, 128)}
VEIN, HOPPER, SACK, STRUT = (0, 255, 255), (255, 255, 0), (0, 255, 128), (255, 64, 0)


@pytest.fixture(autouse=True)
def extra_items():
    before = dict(fakes.ITEMS)
    fakes.ITEMS.update(EXTRA)
    yield
    fakes.ITEMS.clear()
    fakes.ITEMS.update(before)


def at(pt, rect):
    x, y, w, h = rect
    return x <= pt[0] < x + w and y <= pt[1] < y + h


class Mine:
    """A tiny Motherlode Mine: a vein gives paydirt every 2 s; the hopper takes paydirt
    into the sack (only while the strut works); the sack hands out ore 27 at a time; the
    bank takes ore."""
    VEIN_R, HOPPER_R, SACK_R, STRUT_R = (240, 150, 40, 30), (330, 80, 30, 30), \
        (120, 200, 30, 30), (420, 220, 25, 25)

    def __init__(self, fake, broken=False):
        self.fake, self.sack, self.mining, self.last, self.broken = fake, 0, False, 0.0, broken
        self.banked, self.bank_open = 0, False
        fake.on_click.append(self.click)
        fake.on_wait.append(self.tick)
        fake.on_key.append(lambda f, k: setattr(self, "bank_open", False) if k == "esc" else None)
        self.draw()

    def draw(self):
        img = self.fake.img
        img[:LAYOUT.viewport.y + LAYOUT.viewport.h, :LAYOUT.viewport.x + LAYOUT.viewport.w] = BG
        outline(img, *self.VEIN_R, VEIN)
        outline(img, *self.HOPPER_R, HOPPER)
        outline(img, *self.SACK_R, SACK)
        outline(img, 380, 60, 30, 30, BANK)
        if self.broken:
            outline(img, *self.STRUT_R, STRUT)

    def free(self):
        return [k for k in range(1, 28) if k not in self.fake.items()]

    def click(self, f, pt):
        if self.bank_open and slot_at(pt) is not None:
            name = f.items().get(slot_at(pt))
            for j, n in list(f.items().items()):
                if n == name:
                    fakes.put_item(f.img, j, None)
                    self.banked += 1
            return
        self.mining = at(pt, self.VEIN_R)
        if at(pt, self.STRUT_R) and self.broken:
            self.broken = False
        elif at(pt, self.HOPPER_R):
            for j, n in list(f.items().items()):
                if n == "paydirt":
                    fakes.put_item(f.img, j, None)
                    if not self.broken:
                        self.sack += 1
        elif at(pt, self.SACK_R):
            for k in self.free()[:min(self.sack, 27)]:
                fakes.put_item(f.img, k, "ore")
                self.sack -= 1
        elif at(pt, (380, 60, 30, 30)):
            self.bank_open = True
        self.draw()

    def tick(self, f):
        if self.mining and f.t - self.last >= 2 and self.free():
            fakes.put_item(f.img, self.free()[0], "paydirt")
            self.last = f.t


MLM = [
    {"name": "fix strut", "when": {"visible": list(STRUT)},
     "do": [{"click": list(STRUT)}, {"wait": 2}]},
    {"name": "mine", "repeat_until": {"full": True}, "max": 40,
     "do": [{"click": list(VEIN)}, {"wait_for": {"gained": "paydirt"}, "timeout": 10}]},
    {"name": "deposit", "count": "loads",
     "do": [{"click": list(HOPPER)}, {"wait_for": {"lacks": "paydirt"}}]},
    {"name": "collect", "when": {"counter_at_least": {"loads": 2}}, "until_fail": True,
     "reset": ["loads"],
     "do": [{"click": list(SACK)}, {"wait_for": {"gained": "ore"}, "timeout": 5},
            {"bank": True}, {"progress": 1}]},
]


def mlm_step():
    return Step.from_dict(dict(name="mlm", skill="mining", task="routine", items=["ore"],
                               routine=MLM, tools=1))


def test_motherlode_style_routine():
    game, fake = make_game(config(extra_items=EXTRA))
    mine = Mine(fake, broken=True)
    task = make_task(game, mlm_step())
    assert task.run_batch() == "ok" and mine.sack == 27 and not mine.broken
    assert task.run_batch() == "ok"
    assert mine.banked == 54 and mine.sack == 0 and task.stats["items"] == 2


def test_failed_wait_is_an_error_outside_until_fail():
    game, fake = make_game(config(extra_items=EXTRA))
    Mine(fake)
    routine = [{"name": "hopper", "do": [{"click": list(HOPPER)},
                                        {"wait_for": {"has": "ore"}, "timeout": 3}]}]
    task = make_task(game, Step.from_dict(dict(name="x", skill="mining", task="routine",
                                                routine=routine)))
    with pytest.raises(BotError, match="wait_for didn't work"):
        task.run_batch()


def test_exhausted_if():
    game, fake = make_game(config(extra_items=EXTRA))
    routine = [{"exhausted_if": {"lacks": "ore"}, "do": [{"wait": 1}]}]
    task = make_task(game, Step.from_dict(dict(name="x", skill="mining", task="routine",
                                                routine=routine)))
    assert task.run_batch() == "exhausted"


def test_bare_on_key_is_explained():
    with pytest.raises(ValueError, match="bare `on:`"):
        Step.from_dict(dict(name="x", skill="mining", task="routine",
                            routine=[{"do": [{"use": {"item": "a", True: "b"}}]}]))


def test_routine_validation():
    with pytest.raises(ValueError, match="unknown condition"):
        Step.from_dict(dict(name="x", skill="mining", task="routine",
                            routine=[{"when": {"glowing": 1}, "do": [{"wait": 1}]}]))
    with pytest.raises(ValueError, match="exactly one"):
        Step.from_dict(dict(name="x", skill="mining", task="routine",
                            routine=[{"do": [{"click": "a", "key": "1"}]}]))
    with pytest.raises(ValueError, match="do"):
        Step.from_dict(dict(name="x", skill="mining", task="routine", routine=[{"name": "x"}]))
