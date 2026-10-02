import pytest

from skillbot.config import Step
from skillbot.game import BotError
from skillbot.planner import make_task

import fakes
from fakes import BG, LAYOUT, config, make_game, outline, slot_at

EXTRA = {"nature_rune": (0, 192, 255), "fire_rune": (192, 255, 64), "yew_longbow": (255, 64, 255)}
SPELL = (700, 300)


@pytest.fixture(autouse=True)
def extra_items():
    before = dict(fakes.ITEMS)
    fakes.ITEMS.update(EXTRA)
    yield
    fakes.ITEMS.clear()
    fakes.ITEMS.update(before)


def alch_setup(bows=5):
    game, fake = make_game(config(extra_items=EXTRA))
    fakes.put_item(fake.img, 0, "nature_rune")
    fakes.put_item(fake.img, 1, "fire_rune")
    for i in range(bows):
        fakes.put_item(fake.img, 2 + i, "yew_longbow")
    state = {"spell": False, "casts": 0}

    def click(f, pt):
        if tuple(pt) == SPELL:
            state["spell"] = True
            return
        i = slot_at(pt)
        if state["spell"] and i is not None and f.items().get(i) == "yew_longbow":
            fakes.put_item(f.img, i, None)
            state["casts"] += 1
        state["spell"] = False
    fake.on_click.append(click)
    return game, fake, state


def alch_step(**kw):
    return Step.from_dict(dict(name="alch", skill="magic", task="cast", spell=SPELL,
                               on_item="yew_longbow", runes=["nature_rune", "fire_rune"],
                               casts_per_batch=50, **kw))


def test_alchemy_casts_until_items_run_out():
    game, fake, state = alch_setup(bows=5)
    task = make_task(game, alch_step())
    assert task.run_batch() == "ok"
    assert state["casts"] == 5 and task.stats["items"] == 5
    assert fake.clicks[0][0] == LAYOUT.tabs["magic"]
    assert task.run_batch() == "exhausted"


def test_teleport_training_needs_only_runes():
    game, fake, state = alch_setup(bows=0)
    task = make_task(game, Step.from_dict(dict(name="tele", skill="magic", task="cast",
                                                spell=SPELL, runes=["nature_rune"],
                                                casts_per_batch=10)))
    assert task.run_batch() == "ok" and task.stats["items"] == 10


# ---- agility --------------------------------------------------------------------------

OBS = [(0, 0, 255), (0, 255, 64), (192, 0, 255), (255, 64, 64)]
MARK = (255, 192, 64)


class Course:
    """The camera follows the player: at obstacle i, obstacle i is drawn ahead and the next
    one further away. Crossing redraws the scene from the next obstacle."""

    def __init__(self, fake, fall_at=None, mark_at=None):
        self.fake, self.at, self.fall_at, self.mark_at = fake, 0, fall_at, mark_at
        self.mark_shown = False
        fake.on_click.append(self.click)
        self.draw()

    def draw(self):
        img = self.fake.img
        img[:LAYOUT.viewport.y + LAYOUT.viewport.h, :LAYOUT.viewport.x + LAYOUT.viewport.w] = BG
        outline(img, 280, 120, 40, 30, OBS[self.at])
        if self.at + 1 < len(OBS):
            outline(img, 400, 60, 30, 20, OBS[self.at + 1])
        else:
            outline(img, 400, 60, 30, 20, OBS[0])            # back at the start
        if self.mark_at == self.at and not self.mark_shown:
            outline(img, 220, 180, 12, 12, MARK)

    def click(self, f, pt):
        if 220 <= pt[0] < 232 and 180 <= pt[1] < 192:
            self.mark_shown = True
            self.draw()
            return
        if 280 <= pt[0] < 320 and 120 <= pt[1] < 150:      # crossed obstacle `at`
            if self.fall_at == self.at:
                self.fall_at = None
                self.at = 0
            else:
                self.at = (self.at + 1) % len(OBS)
            self.draw()


def agility_step(**kw):
    return Step.from_dict(dict(name="rooftop", skill="agility", task="agility", obstacles=OBS,
                               loot=MARK, laps_per_batch=2, idle_timeout=5, **kw))


def test_laps_with_a_mark_and_a_fall():
    game, fake = make_game(config())
    course = Course(fake, fall_at=2, mark_at=1)
    task = make_task(game, agility_step())
    assert task.run_batch() == "ok"
    assert task.stats["laps"] == 2 and task.stats["marks"] == 1 and task.stats["falls"] == 1
    assert course.at == 0


def test_stuck_obstacle_raises():
    game, fake = make_game(config())
    course = Course(fake)
    fake.on_click.remove(course.click)                    # clicks do nothing
    task = make_task(game, agility_step())
    with pytest.raises(BotError, match="obstacle 1"):
        task.run_batch()


def test_agility_and_cast_validation():
    with pytest.raises(ValueError, match="obstacle colors"):
        Step.from_dict(dict(name="x", skill="agility", task="agility", obstacles=[OBS[0]]))
    with pytest.raises(ValueError, match="spell"):
        Step.from_dict(dict(name="x", skill="magic", task="cast"))
