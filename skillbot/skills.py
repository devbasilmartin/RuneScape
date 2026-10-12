"""Reading levels from the skills tab.

Digit shapes are learned, not shipped: ``learn-digits`` pairs what is on screen with
levels you type in, and while the bot runs it learns any new digit the first time a
level ticks over to it. That relies on the level going up by exactly one between
reads, so until all ten digits are known the planner re-reads the level after every
item gained. Shapes are stored as text in data/digits.json.
"""
from pathlib import Path

from .digits import GlyphBook, segment
from .layout import Layout
from .vision import color_mask

# Order of the skills tab, left to right, top to bottom.
def combat_level(levels: dict) -> int:
    """The game's combat level (unknown skills count as 1, hitpoints as 10)."""
    g = lambda s: levels.get(s, 10 if s == "hitpoints" else 1)  # noqa: E731
    base = 0.25 * (g("defence") + g("hitpoints") + g("prayer") // 2)
    best = max(0.325 * (g("attack") + g("strength")), 0.325 * (g("ranged") * 3 // 2),
               0.325 * (g("magic") * 3 // 2))
    return int(base + best)


SKILLS = ("attack", "hitpoints", "mining", "strength", "agility", "smithing", "defence",
          "herblore", "fishing", "ranged", "thieving", "cooking", "prayer", "crafting",
          "firemaking", "magic", "fletching", "woodcutting", "runecraft", "slayer", "farming",
          "construction", "hunter")

LEVEL_COLOR = (255, 255, 0)


class SkillReader:
    def __init__(self, layout: Layout, book: GlyphBook | None = None, tolerance: int = 60):
        self.layout = layout
        self.book = book or GlyphBook()
        self.tolerance = tolerance

    @classmethod
    def load(cls, layout: Layout, data_dir: Path) -> "SkillReader":
        return cls(layout, GlyphBook.load(data_dir / "digits.json"))

    def save(self) -> None:
        self.book.save()

    def known_digits(self) -> str:
        return self.book.known_digits()

    def complete(self) -> bool:
        return self.book.complete()

    def _glyphs(self, img, skill: str):
        box = self.layout.skill_level(SKILLS.index(skill)).crop(img)
        return segment(color_mask(box, LEVEL_COLOR, self.tolerance))

    def read(self, img, skill: str) -> int | None:
        return self.book.read(self._glyphs(img, skill))

    def learn(self, img, skill: str, level: int) -> bool:
        """Teach the glyphs shown for ``skill`` given its true level."""
        return self.book.learn(self._glyphs(img, skill), level)

    def read_expecting(self, img, skill: str, previous: int, max_jump: int = 1) -> int | None:
        """Read a level: exactly, when every digit's shape is known (whatever the level
        was); otherwise only within ``previous .. previous + max_jump``, learning an
        unseen digit if exactly one value in that range fits the screen."""
        glyphs = self._glyphs(img, skill)
        exact = self.book.read(glyphs)
        if exact is not None:
            return exact
        return self.book.read_among(glyphs, range(previous, min(previous + max_jump, 99) + 1))
