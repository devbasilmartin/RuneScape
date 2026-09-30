"""Inventory reading from RuneLite Inventory Tags.

Tag each item you care about with its own color (shift + right-click the item →
Tag). A slot's item is whichever configured tag color is drawn in it. Untagged
items (your net, tinderbox...) are invisible to the bot, so it never drops or
banks them.
"""

from .layout import Layout, Rect
from .vision import color_mask

SLOTS = 28


class Inventory:
    def __init__(self, layout: Layout, items: dict[str, tuple], tools: int = 1,
                 tolerance: int = 25, min_pixels: int = 6):
        self.layout = layout
        self.items = {name: tuple(rgb) for name, rgb in items.items()}
        self.tools = tools
        self.tolerance = tolerance
        self.min_pixels = min_pixels

    def _area(self, i) -> Rect:
        # Tag outlines hug the item sprite and can poke a pixel or two out of the slot.
        s = self.layout.slot(i)
        return Rect(s.x - 2, s.y - 2, s.w + 4, s.h + 4)

    def tag(self, img, i) -> str | None:
        area = self._area(i).crop(img)
        best, best_count = None, self.min_pixels - 1
        for name, rgb in self.items.items():
            count = int(color_mask(area, rgb, self.tolerance).sum())
            if count > best_count:
                best, best_count = name, count
        return best

    def tags(self, img) -> dict[int, str]:
        """Map of slot index -> item name for every tagged slot."""
        found = {}
        for i in range(SLOTS):
            name = self.tag(img, i)
            if name:
                found[i] = name
        return found

    def slots_with(self, img, name: str) -> list[int]:
        return [i for i, n in self.tags(img).items() if n == name]

    def is_full(self, img) -> bool:
        return len(self.tags(img)) >= SLOTS - self.tools

    def any_tag_visible(self, img) -> bool:
        inv = self.layout.inventory
        area = Rect(inv.x - 2, inv.y - 2, inv.w + 4, inv.h + 4).crop(img)
        return any(color_mask(area, rgb, self.tolerance).sum() >= self.min_pixels
                   for rgb in self.items.values())


