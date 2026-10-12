import json

import pytest

from skillbot.config import Step
from skillbot.game import StopBot
from skillbot.hp_guard import DangerLog, HPGuard

from fakes import config, make_game, put_item, slot_at
from test_combat import HP_COLOR, draw_hp


class Session:
    def __init__(self):
        self.logouts = 0

    def logout(self, attempts=6):
        self.logouts += 1
        return True


class World:
    """Your HP, which food heals by 30%."""

    def __init__(self, fake, hp):
        self.fake, self.hp, self.eaten = fake, hp, 0
        draw_hp(fake.img, hp)
        fake.on_click.append(self.click)

    def set(self, hp):
        self.hp = hp
        draw_hp(self.fake.img, hp)

    def click(self, fake, pt):
        i = slot_at(pt)
        if i is not None and fake.items().get(i) in ("shrimps", "trout") and not fake.shift:
            put_item(fake.img, i, None)
            self.eaten += 1
            self.set(min(1.0, self.hp + 0.3))


def setup(hp=1.0, food=(), step=None, tmp_path=None):
    game, fake = make_game(config(hp_bar_color=HP_COLOR))
    put_item(fake.img, 0, "logs")              # something tagged: the inventory is open
    for i, name in enumerate(food, 1):
        put_item(fake.img, i, name)
    world = World(fake, hp)
    session = Session()
    danger = DangerLog(tmp_path / "danger.json" if tmp_path else None)
    game.hp_guard = HPGuard(game, session, danger, level=lambda skill: 20)
    game.hp_guard.step = step
    return game, fake, world, session


def later(game, fake, seconds=3):
    fake.t += seconds
    return game.grab()


def chop(**kw):
    return Step.from_dict({"name": "oaks", "skill": "woodcutting", "task": "gather",
                           "target": (0, 255, 255), "items": ["logs"], **kw})


def test_eats_any_food_during_any_activity():
    game, fake, world, _ = setup(hp=0.9, food=["shrimps"], step=chop())
    later(game, fake)
    world.set(0.4)
    later(game, fake)
    assert world.eaten == 1 and world.hp == pytest.approx(0.7)
    assert game.hp_guard.stats["eaten"] == 1


def test_the_steps_own_food_list_wins():
    game, fake, world, _ = setup(hp=0.4, food=["shrimps", "trout"], step=chop(food=["trout"]))
    later(game, fake)
    assert fake.items().get(1) == "shrimps" and 2 not in fake.items()


def test_no_food_and_being_hit_logs_out_and_says_why(tmp_path):
    game, fake, world, session = setup(hp=0.8, step=chop(), tmp_path=tmp_path)
    later(game, fake)
    world.set(0.45)
    with pytest.raises(StopBot, match="HP 45% and no food left, so I logged out"):
        later(game, fake)
    assert session.logouts == 1
    saved = json.loads((tmp_path / "danger.json").read_text())
    assert saved["oaks"][0]["level"] == 20


def test_low_but_steady_hp_carries_on():
    """E.g. woodcutting right after a fight, with nothing hitting you."""
    game, fake, world, session = setup(hp=0.35, step=chop())
    for _ in range(5):
        later(game, fake, 30)
    assert session.logouts == 0 and fake.clicks == []


def test_critical_hp_flees_even_when_steady():
    game, fake, world, session = setup(hp=0.15, step=chop())
    with pytest.raises(StopBot):
        later(game, fake)
    assert session.logouts == 1


def test_no_bar_on_screen_does_nothing():
    game, fake, world, session = setup(hp=0.0, step=chop())
    later(game, fake)
    assert session.logouts == 0 and fake.clicks == []


def test_a_step_that_banks_for_food_fetches_its_own():
    fight = Step.from_dict({"name": "cows", "skill": "attack", "task": "combat",
                            "target": (255, 128, 128), "food": ["trout"]})
    game, fake, world, session = setup(hp=0.8, step=fight)
    later(game, fake)
    world.set(0.3)
    later(game, fake)
    assert session.logouts == 0
    world.set(0.1)
    with pytest.raises(StopBot):
        later(game, fake)


def test_never_eats_while_dropping():
    game, fake, world, _ = setup(hp=0.9, food=["shrimps"], step=chop())
    later(game, fake)
    world.set(0.3)
    fake.t += 3
    game.drop(names={"logs"})
    assert [slot_at(pt) for pt, shift in fake.clicks if shift] == [0]
    assert world.eaten == 1                    # before shift went down, not during


def test_checks_only_every_couple_of_seconds():
    game, fake, world, _ = setup(hp=0.3, food=["shrimps", "shrimps"], step=chop())
    later(game, fake)
    world.set(0.3)
    game.grab()
    assert world.eaten == 1


def test_danger_log(tmp_path):
    now = [1000.0]
    log = DangerLog(tmp_path / "d.json", clock=lambda: now[0])
    assert log.add("oaks", 20) == 1 and log.dangerous_until("oaks") is None
    assert log.add("oaks", 22) == 2 and log.dangerous_until("oaks") == 22
    now[0] += 15 * 86400                       # two weeks later it's forgotten
    assert log.dangerous_until("oaks") is None
    assert DangerLog(tmp_path / "d.json").data["oaks"][1]["level"] == 22


def test_planner_skips_a_dangerous_step_until_past_the_level(tmp_path):
    from skillbot.planner import Planner
    game, fake, world, _ = setup(step=None, tmp_path=tmp_path)
    for level in (20, 21):
        game.hp_guard.danger.add("oaks", level)

    class Levels:
        level = 21

        def get(self, skill):
            return self.level
    notes = []
    planner = Planner(game, Levels(), notify=notes.append)
    assert not planner.allowed(chop()) and "past 21" in notes[0]
    planner.levels.level = 22
    assert planner.allowed(chop())


def test_every_known_food_has_a_color():
    from pathlib import Path
    from skillbot.hp_guard import FOOD
    text = (Path(__file__).parent.parent / "colors.yaml").read_text()
    assert all(f"\n{f}:" in text for f in FOOD)
