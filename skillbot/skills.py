"""Reading levels from the skills tab.

Digits are recognised by their exact pixel shape. Shapes are learned, not shipped:
``learn-digits`` pairs what is on screen with levels you type in, and while the bot
runs it learns any new digit the first time a level ticks over to it. That relies on
the level going up by exactly one between reads, so until all ten digits are known
the planner re-reads the level after every item gained. Glyphs are stored as text
in data/digits.json.
"""
import json
from pathlib import Path

import numpy as np

from .layout import Layout
from .vision import color_mask

# Order of the skills tab, left to right, top to bottom.
SKILLS = ("attack", "hitpoints", "mining", "strength", "agility", "smithing", "defence",
          "herblore", "fishing", "ranged", "thieving", "cooking", "prayer", "crafting",
          "firemaking", "magic", "fletching", "woodcutting", "runecraft", "slayer", "farming",
          "construction", "hunter")

LEVEL_COLOR = (255, 255, 0)


def glyph_key(glyph: np.ndarray) -> str:
    return "/".join("".join("1" if v else "0" for v in row) for row in glyph)


def segment(mask: np.ndarray) -> list[np.ndarray]:
    """Split a text mask into glyphs at empty columns, each trimmed to its own box."""
    cols = mask.any(axis=0)
    glyphs, start = [], None
    for x, filled in enumerate(list(cols) + [False]):
        if filled and start is None:
            start = x
        elif not filled and start is not None:
            g = mask[:, start:x]
            rows = np.flatnonzero(g.any(axis=1))
            glyphs.append(g[rows[0]:rows[-1] + 1])
            start = None
    return glyphs


class SkillReader:
    def __init__(self, layout: Layout, glyphs: dict[str, str] | None = None,
                 path: Path | None = None, tolerance: int = 60):
        self.layout = layout
        self.glyphs = dict(glyphs or {})   # glyph_key -> digit
        self.path = path
        self.tolerance = tolerance

    @classmethod
    def load(cls, layout: Layout, data_dir: Path) -> "SkillReader":
        path = data_dir / "digits.json"
        glyphs = json.loads(path.read_text()) if path.exists() else {}
        return cls(layout, glyphs, path)

    def save(self) -> None:
        if self.path:
            self.path.write_text(json.dumps(self.glyphs, indent=1, sort_keys=True))

    def _glyphs(self, img, skill: str) -> list[np.ndarray]:
        box = self.layout.skill_level(SKILLS.index(skill)).crop(img)
        return segment(color_mask(box, LEVEL_COLOR, self.tolerance))

    def known_digits(self) -> str:
        return "".join(sorted(set(self.glyphs.values())))

    def complete(self) -> bool:
        return len(self.known_digits()) == 10

    def read(self, img, skill: str) -> int | None:
        digits = [self.glyphs.get(glyph_key(g)) for g in self._glyphs(img, skill)]
        if not digits or None in digits:
            return None
        return int("".join(digits))

    def learn(self, img, skill: str, level: int) -> bool:
        """Teach the glyphs shown for ``skill`` given its true level."""
        glyphs = self._glyphs(img, skill)
        text = str(level)
        if len(glyphs) != len(text):
            return False
        for g, d in zip(glyphs, text):
            self.glyphs[glyph_key(g)] = d
        return True

    def read_expecting(self, img, skill: str, previous: int, max_jump: int = 1) -> int | None:
        """Read a level known to be in ``previous .. previous + max_jump``, learning an
        unseen digit if exactly one value in that range fits the screen."""
        level = self.read(img, skill)
        if level is not None:
            return level
        keys = [glyph_key(g) for g in self._glyphs(img, skill)]
        if not keys:
            return None
        matches = []
        for cand in range(previous, min(previous + max_jump, 99) + 1):
            text = str(cand)
            if len(text) == len(keys) and all(
                    self.glyphs.get(k) in (None, d) for k, d in zip(keys, text)):
                # an unknown glyph must not be a digit we already know by another shape
                unknown = {d for k, d in zip(keys, text) if k not in self.glyphs}
                if not unknown & set(self.glyphs.values()):
                    matches.append(cand)
        if len(matches) != 1:
            return None
        for k, d in zip(keys, str(matches[0])):
            self.glyphs.setdefault(k, d)
        self.save()
        return matches[0]
