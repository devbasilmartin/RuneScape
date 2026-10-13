import pytest

from skillbot.colors import Registry
from skillbot.game import StopBot
from skillbot.library import Method
from skillbot.planner import TASK_TYPES, Planner
from skillbot.schedule import DONE, TIME_UP, Schedule, Store, entry_step, run_schedule
from skillbot.tasks import Task

from fakes import config, make_game
from test_planner_session import FakeLevels

LIB = {
    "trees": Method.from_dict("trees", {"name": "trees", "skills": ["woodcutting"],
                                        "levels": [1, 15], "step": {
                                            "task": "gather", "target": "tree",
                                            "items": ["logs"], "when_full": "drop"}}),
    "fish": Method.from_dict("fish", {"name": "fish", "skills": ["fishing"],
                                      "levels": [1, 20], "step": {
                                          "task": "gather", "target": "fishing_spot",
                                          "items": ["logs"], "when_full": "bank"}}),
    "hard": Method.from_dict("hard", {"name": "hard", "skills": ["mining"],
                                      "levels": [30, 99], "step": {
                                          "task": "gather", "target": "rock",
                                          "items": ["logs"]}}),
    "alch": Method.from_dict("alch", {"name": "alch", "skills": ["magic"], "levels": [1, 99],
                                      "step": {"task": "agility",
                                               "obstacles": ["tree", "rock"]}}),
}


class Worker(Task):
    """A batch takes a minute; `supply` limits how many batches a method can do."""
    log, supply, levels = [], {}, None

    def run_batch(self):
        left = self.supply.get(self.step.skill)
        if left is not None:
            if left == 0:
                return "exhausted"
            self.supply[self.step.skill] = left - 1
        self.game.wait(60)
        self.log.append(self.step.name)
        if self.step.skill in self.gains:
            self.levels.levels[self.step.skill] += 1
        return "ok"


class FakeSession:
    def __init__(self):
        self.logouts = 0

    def ensure(self):
        pass

    def logout(self):
        self.logouts += 1
        return True


@pytest.fixture
def world(monkeypatch):
    monkeypatch.setitem(TASK_TYPES, "gather", Worker)
    Worker.log, Worker.supply, Worker.gains = [], {}, set()
    game, fake = make_game(config())
    Worker.levels = levels = FakeLevels({"woodcutting": 10, "fishing": 10, "mining": 1,
                                         "magic": 1})
    notes = []
    planner = Planner(game, levels, FakeSession(), supervised=True, notify=notes.append)
    planner.resync = lambda skills: None
    return planner, fake, notes


def run(planner, d):
    with pytest.raises(StopBot) as e:
        run_schedule(planner, Schedule.from_dict(d, LIB), LIB, Registry.load(), {})
    return str(e.value)


def test_entries_run_for_their_minutes_then_log_out(world):
    planner, fake, notes = world
    reason = run(planner, {"entries": [{"method": "trees", "minutes": 5},
                                       {"method": "fish", "minutes": 3}]})
    assert reason == DONE and planner.session.logouts == 1
    assert Worker.log == ["trees"] * 5 + ["fish"] * 3       # past trees' own range? kept going
    assert not notes


def test_until_level_ends_an_entry_and_the_upper_range_is_ignored(world):
    planner, fake, notes = world
    Worker.gains = {"woodcutting"}
    run(planner, {"entries": [{"method": "trees", "until_level": 18}]})   # trees are 1-15
    assert planner.levels.get("woodcutting") == 18 and len(Worker.log) == 8


def test_running_out_early_and_not_starting_are_skipped_with_a_note(world):
    planner, fake, notes = world
    Worker.supply = {"woodcutting": 2, "fishing": 0}
    reason = run(planner, {"entries": [{"method": "trees", "minutes": 10},
                                       {"method": "fish", "minutes": 5},
                                       {"method": "hard", "minutes": 5}]})
    assert reason == DONE and Worker.log == ["trees", "trees"]
    assert "trees ran out after 2 of 10 min" in notes[0]
    assert "fish couldn't get started" in notes[1]
    assert "hard: needs mining 30 (you have 1)" in notes[2]


def test_repeat_for_hours_cycles_then_logs_out(world):
    planner, fake, notes = world
    reason = run(planner, {"repeat": {"hours": 1},
                           "entries": [{"method": "trees", "minutes": 10},
                                       {"method": "fish", "minutes": 5}]})
    assert reason == TIME_UP and planner.session.logouts == 1
    assert 55 <= len(Worker.log) <= 61 and Worker.log[10:15] == ["fish"] * 5


def test_repeat_forever_stops_when_nothing_can_run(world):
    planner, fake, notes = world
    Worker.supply = {"woodcutting": 3}
    reason = run(planner, {"repeat": "forever", "entries": [{"method": "trees"}]})
    assert "nothing in the schedule could run" in reason and len(Worker.log) == 3


def test_unattended_skips_unproven_entries(world, tmp_path):
    from skillbot.trust import TrustStore
    planner, fake, notes = world
    planner.supervised, planner.trust = False, TrustStore(tmp_path / "trust.json")
    reason = run(planner, {"entries": [{"method": "trees", "minutes": 2}]})
    assert reason == DONE and Worker.log == [] and "experimental" in notes[0]


def test_validation():
    def bad(d, match):
        with pytest.raises(ValueError, match=match):
            Schedule.from_dict(d, LIB)
    bad({"entries": []}, "at least one")
    bad({"entries": [{"method": "nope"}]}, "no method")
    bad({"entries": [{"method": "alch", "when_full": "drop"}]}, "always banks")
    bad({"entries": [{"method": "trees", "until_level": 120}]}, "2-99")
    bad({"repeat": "twice", "entries": [{"method": "trees"}]}, "repeat")
    bad({"entries": [{"method": "trees", "skill": "attack"}]}, "trains woodcutting")


def test_store_and_bank_override(tmp_path):
    store = Store(tmp_path / "schedules")
    s = Schedule.from_dict({"repeat": {"hours": 2}, "entries": [
        {"method": "trees", "minutes": 60, "when_full": "bank"}]}, LIB)
    store.save("bow loop", s)
    assert store.names() == ["bow loop"]
    assert store.load("bow loop", LIB).to_dict() == s.to_dict()
    with pytest.raises(ValueError):
        store.path("../evil")
    step = entry_step(s.entries[0], LIB["trees"], Registry.load(), {})
    assert step.when_full == "bank" and step.name == "trees [bank]" and step.max_minutes == 60
    same = Schedule.from_dict({"entries": [{"method": "fish", "when_full": "bank"}]}, LIB)
    assert entry_step(same.entries[0], LIB["fish"], Registry.load(), {}).name == "fish"


def test_combat_can_drop_and_then_stops_when_out_of_food():
    cows = Method.from_dict("cows", {"name": "cows", "skills": ["attack", "strength"],
                                     "levels": [1, 40], "step": {
                                         "task": "combat", "target": "cow", "loot": "loot",
                                         "items": ["cowhide"], "food": ["trout"],
                                         "when_full": "bank"}})
    assert cows.can_drop
    s = Schedule.from_dict({"entries": [{"method": "cows", "skill": "strength",
                                         "when_full": "drop"}]}, {"cows": cows})
    step = entry_step(s.entries[0], cows, Registry.load(), {})
    assert step.when_full == "drop" and step.when_out_of_food == "stop"
    assert step.name == "cows (strength) [drop]"
    banked = entry_step(Schedule.from_dict({"entries": [{"method": "cows"}]},
                                           {"cows": cows}).entries[0], cows, Registry.load(), {})
    assert banked.when_out_of_food == "bank"


def test_a_stopped_schedule_carries_on_at_the_entry_it_was_on(world, tmp_path):
    """An account handover (or a restart) stops the run part way; the next run of the same
    schedule starts at that entry, and a finished one starts from the top again."""
    planner, fake, notes = world
    resume = tmp_path / "resume.json"
    d = {"entries": [{"method": "trees", "minutes": 2}, {"method": "fish", "minutes": 2}]}
    sched = Schedule.from_dict(d, LIB)
    stop_in_fish = lambda: Worker.log.count("fish") == 1           # noqa: E731
    orig = Worker.run_batch

    def handover(self):
        if stop_in_fish():
            raise StopBot("handover")
        return orig(self)
    Worker.run_batch = handover
    try:
        with pytest.raises(StopBot, match="handover"):
            run_schedule(planner, sched, LIB, Registry.load(), {}, resume=resume)
    finally:
        Worker.run_batch = orig
    Worker.log.clear()
    with pytest.raises(StopBot):
        run_schedule(planner, sched, LIB, Registry.load(), {}, resume=resume)
    assert Worker.log == ["fish", "fish"]                  # carried on with fishing
    assert not resume.exists()                             # finished: next run from the top


def test_rotation_turns_can_run_a_saved_schedule():
    from skillbot.rotation import RotationConfig
    cfg = RotationConfig.from_dict({"accounts": [
        {"profile": "a", "schedule": "f2p-skills"}, {"profile": "b", "goals": "g.yaml"},
        {"profile": "c"}]})
    assert [t.mode for t in cfg.accounts] == ["schedule:f2p-skills", "g.yaml", None]
    with pytest.raises(ValueError, match="not both"):
        RotationConfig.from_dict({"accounts": [{"profile": "a", "schedule": "s",
                                                "goals": "g"}]})
