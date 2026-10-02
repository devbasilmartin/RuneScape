import pytest
import yaml

from skillbot.colors import Registry
from skillbot.config import Config
from skillbot.goals import Chooser, Goals, QuestLog
from skillbot.library import Method, load_library
from skillbot.xp import xp_between, xp_for_level


def cfg():
    return Config.load("config.example.yaml")


def lib(**extra):
    methods = load_library()
    methods.update(extra)
    return methods


def chooser(goals, methods=None, quests=(), **kw):
    log = QuestLog(None)
    for q in quests:
        log.add(q)
    return Chooser(goals, methods or lib(), cfg(), Registry.load(), log, **kw)


def test_xp_table():
    assert xp_for_level(1) == 0 and xp_for_level(2) == 83 and xp_for_level(99) == 13034431
    assert xp_between(50, 40) == 0


def test_starter_library_builds_steps_with_the_example_config():
    reg = Registry.load()
    spells = {"varrock_teleport": (1, 1), "camelot_teleport": (2, 2), "high_alchemy": (3, 3)}
    for m in load_library().values():
        for skill in m.skills:
            step = m.to_step(skill, m.levels[1], 0, reg, spells)
            assert step.skill == skill


def test_magic_methods_explain_missing_spell_positions():
    g = Goals(targets={"magic": 99})
    text = chooser(g).explain({"magic": 30})
    assert "spell 'varrock_teleport' has no position" in text


def test_goals_file(tmp_path):
    path = tmp_path / "goals.yaml"
    path.write_text(yaml.safe_dump({"unlocks_first": {"magic": 45}, "exclude": ["sailing"],
                                    "overrides": {"woodcutting": "oaks_draynor"}}))
    g = Goals.load(path)
    assert g.unlocks == {"magic": 45} and "sailing" not in g.targets and g.targets["mining"] == 99
    path.write_text(yaml.safe_dump({"unlocks_first": {"magik": 45}}))
    with pytest.raises(ValueError, match="unknown skill"):
        Goals.load(path)


def test_unlock_goals_come_first_in_order():
    g = Goals(unlocks={"attack": 10, "woodcutting": 50}, targets={"fishing": 99})
    d = chooser(g).next({"woodcutting": 35})
    assert d.skill == "attack" and d.phase == "unlock" and d.target == 10
    assert d.step.style == 0                                    # attack style for attack
    d = chooser(g).next({"attack": 10, "woodcutting": 35})
    assert d.skill == "woodcutting" and d.method.id == "willows_draynor" and d.target == 50


def test_rotation_picks_most_hours_left():
    g = Goals(targets={"woodcutting": 99, "fishing": 20})
    d = chooser(g).next({"woodcutting": 50, "fishing": 1})
    assert d.phase == "rotation" and d.skill == "woodcutting"   # far more hours to go
    assert d.target == 60                                       # willows only go to 60
    assert d.step.max_minutes == 120


def test_method_ranking_reliability_then_profit_then_xp():
    fast = Method.from_dict("fast_willows", {
        "skills": ["woodcutting"], "levels": [30, 60], "xp_per_hour": 90000,
        "profit_per_hour": 15000, "reliability": 3,
        "step": {"task": "gather", "target": "willow_tree", "items": ["willow_logs"]}})
    rich = Method.from_dict("rich_willows", {
        "skills": ["woodcutting"], "levels": [30, 60], "xp_per_hour": 20000,
        "profit_per_hour": 90000, "reliability": 5,
        "step": {"task": "gather", "target": "willow_tree", "items": ["willow_logs"]}})
    g = Goals(targets={"woodcutting": 99})
    d = chooser(g, lib(fast_willows=fast, rich_willows=rich)).next({"woodcutting": 40})
    assert d.method.id == "rich_willows"          # reliability 5 beats 3; then profit wins
    g.overrides = {"woodcutting": "fast_willows"}
    d = chooser(g, lib(fast_willows=fast, rich_willows=rich)).next({"woodcutting": 40})
    assert d.method.id == "fast_willows"


def test_quests_trust_and_setup_gate_methods():
    from skillbot.trust import TrustStore
    g = Goals(targets={"runecraft": 99})
    assert chooser(g).next({"runecraft": 20}) is None                 # needs Rune Mysteries
    assert chooser(g, quests=["Rune Mysteries"]).next({"runecraft": 20}).method.id \
        == "fire_runes_alkharid"
    trust = TrustStore(None)
    c = chooser(g, quests=["Rune Mysteries"], trust=trust)
    assert c.next({"runecraft": 20}) is None                          # still experimental
    assert "experimental" in c.explain({"runecraft": 20})
    bad = Method.from_dict("needs_tags", {"skills": ["fishing"], "xp_per_hour": 1,
                                          "step": {"task": "gather", "target": "fishing_spot",
                                                   "items": ["raw_lobster"]}})
    step, reason = chooser(Goals()).check(bad, "fishing", {})
    assert step is None and "raw_lobster" in reason


def test_resting_a_method_and_explain_text():
    g = Goals(unlocks={"woodcutting": 60}, targets={"woodcutting": 99})
    c = chooser(g)
    c.rest("willows_draynor", until=100.0)
    assert c.next({"woodcutting": 40}, now=50.0) is None
    assert c.next({"woodcutting": 40}, now=150.0).method.id == "willows_draynor"
    text = c.explain({"woodcutting": 40}, now=150.0)
    assert "Next: woodcutting 40 → 60" in text and "first unmet unlock goal" in text
    assert "oaks (Draynor) [✗ for levels 15-30" in text


def test_planner_runs_goals_until_done(monkeypatch):
    from skillbot.game import StopBot
    from skillbot.planner import TASK_TYPES, Planner
    from skillbot.tasks import Task

    from fakes import make_game

    class Levels:
        levels = {"woodcutting": 58}
        reader = type("R", (), {"complete": lambda self: True})()

        def get(self, s):
            return self.levels.get(s, 1)

        def refresh(self, skills):
            pass
    levels = Levels()

    class Chop(Task):
        def run_batch(self):
            levels.levels["woodcutting"] += 1
            return "ok"
    monkeypatch.setitem(TASK_TYPES, "gather", Chop)
    game, _ = make_game(cfg())
    p = Planner(game, levels)
    p.chooser = chooser(Goals(targets={"woodcutting": 60}))
    with pytest.raises(StopBot, match="nothing left"):
        p.run()
    assert levels.levels["woodcutting"] == 60
