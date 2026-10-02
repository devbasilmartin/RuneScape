"""Prices from the OSRS Wiki real-time prices API (your server follows official prices).

The Discord service polls it hourly, keeps 30 days of history per watched item in
data/prices/, and sends alerts:

- sell: something the bot produced (the ledger) is up ≥10% on its 7-day average and the
  pile is worth ≥500k
- buy: a supply the planned methods use is down ≥10% on its 7-day average
- each at most once per item per 24 hours; thresholds in config (prices:)

Item names are the Inventory Tags names (willow_logs → "Willow logs"); add exceptions in
config under prices: names:.
"""
import json
import logging
import time
import urllib.request
from dataclasses import dataclass, field, fields
from pathlib import Path

log = logging.getLogger("skillbot")

API = "https://prices.runescape.wiki/api/v1/osrs"
USER_AGENT = "skillbot (personal OSRS training planner; github.com/devbasilmartin/RuneScape)"
DAY = 86400


def http_json(url: str):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def wiki_name(item: str, overrides: dict) -> str:
    if item in overrides:
        return overrides[item]
    words = item.replace("_", " ")
    return words[:1].upper() + words[1:]


@dataclass
class PriceConfig:
    sell_rise: float = 0.10
    buy_drop: float = 0.10
    min_value: int = 500_000
    cooldown_hours: float = 24
    poll_minutes: float = 60
    names: dict = field(default_factory=dict)       # tag name -> wiki item name

    @classmethod
    def from_dict(cls, d: dict | None) -> "PriceConfig":
        d = dict(d or {})
        unknown = set(d) - {f.name for f in fields(cls)}
        if unknown:
            raise ValueError(f"unknown prices keys: {sorted(unknown)}")
        return cls(**d)


class Prices:
    def __init__(self, folder: Path, cfg: PriceConfig, fetch=http_json, clock=time.time):
        self.folder = Path(folder)
        self.folder.mkdir(parents=True, exist_ok=True)
        self.cfg = cfg
        self.fetch = fetch
        self.clock = clock
        self.history = self._load("history.json", {})     # wiki name -> [[t, price], ...]
        self.alerts = self._load("alerts.json", {})       # "kind:name" -> last alert time
        self.ids = {}
        self.last_poll = float("-inf")

    def _load(self, name, default):
        path = self.folder / name
        return json.loads(path.read_text()) if path.exists() else default

    def _save(self, name, data):
        (self.folder / name).write_text(json.dumps(data))

    # ---- fetching ----------------------------------------------------------------------
    def item_id(self, wiki: str) -> int | None:
        if not self.ids:
            mapping_path = self.folder / "mapping.json"
            if mapping_path.exists() and self.clock() - mapping_path.stat().st_mtime < DAY:
                mapping = json.loads(mapping_path.read_text())
            else:
                mapping = self.fetch(f"{API}/mapping")
                mapping_path.write_text(json.dumps(mapping))
            self.ids = {m["name"].lower(): m["id"] for m in mapping}
        return self.ids.get(wiki.lower())

    def poll(self, items) -> dict:
        """Fetch current prices for ``items`` (tag names) and add them to the history.
        Returns {tag name: price}; untradeable or unknown items are left out."""
        latest = self.fetch(f"{API}/latest")["data"]
        now, out = self.clock(), {}
        for item in items:
            wiki = wiki_name(item, self.cfg.names)
            item_id = self.item_id(wiki)
            entry = latest.get(str(item_id)) if item_id else None
            if not entry:
                continue
            highs = [v for v in (entry.get("high"), entry.get("low")) if v]
            if not highs:
                continue
            price = sum(highs) / len(highs)
            series = [p for p in self.history.get(wiki, []) if p[0] > now - 30 * DAY]
            series.append([now, price])
            self.history[wiki] = series
            out[item] = price
        self._save("history.json", self.history)
        self.last_poll = now
        return out

    # ---- reading -----------------------------------------------------------------------
    def price(self, item: str) -> float | None:
        series = self.history.get(wiki_name(item, self.cfg.names))
        return series[-1][1] if series else None

    def average(self, item: str, days: float = 7) -> float | None:
        """Average over the last ``days``, once there are at least 3 days of history."""
        series = self.history.get(wiki_name(item, self.cfg.names), [])
        now = self.clock()
        recent = [p for t, p in series if t > now - days * DAY]
        if not recent or series[0][0] > now - 3 * DAY:
            return None
        return sum(recent) / len(recent)

    def profit_per_hour(self, trade: dict) -> float | None:
        """Live profit of a method's trade: {inputs: {item: per hour}, outputs: {...}}."""
        total = 0.0
        for sign, key in ((-1, "inputs"), (1, "outputs")):
            for item, per_hour in (trade.get(key) or {}).items():
                p = self.price(item)
                if p is None:
                    return None
                total += sign * p * per_hour
        return total

    # ---- alerts ------------------------------------------------------------------------
    def _cooled(self, key: str) -> bool:
        return self.clock() - self.alerts.get(key, 0) >= self.cfg.cooldown_hours * 3600

    def _mark(self, key: str) -> None:
        self.alerts[key] = self.clock()
        self._save("alerts.json", self.alerts)

    def alerts_for(self, produced: dict, supplies: dict) -> list[str]:
        """``produced``: {item: count the bot has banked}; ``supplies``: {item: amount
        upcoming methods need}. Returns the messages to send."""
        out = []
        for item, count in produced.items():
            price, avg = self.price(item), self.average(item)
            if not (price and avg and count):
                continue
            rise = price / avg - 1
            value = price * count
            if rise >= self.cfg.sell_rise and value >= self.cfg.min_value \
                    and self._cooled(f"sell:{item}"):
                self._mark(f"sell:{item}")
                out.append(f"💰 {wiki_name(item, self.cfg.names)} is up {rise:.0%} on its 7-day "
                           f"average ({price:,.0f} gp): your {count:,} are worth {value:,.0f}. "
                           "Good time to sell.")
        for item, amount in supplies.items():
            price, avg = self.price(item), self.average(item)
            if not (price and avg):
                continue
            drop = 1 - price / avg
            value = price * amount if amount else self.cfg.min_value
            if drop >= self.cfg.buy_drop and value >= self.cfg.min_value \
                    and self._cooled(f"buy:{item}"):
                self._mark(f"buy:{item}")
                need = f" (~{amount:,} for upcoming training)" if amount else ""
                out.append(f"🛒 {wiki_name(item, self.cfg.names)} is down {drop:.0%} on its 7-day "
                           f"average ({price:,.0f} gp){need}. Good time to stock up.")
        return out


class Ledger:
    """What the bot has banked, per item, since you last said you sold it."""

    def __init__(self, path: Path | None):
        self.path = Path(path) if path else None
        self.counts = json.loads(self.path.read_text()) if self.path and self.path.exists() else {}

    def add(self, item: str, count: int) -> None:
        self.counts[item] = self.counts.get(item, 0) + count
        self.save()

    def sold(self, item: str) -> None:
        self.counts.pop(item, None)
        self.save()

    def save(self) -> None:
        if self.path:
            self.path.write_text(json.dumps(self.counts, indent=1))
