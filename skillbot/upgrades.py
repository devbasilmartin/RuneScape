"""Tool and weapon upgrade notices: when a level unlocks a better tier, say so once.
You buy it (GE trading stays manual) and put it in the gear tab; the bot then uses it."""
import json
from pathlib import Path

TIERS = ((1, "bronze/iron"), (6, "steel"), (11, "black"), (21, "mithril"), (31, "adamant"),
         (41, "rune"), (61, "dragon"))
LADDERS = {
    "woodcutting": [(lvl, f"{tier} axe") for lvl, tier in TIERS],
    "mining": [(lvl, f"{tier} pickaxe") for lvl, tier in TIERS],
    "attack": [(1, "bronze/iron scimitar"), (5, "steel scimitar"), (10, "black scimitar"),
               (20, "mithril scimitar"), (30, "adamant scimitar"), (40, "rune scimitar"),
               (60, "dragon scimitar (needs Monkey Madness I)")],
}


class Upgrades:
    def __init__(self, path: Path | None, notify):
        self.path = Path(path) if path else None
        self.notify = notify
        self.told = set(json.loads(self.path.read_text())) if self.path and self.path.exists() \
            else set()

    def level_up(self, skill: str, old: int, new: int) -> None:
        for level, item in LADDERS.get(skill, []):
            key = f"{skill}:{level}"
            if old < level <= new and level > 1 and key not in self.told:
                self.told.add(key)
                self.notify(f"⬆️ {skill.title()} {new}: {item} unlocked. Buy one and put it in the "
                            "gear tab when you can.")
        if self.path:
            self.path.write_text(json.dumps(sorted(self.told)))
