import pytest

from skillbot.config import Step
from skillbot.planner import make_task

import fakes
from fakes import BG, LAYOUT, config, make_game, outline

EXTRA = {"coin_pouch": (64, 128, 192), "trout": (128, 0, 255)}
KNIGHT, HP = (64, 64, 192), (255, 0, 0)


@pytest.fixture(autouse=True)
def extra_items():
    before = dict(fakes.ITEMS)
    fakes.ITEMS.update(EXTRA)
    yield
    fakes.ITEMS.clear()
    fakes.ITEMS.update(before)


def draw_hp(img, frac):
    bar = LAYOUT.hp_bar
    img[bar.y:bar.y + bar.h, bar.x:bar.x + bar.w] = BG
    n = int(bar.h * frac)
    if n:
        img[bar.y + bar.h - n:bar.y + bar.h, bar.x:bar.x + bar.w] = HP


def test_pickpockets_waits_out_stuns_and_opens_pouches():
    game, fake = make_game(config(extra_items=EXTRA, hp_bar_color=HP))
    outline(fake.img, 245, 155, 30, 30, KNIGHT)
    fakes.put_item(fake.img, 1, "trout")
    state = {"attempt": 0, "hp": 1.0, "opened": 0}
    draw_hp(fake.img, 1.0)

    def click(f, pt):
        if 245 <= pt[0] < 275 and 155 <= pt[1] < 185:
            state["attempt"] += 1
            if state["attempt"] % 4 == 0:                    # every 4th attempt fails
                state["hp"] -= 0.02
                draw_hp(f.img, state["hp"])
            else:
                fakes.put_item(f.img, 2, "coin_pouch")
        elif f.items().get(2) == "coin_pouch" and LAYOUT.slot(2).x <= pt[0] < LAYOUT.slot(2).x + 32:
            state["opened"] += 1
            fakes.put_item(f.img, 2, None)
    fake.on_click.append(click)
    step = Step.from_dict(dict(name="knights", skill="thieving", task="thieve", target=KNIGHT,
                               items=[], food=["trout"], eat_below=0.3, pouch="coin_pouch",
                               open_every=10, attempts_per_batch=40))
    task = make_task(game, step)
    t0 = fake.t
    assert task.run_batch() == "ok"
    assert task.stats["attempts"] == 40 and task.stats["stuns"] == 10
    assert state["opened"] == 3                               # at attempts 10, 20, 30
    assert fake.t - t0 >= 10 * 4.6                            # waited out every stun
