import pytest

from skillbot.game import BotError, StopBot
from skillbot.planner import TASK_TYPES, Planner
from skillbot.session import Session, sample
from skillbot.tasks import Task

from fakes import LAYOUT, TREE, blank, config, make_game


class FakeLevels:
    def __init__(self, levels, reader_complete=True):
        self.levels = dict(levels)
        self.reader = type("R", (), {"complete": lambda self: reader_complete})()
        self.refreshes = 0

    def get(self, skill):
        return self.levels.get(skill, 1)

    def refresh(self, skills):
        self.refreshes += 1


class ScriptedTask(Task):
    """Each batch raises the step's level by one (or runs the step's script)."""
    script = {}

    def run_batch(self):
        action = self.script.get(self.step.name, "level")
        if action == "error":
            raise BotError("boom")
        if action == "exhausted":
            return "exhausted"
        self.levels.levels[self.step.skill] = self.levels.get(self.step.skill) + 1
        self.log.append(self.step.name)
        return "ok"


@pytest.fixture
def scripted(monkeypatch):
    monkeypatch.setitem(TASK_TYPES, "gather", ScriptedTask)
    ScriptedTask.log = []
    ScriptedTask.script = {}
    return ScriptedTask


def steps(*specs):
    return [dict(name=n, skill=s, task="gather", target=TREE, until_level=u, items=["logs"])
            for n, s, u in specs]


def test_plan_trains_each_step_to_its_level_then_stops(scripted):
    cfg = config(steps(("trees", "woodcutting", 3), ("oaks", "woodcutting", 5),
                       ("mine", "mining", 2)))
    game, fake = make_game(cfg)
    levels = FakeLevels({"woodcutting": 1, "mining": 1})
    scripted.levels = levels
    with pytest.raises(StopBot, match="plan complete"):
        Planner(game, levels).run()
    assert scripted.log == ["trees", "trees", "oaks", "oaks", "mine"]


def test_steps_already_done_are_skipped(scripted):
    cfg = config(steps(("trees", "woodcutting", 15), ("oaks", "woodcutting", 16)))
    game, _ = make_game(cfg)
    levels = FakeLevels({"woodcutting": 15})
    scripted.levels = levels
    with pytest.raises(StopBot):
        Planner(game, levels).run()
    assert scripted.log == ["oaks"]


def test_stops_after_repeated_errors(scripted):
    cfg = config(steps(("trees", "woodcutting", 5)), max_consecutive_errors=3)
    game, fake = make_game(cfg)
    scripted.levels = FakeLevels({})
    scripted.script = {"trees": "error"}
    with pytest.raises(StopBot, match="3 errors in a row"):
        Planner(game, scripted.levels).run()
    assert fake.keys.count("esc") >= 4       # recovery closed interfaces between tries


def test_stops_when_every_step_is_out_of_supplies(scripted):
    cfg = config(steps(("cook", "cooking", 50)))
    game, _ = make_game(cfg)
    scripted.levels = FakeLevels({})
    scripted.script = {"cook": "exhausted"}
    with pytest.raises(StopBot, match="no step could make progress"):
        Planner(game, scripted.levels).run()


def logged_in_screen():
    img = blank()
    for x, y in LAYOUT.fingerprint_points:
        img[y - 3:y + 4, x - 3:x + 4] = (150, 130, 100)
    return img


def test_session_recognises_login_screen():
    game, fake = make_game(config())
    fake.img = logged_in_screen()
    session = Session(game, sample(fake.img, LAYOUT.fingerprint_points))
    assert session.logged_in(fake.img)
    assert not session.logged_in(blank())


def test_logout_stops_when_configured(monkeypatch):
    game, fake = make_game(config(on_logout="stop"))
    session = Session(game, sample(logged_in_screen(), LAYOUT.fingerprint_points))
    with pytest.raises(StopBot, match="logged out"):
        session.ensure()


def test_relogin_uses_environment_credentials(monkeypatch):
    monkeypatch.setenv("SKILLBOT_USERNAME", "bob")
    monkeypatch.setenv("SKILLBOT_PASSWORD", "hunter2")
    game, fake = make_game(config(on_logout="relogin"))
    session = Session(game, sample(logged_in_screen(), LAYOUT.fingerprint_points))

    def play(fake, pt):
        if tuple(pt) == LAYOUT.login_play:
            fake.img = logged_in_screen()
    fake.on_click.append(play)
    session.ensure()
    assert ("type", "bob") in fake.keys and ("type", "hunter2") in fake.keys
    assert session.logged_in(fake.img)


def test_relogin_without_credentials_stops(monkeypatch):
    monkeypatch.delenv("SKILLBOT_USERNAME", raising=False)
    monkeypatch.delenv("SKILLBOT_PASSWORD", raising=False)
    game, _ = make_game(config(on_logout="relogin"))
    session = Session(game, sample(logged_in_screen(), LAYOUT.fingerprint_points))
    with pytest.raises(StopBot, match="SKILLBOT_USERNAME"):
        session.ensure()


def test_resync_resets_the_client_before_training(scripted):
    cfg = config(steps(("trees", "woodcutting", 2)))
    game, fake = make_game(cfg)
    levels = FakeLevels({"woodcutting": 1})
    scripted.levels = levels
    with pytest.raises(StopBot):
        Planner(game, levels).run()
    assert fake.keys[:2] == ["esc", "esc"]               # closed whatever was open
    assert fake.clicks[0][0] == LAYOUT.tabs["inventory"]  # then the inventory tab
    assert levels.refreshes >= 1


def test_logout_waits_out_the_combat_timer():
    game, fake = make_game(config())
    fake.img = logged_in_screen()
    session = Session(game, sample(fake.img, LAYOUT.fingerprint_points))
    tries = []

    def click(fake, pt):
        if tuple(pt) == LAYOUT.logout_button:
            tries.append(fake.t)
            if len(tries) == 2:                   # the first try is "in combat"
                fake.img = blank()
    fake.on_click.append(click)
    assert session.logout() and len(tries) == 2
    assert session.logout() and len(tries) == 2   # already out: nothing to click


def test_handover_flag_stops_between_batches_and_logs_the_step(scripted, tmp_path):
    from skillbot.history import read_events
    from skillbot.planner import HANDOVER
    cfg = config(steps(("trees", "woodcutting", 10)))
    game, fake = make_game(cfg)
    levels = FakeLevels({"woodcutting": 1})
    scripted.levels = levels
    planner = Planner(game, levels, status_dir=tmp_path)
    scripted.script = {}
    orig = ScriptedTask.run_batch

    def batch(self):
        if len(self.log) == 2:
            (tmp_path / "handover").write_text("")
        return orig(self)
    ScriptedTask.run_batch = batch
    try:
        with pytest.raises(StopBot, match=HANDOVER):
            planner.run()
    finally:
        ScriptedTask.run_batch = orig
    assert scripted.log == ["trees"] * 3
    (step,) = [e for e in read_events(tmp_path) if e["event"] == "step"]
    assert step["from"] == 1 and step["to"] == 4 and step["skill"] == "woodcutting"
