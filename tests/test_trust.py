import datetime as dt

import pytest

from skillbot.game import BotError, StopBot
from skillbot.planner import TASK_TYPES, Planner
from skillbot.tasks import Task
from skillbot.trust import TrustStore, fingerprint

from fakes import TREE, config, make_game


class Clock:
    def __init__(self):
        self.t = dt.datetime(2026, 10, 1, 12).timestamp()

    def __call__(self):
        return self.t


def store(tmp_path, clock=None):
    return TrustStore(tmp_path / "trust.json", clock=clock or Clock())


def test_new_steps_are_experimental_and_promote_after_clean_supervised_hours(tmp_path):
    s = store(tmp_path)
    s.record("trees", "c1")
    assert s.level("trees") == "experimental"
    s.add_time("trees", 3600, supervised=True)
    s.add_error("trees", supervised=True)               # the clean hours start over
    s.add_time("trees", 3600, supervised=True)
    assert s.evaluate("trees") is None
    s.add_time("trees", 3600, supervised=True)
    assert "promoted to trial" in s.evaluate("trees")
    assert s.level("trees") == "trial"


def test_trial_needs_hours_days_few_errors_and_no_stops(tmp_path):
    clock = Clock()
    s = store(tmp_path, clock)
    s.record("trees", "c1")
    s.set_level("trees", "trial")
    for day in range(2):
        s.add_time("trees", 12 * 3600, supervised=False)
        clock.t += 86400
    assert s.evaluate("trees") is None                  # 24h, but only 2 days
    s.add_time("trees", 3600, supervised=False)
    for _ in range(7):                                  # 25h allows 6 errors
        s.add_error("trees", supervised=False)
    assert s.evaluate("trees") is None
    s.set_level("trees", "trial")
    for day in range(3):
        s.add_time("trees", 9 * 3600, supervised=False)
        clock.t += 86400
    s.add_error("trees", supervised=False)
    assert "promoted to trusted" in s.evaluate("trees")


def test_a_stop_during_trial_blocks_promotion(tmp_path):
    clock = Clock()
    s = store(tmp_path, clock)
    s.record("x", "c")
    s.set_level("x", "trial")
    s.add_stop("x")
    for _ in range(3):
        s.add_time("x", 9 * 3600, supervised=False)
        clock.t += 86400
    assert s.evaluate("x") is None


def test_trusted_demoted_after_two_stops_in_a_day(tmp_path):
    clock = Clock()
    s = store(tmp_path, clock)
    s.record("x", "c")
    s.set_level("x", "trusted")
    s.add_stop("x")
    clock.t += 2 * 86400
    s.add_stop("x")
    assert s.evaluate("x") is None                      # two days apart: fine
    clock.t += 3600
    s.add_stop("x")
    assert "demoted to trial" in s.evaluate("x")


def test_code_change_resets(tmp_path):
    s = store(tmp_path)
    s.record("x", "v1")
    s.set_level("x", "trusted")
    _, msg = s.record("x", "v2")
    assert s.level("x") == "trial" and "changed" in msg
    s.record("y", "v1")
    _, msg = s.record("y", "v2")
    assert s.level("y") == "experimental" and msg is None
    assert TrustStore(tmp_path / "trust.json").level("x") == "trial"   # persisted


def test_fingerprint_tracks_settings(tmp_path):
    from skillbot.config import Step
    a = Step.from_dict(dict(name="t", skill="woodcutting", task="gather", target=TREE,
                            items=["logs"]))
    b = Step.from_dict(dict(name="t", skill="woodcutting", task="gather", target=TREE,
                            items=["logs"], idle_timeout=30))
    cls = TASK_TYPES["gather"]
    assert fingerprint(a, cls) == fingerprint(a, cls) != fingerprint(b, cls)


# ---- planner integration ---------------------------------------------------------------

class Levels:
    def __init__(self):
        self.levels = {}
        self.reader = type("R", (), {"complete": lambda self: True})()

    def get(self, skill):
        return self.levels.get(skill, 1)

    def refresh(self, skills):
        pass


class Scripted(Task):
    script = "level"

    def run_batch(self):
        if self.script == "error":
            raise BotError("boom")
        self.game.wait(600)                              # each batch takes 10 minutes
        if self.script == "level":
            self.levels.levels[self.step.skill] = self.levels.get(self.step.skill) + 1
        return "ok"


@pytest.fixture
def scripted(monkeypatch):
    monkeypatch.setitem(TASK_TYPES, "gather", Scripted)
    Scripted.levels = Levels()
    Scripted.script = "level"
    return Scripted


def planner(tmp_path, steps, supervised=False, **cfg_kw):
    cfg = config([dict(name=n, skill=s, task="gather", target=TREE, until_level=u,
                       items=["logs"]) for n, s, u in steps], **cfg_kw)
    game, fake = make_game(cfg)
    sent = []
    p = Planner(game, Scripted.levels, trust=TrustStore(tmp_path / "trust.json",
                                                         clock=lambda: fake.t + 1.8e9),
                supervised=supervised, notify=sent.append)
    return p, fake, sent


def test_unsupervised_run_skips_experimental_steps(tmp_path, scripted):
    p, fake, sent = planner(tmp_path, [("trees", "woodcutting", 5)])
    with pytest.raises(StopBot, match="only experimental steps"):
        p.run()
    assert any("experimental" in m for m in sent)
    assert scripted.levels.get("woodcutting") == 1


def test_supervised_run_stops_at_first_error_without_crediting_time(tmp_path, scripted):
    p, fake, sent = planner(tmp_path, [("trees", "woodcutting", 99)], supervised=True)
    scripted.script = "error"
    with pytest.raises(StopBot, match="first error"):
        p.run()
    assert p.trust.data["trees"]["supervised_s"] == 0


def test_supervised_hours_promote_then_trial_runs_in_reported_slices(tmp_path, scripted):
    p, fake, sent = planner(tmp_path, [("trees", "woodcutting", 14)], supervised=True)
    with pytest.raises(StopBot, match="plan complete"):
        p.run()                                          # 13 batches x 10 min > 2h
    assert p.trust.level("trees") == "trial"
    assert any("promoted to trial" in m for m in sent)

    scripted.script = "xp"                               # no level-ups: runs until the slice ends
    p2, fake2, sent2 = planner(tmp_path, [("trees", "woodcutting", 99)])
    p2.run_step(p2.game.cfg.plan[0])
    assert 120 * 60 <= fake2.t < 140 * 60                # one 2-hour slice
    assert any(m.startswith("trial report") for m in sent2)
