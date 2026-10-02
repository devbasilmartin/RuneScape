import json

from skillbot.library import load_library
from skillbot.pricewatch import PriceWatch, current_methods, supplies
from skillbot.prices import DAY, Ledger, PriceConfig, Prices, wiki_name
from skillbot.upgrades import Upgrades

MAPPING = [{"id": 1519, "name": "Willow logs"}, {"id": 1436, "name": "Rune essence"},
           {"id": 554, "name": "Fire rune"}, {"id": 1739, "name": "Cowhide"},
           {"id": 333, "name": "Trout"}]


class Market:
    def __init__(self):
        self.prices = {1519: 40, 1436: 4, 554: 5, 1739: 100, 333: 60}
        self.calls = []

    def __call__(self, url):
        self.calls.append(url)
        if url.endswith("/mapping"):
            return MAPPING
        return {"data": {str(i): {"high": p + 1, "low": p - 1} for i, p in self.prices.items()}}


class Clock:
    def __init__(self):
        self.t = 1_800_000_000.0

    def __call__(self):
        return self.t


def prices(tmp_path, **cfg):
    market, clock = Market(), Clock()
    return Prices(tmp_path, PriceConfig.from_dict(cfg), fetch=market, clock=clock), market, clock


def test_names():
    assert wiki_name("willow_logs", {}) == "Willow logs"
    assert wiki_name("raw_shrimps", {"raw_shrimps": "Raw shrimps"}) == "Raw shrimps"


def test_poll_history_and_average(tmp_path):
    p, market, clock = prices(tmp_path)
    p.poll(["willow_logs", "burnt_fish"])                    # burnt fish isn't tradeable
    assert p.price("willow_logs") == 40 and p.price("burnt_fish") is None
    assert p.average("willow_logs") is None                  # needs 3 days of history
    for _ in range(4):
        clock.t += DAY
        p.poll(["willow_logs"])
    assert p.average("willow_logs") == 40
    again = Prices(tmp_path, PriceConfig(), fetch=market, clock=clock)
    assert again.price("willow_logs") == 40                  # history persisted


def test_profit_per_hour(tmp_path):
    p, _, _ = prices(tmp_path)
    p.poll(["rune_essence", "fire_rune"])
    assert p.profit_per_hour({"inputs": {"rune_essence": 100}, "outputs": {"fire_rune": 100}}) == 100
    assert p.profit_per_hour({"outputs": {"unknown_item": 1}}) is None


def test_sell_and_buy_alerts_with_cooldown(tmp_path):
    p, market, clock = prices(tmp_path, min_value=10_000)
    for _ in range(5):
        p.poll(["willow_logs", "rune_essence"])
        clock.t += DAY
    market.prices[1519] = 60                                 # willows +50%
    market.prices[1436] = 2                                  # essence -50%
    p.poll(["willow_logs", "rune_essence"])
    alerts = p.alerts_for({"willow_logs": 1000}, {"rune_essence": 20_000})
    assert any("Willow logs is up" in a for a in alerts)
    assert any("Rune essence is down" in a for a in alerts)
    assert p.alerts_for({"willow_logs": 1000}, {"rune_essence": 20_000}) == []   # cooldown
    clock.t += 25 * 3600
    assert len(p.alerts_for({"willow_logs": 1000}, {"rune_essence": 20_000})) == 2
    clock.t += 25 * 3600
    assert p.alerts_for({"willow_logs": 10}, {}) == []       # pile too small to bother


def test_ledger_counts_deposits(tmp_path):
    from fakes import config, make_game, put_item, slot_at
    game, fake = make_game(config())
    game.ledger = Ledger(tmp_path / "ledger.json")
    fake.on_click.append(lambda f, pt: [put_item(f.img, j, None) for j in list(f.items())]
                         if slot_at(pt) is not None else None)     # deposit-all on click
    for i in range(1, 6):
        put_item(fake.img, i, "logs")
    game.deposit(game.inv.tags(fake.grab()))
    assert game.ledger.counts == {"logs": 5}
    game.ledger.sold("logs")
    assert Ledger(tmp_path / "ledger.json").counts == {}


def test_upgrade_notices_once(tmp_path):
    sent = []
    up = Upgrades(tmp_path / "u.json", sent.append)
    up.level_up("woodcutting", 40, 41)
    up.level_up("woodcutting", 40, 41)
    assert len(sent) == 1 and "rune axe" in sent[0]
    up.level_up("mining", 5, 22)                              # skipped past two tiers
    assert any("steel pickaxe" in m for m in sent) and any("mithril pickaxe" in m for m in sent)
    assert len(Upgrades(tmp_path / "u.json", sent.append).told) == 4


def test_watch_supplies_shopping_and_alerts(tmp_path):
    p, market, clock = prices(tmp_path, min_value=1)
    data = tmp_path / "acct"
    data.mkdir()
    (data / "progress.json").write_text(json.dumps({"levels": {"runecraft": 20}}))
    watch = PriceWatch(p, load_library(), lambda: data)
    methods = current_methods(load_library(), {"runecraft": 20})
    assert "fire_runes_alkharid" in {m.id for m in methods}
    assert supplies(methods)["rune_essence"] == 1700 * 12
    assert watch.due()
    watch.run()
    assert not watch.due()
    text = watch.shopping()
    assert "Rune essence: 20,400 × 4 = 81,600 gp" in text


def test_chooser_uses_live_profit(tmp_path):
    from skillbot.colors import Registry
    from skillbot.config import Config
    from skillbot.goals import Chooser, Goals, QuestLog
    p, market, clock = prices(tmp_path)
    p.poll(["rune_essence", "fire_rune", "willow_logs", "cowhide", "trout"])
    c = Chooser(Goals(targets={"runecraft": 99}), load_library(), Config.load("config.example.yaml"),
                Registry.load(), QuestLog(None), prices=p)
    fire = load_library()["fire_runes_alkharid"]
    assert c.profit(fire) == 1700 * (5 - 4)
