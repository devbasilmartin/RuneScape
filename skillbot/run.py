"""Keeps run switched on, for every skill.

The run orb's icon changes color when run is toggled, so ``calibrate-run`` records a
small color sample of it in both states (data/run_orb.json) and the current state is
whichever sample the screen is closer to.

When energy runs out the game turns run off. The bot switches it back on once the
energy number next to the orb reaches ``run_min_energy``. The number is read with
learned digit shapes (data/energy_digits.json, taught by ``learn-energy`` and then
learned as the number changes). If it can't be read, the bot falls back to waiting
``run_retry_seconds`` before trying again, so it never spams the orb.
"""
import json
import logging
from pathlib import Path

import numpy as np

from .digits import GlyphBook, segment
from .layout import Rect

log = logging.getLogger("skillbot")

CHECK_EVERY = 5.0     # seconds between looks at the orb


def orb_sample(img, point) -> list[int]:
    x, y = point
    patch = img[y - 2:y + 3, x - 2:x + 3].reshape(-1, img.shape[-1])[:, :3]
    return [int(v) for v in patch.mean(axis=0)]


def energy_mask(img) -> np.ndarray:
    """The energy number is drawn green (full) through yellow to red (empty): bright
    red and/or green with almost no blue. The orb and its shadow are dark."""
    rgb = img[..., :3].astype(np.int16)
    return (rgb[..., 2] < 80) & (rgb[..., :2].max(axis=-1) > 150)


class EnergyReader:
    WINDOW = 8        # energy can move this much between two looks at the orb (5s)

    def __init__(self, box: Rect, book: GlyphBook | None = None):
        self.box = box
        self.book = book or GlyphBook()

    def glyphs(self, img):
        return segment(energy_mask(self.box.crop(img)))

    def read(self, img, previous: int | None = None, window: int = WINDOW) -> int | None:
        """Read the energy. Given the ``previous`` reading, an unknown digit is learned
        when only one value within ``window`` of it fits the screen; watching the number
        change one point at a time (window 1) makes that unambiguous."""
        glyphs = self.glyphs(img)
        if previous is None:
            value = self.book.read(glyphs)
        else:
            lo, hi = max(0, previous - window), min(100, previous + window)
            value = self.book.read_among(glyphs, range(lo, hi + 1))
        return value if value is not None and 0 <= value <= 100 else None

    def learn(self, img, value: int) -> bool:
        return self.book.learn(self.glyphs(img), value)


class RunManager:
    def __init__(self, game, on_sample, off_sample, retry: float = 60.0,
                 energy: EnergyReader | None = None, min_energy: int = 50):
        self.game = game
        self.on = np.array(on_sample)
        self.off = np.array(off_sample)
        self.retry = retry
        self.reader = energy
        self.min_energy = min_energy
        self.energy = None
        self.last_check = -CHECK_EVERY
        self.last_state = None
        self.next_try = 0.0
        self.stats = {"enabled": 0, "ran_out": 0}

    @classmethod
    def load(cls, game, data_dir: Path) -> "RunManager":
        path = data_dir / "run_orb.json"
        if not path.exists():
            raise SystemExit("run: always needs `python -m skillbot calibrate-run` first "
                             "(or set run: off in config.yaml).")
        samples = json.loads(path.read_text())
        reader = EnergyReader(game.layout.run_energy_box,
                              GlyphBook.load(data_dir / "energy_digits.json"))
        if not reader.book.glyphs:
            log.warning("run energy digits not learned (`python -m skillbot learn-energy`); "
                        "using the %ds retry timer instead", game.cfg.run_retry_seconds)
        return cls(game, samples["on"], samples["off"], game.cfg.run_retry_seconds,
                   reader, game.cfg.run_min_energy)

    def state(self, img) -> str | None:
        """"on", "off", or None when the orb looks like neither (e.g. logged out)."""
        now = np.array(orb_sample(img, self.game.layout.run_orb))
        d_on = np.abs(now - self.on).max()
        d_off = np.abs(now - self.off).max()
        if min(d_on, d_off) > 40:
            return None
        return "on" if d_on < d_off else "off"

    def read_energy(self, img) -> int | None:
        if self.reader is None:
            return None
        value = self.reader.read(img, self.energy)
        self.energy = value
        return value

    def maintain(self) -> None:
        g = self.game
        t = g.now()
        if t - self.last_check < CHECK_EVERY:
            return
        self.last_check = t
        img = g.grab()
        state = self.state(img)
        energy = self.read_energy(img)
        if state == "off" and self.last_state == "on":
            log.info("out of run energy; walking until %d%%", self.min_energy)
            self.stats["ran_out"] += 1
            self.next_try = t + self.retry
        self.last_state = state or self.last_state
        if state != "off":
            return
        if energy is not None:
            if energy < self.min_energy:
                return
        elif t < self.next_try:
            return
        g.controls.click(g.layout.run_orb)
        g.wait(0.3, 0.5)
        if self.state(g.grab()) == "on":
            log.info("run on (%s%% energy)", "?" if energy is None else energy)
            self.stats["enabled"] += 1
            self.last_state = "on"
        else:
            self.next_try = t + self.retry     # not enough energy yet
            self.last_state = "off"
