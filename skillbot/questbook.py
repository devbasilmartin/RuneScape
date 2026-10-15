"""The quest list (library/quests/f2p.yaml): what each quest needs, whether this account can
start it, and the quest tab, read to see which quests are finished.

The quest tab draws each quest's name in red (not started), yellow (started) or green
(finished). A name's pixel shape is the same in every color, so it's taught once, like a
menu word: hover the name with the quest tab open and run `teach-quest NAME`
(data/quest_words.json). Reading the tab then finds each taught name among the visible
lines and reports its color. Names scrolled out of view read as unknown.
"""
import logging
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import yaml

from .menu import MenuBook, signature

log = logging.getLogger("skillbot")

QUESTS_FILE = Path(__file__).resolve().parent.parent / "library" / "quests" / "f2p.yaml"
DONE, STARTED, NOT_STARTED = "finished", "started", "not started"
MIN_PIXELS = 8           # a line with fewer text pixels is noise


@dataclass
class Quest:
    name: str
    start: str | None = None
    levels: dict = field(default_factory=dict)
    items: tuple = ()
    needs_you: tuple = ()
    rewards: str = ""
    members: bool = False


def load_quests(path: Path = QUESTS_FILE) -> dict[str, Quest]:
    raw = yaml.safe_load(Path(path).read_text()) or {}
    quests = {}
    for name, d in raw.items():
        d = dict(d or {})
        unknown = set(d) - {"start", "levels", "items", "needs_you", "rewards", "members"}
        if unknown:
            raise ValueError(f"quest {name!r}: unknown keys {sorted(unknown)}")
        quests[name] = Quest(name, d.get("start"), dict(d.get("levels") or {}),
                             tuple(d.get("items") or ()), tuple(d.get("needs_you") or ()),
                             str(d.get("rewards", "")), bool(d.get("members", False)))
    return quests


def find(quests: dict, name: str) -> Quest | None:
    return next((q for n, q in quests.items() if n.lower() == (name or "").lower()), None)


def problems(quest: Quest, levels: dict, account: str, ready) -> list[str]:
    """Why the bot can't start this quest now ([] when it can). ``ready``: a QuestLog of
    quests whose items you've marked as brought."""
    out = []
    if account == "f2p" and quest.members:
        out.append("members quest")
    for skill, need in quest.levels.items():
        if levels.get(skill, 1) < need:
            out.append(f"needs {skill} {need} (you have {levels.get(skill, 1)})")
    if quest.items and not ready.has(quest.name):
        out.append(f"bring {', '.join(quest.items)}, then `quest-ready \"{quest.name}\"`")
    return out


# ---- the quest tab ---------------------------------------------------------------------

def _state(px: np.ndarray) -> np.ndarray:
    """Per pixel: 0 none, 1 red, 2 yellow, 3 green (the quest tab's three text colors)."""
    r, g, b = (px[..., i].astype(int) for i in range(3))
    out = np.zeros(px.shape[:2], np.uint8)
    out[(r >= 180) & (g <= 70) & (b <= 70)] = 1
    out[(r >= 180) & (g >= 180) & (b <= 70)] = 2
    out[(g >= 150) & (r <= 90) & (b <= 90)] = 3
    return out


def tab_lines(img: np.ndarray, area) -> list:
    """The quest tab's text lines, top to bottom: (middle y, signature, state)."""
    state = _state(area.crop(img))
    rows = np.flatnonzero((state > 0).any(axis=1))
    lines, start = [], None
    for i, y in enumerate(rows):
        if start is None:
            start = y
        if i + 1 == len(rows) or rows[i + 1] > y + 2:
            band = state[start:y + 1]
            if (band > 0).sum() >= MIN_PIXELS:
                counts = np.bincount(band[band > 0], minlength=4)
                name = {1: NOT_STARTED, 2: STARTED, 3: DONE}[int(counts[1:].argmax()) + 1]
                lines.append((area.y + (start + y) // 2, signature(band > 0), name))
            start = None
    return lines


def tab_states(img: np.ndarray, area, book: MenuBook) -> dict[str, str]:
    """Each taught quest visible in the tab: finished, started or not started."""
    lines = tab_lines(img, area)
    sigs = [s for _, s, _ in lines]
    out = {}
    for name in book.words:
        row = book.find(name, sigs)
        if row is not None:
            out[name] = lines[row - 1][2]
    return out


def teach(img: np.ndarray, area, book: MenuBook, name: str, mouse_y: int) -> str:
    """Remember the line under the mouse as ``name``; returns its state."""
    lines = tab_lines(img, area)
    if not lines:
        raise ValueError("no quest names found: open the quest tab first")
    y, sig, state = min(lines, key=lambda line: abs(line[0] - mouse_y))
    if abs(y - mouse_y) > 10:
        raise ValueError("hover the quest's name in the quest tab")
    book.learn(name, sig)
    book.save()
    return state


def read_tab(game, book: MenuBook) -> dict[str, str]:
    """Open the quest tab, read it, and go back to the inventory."""
    game.open_tab("quest")
    states = tab_states(game.grab(), game.layout.quest_list, book)
    game.open_tab("inventory")
    return states
