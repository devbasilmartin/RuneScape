"""Inventory reading by comparing slots to a baseline screenshot.

The baseline is captured with only your tools (net, tinderbox...) in the inventory.
A slot counts as "new" when it differs from the baseline, so tools are ignored
automatically. Item templates (optional) identify what a slot holds, which the
cooking step needs to tell raw fish from cooked.
"""
from pathlib import Path

import numpy as np

from .layout import Layout
from .vision import load_png, match_score

SLOTS = 28


class Inventory:
    def __init__(self, layout: Layout, baseline: np.ndarray, tool_slots=(0,),
                 bank_baseline: np.ndarray | None = None,
                 templates: dict[str, np.ndarray] | None = None,
                 diff_threshold: float = 4.0, match_threshold: float = 0.85):
        self.layout = layout
        self.baseline = baseline
        self.bank_baseline = bank_baseline
        self.tool_slots = set(tool_slots)
        self.templates = templates or {}
        self.diff_threshold = diff_threshold
        self.match_threshold = match_threshold

    @classmethod
    def load(cls, layout: Layout, data_dir: Path, **kw) -> "Inventory":
        baseline = load_png(data_dir / "inv_baseline.png")
        bank = data_dir / "inv_baseline_bank.png"
        templates = {p.stem: load_png(p) for p in sorted((data_dir / "items").glob("*.png"))}
        return cls(layout, baseline, bank_baseline=load_png(bank) if bank.exists() else None,
                   templates=templates, **kw)

    def _slot_img(self, img, i):
        return self.layout.slot(i).crop(img)

    def _baseline_slot(self, i, in_bank=False):
        base = self.bank_baseline if in_bank and self.bank_baseline is not None else self.baseline
        inv, s = self.layout.inventory, self.layout.slot(i)
        return base[s.y - inv.y:s.y - inv.y + s.h, s.x - inv.x:s.x - inv.x + s.w]

    def is_new(self, img, i, in_bank=False) -> bool:
        """True if slot ``i`` holds something that is not one of your tools."""
        if i in self.tool_slots:
            return False
        a = self._slot_img(img, i).astype(np.int16)
        b = self._baseline_slot(i, in_bank).astype(np.int16)
        return float(np.abs(a - b).mean()) > self.diff_threshold

    def new_slots(self, img, in_bank=False) -> list[int]:
        return [i for i in range(SLOTS) if self.is_new(img, i, in_bank)]

    def is_full(self, img) -> bool:
        return len(self.new_slots(img)) >= SLOTS - len(self.tool_slots)

    def identify(self, img, i) -> str | None:
        slot = self._slot_img(img, i)
        best, best_score = None, self.match_threshold
        for name, tmpl in self.templates.items():
            score, _ = match_score(slot, tmpl)
            if score >= best_score:
                best, best_score = name, score
        return best

    def slots_with(self, img, name: str) -> list[int]:
        return [i for i in self.new_slots(img) if self.identify(img, i) == name]
