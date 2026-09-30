"""Fixed-mode client geometry, in pixels relative to the top-left of the game canvas.

Fixed mode is always 765x503, so every UI element sits at a known offset from the
canvas origin. Values can be overridden in config.yaml (``layout:`` section);
use ``python -m fishbot debug`` to check them against your client.
"""
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Rect:
    x: int
    y: int
    w: int
    h: int

    @property
    def center(self) -> tuple[int, int]:
        return self.x + self.w // 2, self.y + self.h // 2

    def crop(self, img):
        return img[self.y:self.y + self.h, self.x:self.x + self.w]


CANVAS_W, CANVAS_H = 765, 503


@dataclass
class Layout:
    viewport: Rect = field(default_factory=lambda: Rect(4, 4, 512, 334))
    inv_origin: tuple[int, int] = (563, 213)   # top-left of slot 0
    slot_step: tuple[int, int] = (42, 36)      # distance between slot origins
    slot_size: tuple[int, int] = (32, 32)
    compass: tuple[int, int] = (561, 20)

    def slot(self, i: int) -> Rect:
        col, row = i % 4, i // 4
        return Rect(self.inv_origin[0] + col * self.slot_step[0],
                    self.inv_origin[1] + row * self.slot_step[1],
                    *self.slot_size)

    @property
    def inventory(self) -> Rect:
        last = self.slot(27)
        return Rect(self.inv_origin[0], self.inv_origin[1],
                    last.x + last.w - self.inv_origin[0], last.y + last.h - self.inv_origin[1])

    @classmethod
    def from_dict(cls, d: dict | None) -> "Layout":
        d = dict(d or {})
        if "viewport" in d:
            d["viewport"] = Rect(*d["viewport"])
        for k in ("inv_origin", "slot_step", "slot_size", "compass"):
            if k in d:
                d[k] = tuple(d[k])
        return cls(**d)
