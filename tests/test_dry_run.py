"""Every library method, end to end against the fake client: on a blank screen and in a
"chaos" world (random highlights and items that change as the bot clicks and waits).
A method may give up with BotError or StopBot, never crash with anything else."""
import random

import pytest

from skillbot.colors import Registry
from skillbot.config import Config
from skillbot.game import BotError, StopBot
from skillbot.library import load_library
from skillbot.planner import make_task

from fakes import ITEMS, FakeClient, make_game, put_item

SPELLS = {k: (600, 300) for k in ("varrock_teleport", "camelot_teleport", "high_alchemy",
                                  "ourania_teleport", "reanimate_adept")}
FAKE_HOURS = 0.5
METHODS = load_library()


class OutOfTime(Exception):
    pass


def scramble(fake, rng, colors):
    for _ in range(rng.randint(0, 6)):
        x, y, w, h = rng.randint(5, 500), rng.randint(5, 320), rng.randint(6, 50), \
            rng.randint(6, 50)
        fake.img[y:y + h, x:x + w] = rng.choice(colors)
    for i in rng.sample(range(28), rng.randint(0, 8)):
        put_item(fake.img, i, rng.choice(list(ITEMS)) if rng.random() < .7 else None)


@pytest.fixture(scope="module")
def world():
    reg = Registry.load()
    return reg, Config.load("config.example.yaml"), [tuple(e.rgb) for e in reg.entries.values()]


@pytest.mark.parametrize("chaos", [False, True], ids=["blank", "chaos"])
@pytest.mark.parametrize("mid", sorted(METHODS))
def test_method_never_crashes(world, mid, chaos):
    reg, cfg, colors = world
    m = METHODS[mid]
    step = m.to_step(m.skills[0], m.levels[1], 30, reg, SPELLS)
    fake, rng = FakeClient(), random.Random(mid)

    def tick(f):
        if f.t > FAKE_HOURS * 3600:
            raise OutOfTime
        if chaos and rng.random() < .3:
            scramble(f, rng, colors)

    if chaos:
        scramble(fake, rng, colors)
        fake.on_click.append(lambda f, pt: rng.random() < .5 and scramble(f, rng, colors))
    fake.on_wait.append(tick)
    game, _ = make_game(cfg, fake)
    try:
        make_task(game, step).run_batch()
    except (BotError, StopBot, OutOfTime):
        pass
