"""The Discord service's hourly price job: poll prices for what matters right now, send
buy/sell alerts, and answer /shopping."""
import json
import logging
from pathlib import Path

from .prices import Ledger, Prices, wiki_name

log = logging.getLogger("skillbot")
SHOPPING_HOURS = 12


def current_methods(library: dict, levels: dict) -> list:
    """Library methods usable at the current levels (by level range only)."""
    out = []
    for m in library.values():
        if any(m.levels[0] <= levels.get(s, 1) < m.levels[1] for s in m.skills):
            out.append(m)
    return out


def supplies(methods) -> dict:
    """{item: amount for SHOPPING_HOURS of training} (0 when the method has no trade)."""
    need = {}
    for m in methods:
        per_hour = dict((m.trade or {}).get("inputs") or {})
        for w in m.step.get("withdraw") or []:
            item = w.get("item") if isinstance(w, dict) else None
            if item:
                per_hour.setdefault(item, 0)
        for item, rate in per_hour.items():
            need[item] = need.get(item, 0) + int(rate * SHOPPING_HOURS)
    return need


class PriceWatch:
    def __init__(self, prices: Prices, library: dict, status_dir_fn):
        self.prices = prices
        self.library = library
        self.status_dir = status_dir_fn      # the active account's data folder

    def _levels(self) -> dict:
        path = Path(self.status_dir()) / "progress.json"
        return json.loads(path.read_text()).get("levels", {}) if path.exists() else {}

    def ledger(self) -> Ledger:
        return Ledger(Path(self.status_dir()) / "ledger.json")

    def due(self) -> bool:
        return self.prices.clock() - self.prices.last_poll >= self.prices.cfg.poll_minutes * 60

    def run(self) -> list[str]:
        methods = current_methods(self.library, self._levels())
        need = supplies(methods)
        produced = self.ledger().counts
        watched = set(need) | set(produced)
        for m in methods:
            watched |= set((m.trade or {}).get("outputs") or {})
        if not watched:
            self.prices.last_poll = self.prices.clock()
            return []
        self.prices.poll(sorted(watched))
        return self.prices.alerts_for(produced, need)

    def shopping(self) -> str:
        need = supplies(current_methods(self.library, self._levels()))
        if not need:
            return "Nothing to buy for the methods at your current levels."
        lines, total = [f"**Shopping list** (about {SHOPPING_HOURS}h of training):"], 0.0
        for item, amount in sorted(need.items()):
            price = self.prices.price(item)
            name = wiki_name(item, self.prices.cfg.names)
            if price and amount:
                total += price * amount
                lines.append(f"• {name}: {amount:,} × {price:,.0f} = {price * amount:,.0f} gp")
            else:
                lines.append(f"• {name}" + (f": {price:,.0f} gp each" if price else ""))
        if total:
            lines.append(f"Total ≈ {total:,.0f} gp")
        return "\n".join(lines)
