import pytest

from skillbot.colors import Registry
from skillbot.config import Config
from skillbot.goals import Chooser, Goals, QuestLog
from skillbot.library import load_library
from skillbot.skills import combat_level


def test_combat_level():
    assert combat_level({}) == 3
    assert combat_level({s: 99 for s in ("attack", "strength", "defence", "hitpoints",
                                         "prayer")}) == 126
    assert combat_level({"attack": 20, "strength": 20, "defence": 19, "hitpoints": 20}) == 22


def test_f2p_library_is_f2p_by_default_and_the_rest_members():
    lib = load_library()
    assert not lib["cows_lumbridge"].members and not lib["fly_fishing_barbarian"].members
    assert lib["ourania_altar"].members and lib["gnome_course"].members


def test_blocked_for_f2p_accounts_and_aggressive_spots():
    lib = load_library()
    assert lib["gnome_course"].blocked("f2p", {}) == "members only"
    assert lib["gnome_course"].blocked("members", {}) is None
    low = {"woodcutting": 35}
    assert "combat 41" in lib["willows_draynor"].blocked("f2p", low)
    strong = {**low, "attack": 40, "strength": 40, "defence": 40, "hitpoints": 40}
    assert lib["willows_draynor"].blocked("f2p", strong) is None


def test_chooser_only_picks_f2p_methods_for_an_f2p_account():
    cfg = Config.load("config.example.yaml")
    cfg.account = "f2p"
    chooser = Chooser(Goals(targets={"agility": 99}), load_library(), cfg, Registry.load(),
                      QuestLog(None))
    reasons = {m.id: why for m, _, why in chooser.candidates("agility", {"agility": 1})}
    assert reasons["gnome_course"] == "members only"


def test_account_must_be_f2p_or_members(tmp_path):
    (tmp_path / "c.yaml").write_text("account: free\n")
    with pytest.raises(ValueError, match="f2p or members"):
        Config.load(tmp_path / "c.yaml")


def test_f2p_mining_and_fishing_can_drop_or_bank():
    """Drop for speed, bank to keep the ore or fish: both must work for every one."""
    from skillbot.colors import Registry
    from skillbot.places import load_places
    places = load_places(Registry.load().resolve)
    gather = [m for m in load_library().values() if not m.members
              and m.skills[0] in ("mining", "fishing") and m.task == "gather"]
    assert {m.id for m in gather} >= {"copper_tin_varrock", "iron_varrock",
                                      "net_fishing_draynor", "fly_fishing_barbarian"}
    for m in gather:
        assert m.can_drop, m.id
        assert m.step.get("bank_location") in places, m.id
        assert m.location in places, m.id
