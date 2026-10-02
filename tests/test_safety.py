import pytest

from skillbot.config import Step
from skillbot.game import StopBot
from skillbot.safety import Safety, SafetyConfig

from fakes import BG, TREE, config, make_game, outline, put_item, slot_at

DANGER, GENIE, RESPAWN, GRAVE, OTHERS = (128, 0, 0), (64, 255, 255), (255, 64, 192), \
    (192, 0, 64), (64, 192, 64)


def game_with(**kw):
    cfg = config(danger_color=DANGER, **kw)
    return make_game(cfg)


def test_clicks_avoid_random_event_npcs():
    game, fake = game_with()
    outline(fake.img, 240, 150, 40, 30, TREE)          # nearest tree...
    outline(fake.img, 235, 145, 50, 40, DANGER)        # ...with a random event on it
    outline(fake.img, 60, 40, 40, 30, TREE)            # a farther, free tree
    assert game.click_nearest(fake.grab(), TREE)
    x, y = fake.clicks[-1][0]
    assert 60 <= x < 100 and 40 <= y < 70


def test_no_click_when_every_target_is_covered():
    game, fake = game_with()
    outline(fake.img, 240, 150, 40, 30, TREE)
    outline(fake.img, 230, 140, 60, 50, DANGER)
    assert not game.click_nearest(fake.grab(), TREE)
    assert fake.clicks == []


def safety(game, **kw):
    sent = []
    s = Safety(game, SafetyConfig.from_dict(kw), GENIE, RESPAWN, GRAVE, OTHERS,
               notify=sent.append)
    return s, sent


STEP = Step.from_dict(dict(name="cows", skill="attack", task="combat", target=TREE,
                           items=["logs"], location="cow field", gear=["shrimps"]))


def test_genie_lamp_is_claimed_on_the_chosen_skill():
    game, fake = game_with(extra_items={"lamp": (0, 192, 255)})
    fake.items = lambda: game.inv.tags(fake.img)
    outline(fake.img, 245, 155, 30, 30, GENIE)
    s, sent = safety(game, genie_skill_point=[600, 300], lamp_confirm=[640, 420])

    def on_click(f, pt):
        if 245 <= pt[0] < 275 and 155 <= pt[1] < 185:          # talked to the Genie
            f.img[155:186, 245:276] = BG
            import fakes
            fakes.ITEMS["lamp"] = (0, 192, 255)
            put_item(f.img, 5, "lamp")
            del fakes.ITEMS["lamp"]
    fake.on_click.append(on_click)
    s.check(STEP)
    points = [p for p, _ in fake.clicks]
    assert (600, 300) in points and (640, 420) in points
    assert points.index((600, 300)) < points.index((640, 420))
    assert slot_at(points[1]) == 5                              # used the lamp first


def test_death_walks_back_takes_grave_and_rewears_gear():
    game, fake = game_with()
    outline(fake.img, 250, 160, 20, 20, RESPAWN)
    trips = []

    class Nav:
        def travel(self, dest, until):
            trips.append((dest, until))
            fake.img[:] = BG
            outline(fake.img, 240, 150, 30, 30, GRAVE)
            put_item(fake.img, 2, "shrimps")                    # gear back in the inventory
    game.nav = Nav()
    fake.on_click.append(lambda f, pt: f.img.__setitem__((slice(150, 181), slice(240, 271)), BG)
                         if 240 <= pt[0] < 270 and 150 <= pt[1] < 180 else None)
    s, sent = safety(game, grave_take=[300, 300])
    s.check(STEP)
    assert trips == [("cow field", GRAVE)]
    points = [p for p, _ in fake.clicks]
    assert (300, 300) in points                                 # took everything
    assert slot_at(points[-1]) == 2                             # re-equipped the gear
    assert "died during 'cows'" in sent[0]


def test_second_death_within_the_window_stops():
    game, fake = game_with()
    game.nav = type("N", (), {"travel": lambda self, d, u: None})()
    s, sent = safety(game)
    s.deaths["cows"] = [fake.t - 60]
    outline(fake.img, 250, 160, 20, 20, RESPAWN)
    with pytest.raises(StopBot, match="died twice"):
        s.check(STEP)


def test_hops_only_after_sustained_crowding_with_cooldown():
    game, fake = game_with()
    outline(fake.img, 240, 150, 40, 30, TREE)
    for x in (200, 300, 260):
        outline(fake.img, x, 120, 15, 30, OTHERS)
    s, _ = safety(game, hop_minutes=2, hop_cooldown_minutes=5)
    assert not s.between_batches(STEP)                         # crowded, but just now
    fake.t += 60
    assert not s.between_batches(STEP)
    fake.t += 70
    assert s.between_batches(STEP)                             # 2+ minutes: hop
    assert ("hotkey", "ctrl", "shift", "right") in fake.keys
    fake.t += 130
    assert not s.between_batches(STEP)                         # crowded again, but cooldown
    fake.t += 400
    assert s.between_batches(STEP)


def test_not_crowded_resets():
    game, fake = game_with()
    outline(fake.img, 240, 150, 40, 30, TREE)
    outline(fake.img, 200, 120, 15, 30, OTHERS)                # just one other player
    s, _ = safety(game)
    fake.t += 1000
    assert not s.between_batches(STEP) and s.crowded_since is None
