"""Learned digit recognition, shared by skill levels and the run energy number.

A number is split into glyphs at empty columns; each glyph's exact pixel shape is looked
up in a book of learned shapes (stored as text). Unknown shapes are learned from values
the caller already knows, or inferred when the number can only have moved a little
since the last read and exactly one candidate fits the screen.
"""
import json
from pathlib import Path

import numpy as np


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


class GlyphBook:
    def __init__(self, glyphs: dict[str, str] | None = None, path: Path | None = None):
        self.glyphs = dict(glyphs or {})   # glyph_key -> digit
        self.path = path

    @classmethod
    def load(cls, path: Path) -> "GlyphBook":
        return cls(json.loads(path.read_text()) if path.exists() else {}, path)

    def save(self) -> None:
        if self.path:
            self.path.write_text(json.dumps(self.glyphs, indent=1, sort_keys=True))

    def known_digits(self) -> str:
        return "".join(sorted(set(self.glyphs.values())))

    def complete(self) -> bool:
        return len(self.known_digits()) == 10

    def read(self, glyphs) -> int | None:
        digits = [self.glyphs.get(glyph_key(g)) for g in glyphs]
        if not digits or None in digits:
            return None
        return int("".join(digits))

    def learn(self, glyphs, value: int) -> bool:
        text = str(value)
        if len(glyphs) != len(text):
            return False
        for g, d in zip(glyphs, text):
            self.glyphs[glyph_key(g)] = d
        return True

    def read_among(self, glyphs, candidates) -> int | None:
        """Read the number, learning an unseen glyph if exactly one candidate fits."""
        value = self.read(glyphs)
        if value is not None:
            return value
        keys = [glyph_key(g) for g in glyphs]
        if not keys:
            return None
        matches = []
        for cand in candidates:
            text = str(cand)
            if len(text) != len(keys):
                continue
            if not all(self.glyphs.get(k) in (None, d) for k, d in zip(keys, text)):
                continue
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
