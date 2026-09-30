"""Keeps run switched on, for every skill.

The run orb's icon changes color when run is toggled, so ``calibrate-run`` records a
small color sample of it in both states (data/run_orb.json) and the current state is
whichever sample the screen is closer to. When energy hits 0 the game turns run off;
clicking the orb then does nothing until some energy is back, so after a failed or
forced switch-off the bot waits ``run_retry_seconds`` before trying again.
"""
import json
import logging
from pathlib import Path

import numpy as np

log = logging.getLogger("skillbot")

CHECK_EVERY = 5.0     # seconds between looks at the orb


def orb_sample(img, point) -> list[int]:
    x, y = point
    patch = img[y - 2:y + 3, x - 2:x + 3].reshape(-1, img.shape[-1])[:, :3]
    return [int(v) for v in patch.mean(axis=0)]


class RunManager:
    def __init__(self, game, on_sample, off_sample, retry: float = 60.0):
        self.game = game
        self.on = np.array(on_sample)
        self.off = np.array(off_sample)
        self.retry = retry
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
        return cls(game, samples["on"], samples["off"], game.cfg.run_retry_seconds)

    def state(self, img) -> str | None:
        """"on", "off", or None when the orb looks like neither (e.g. logged out)."""
        now = np.array(orb_sample(img, self.game.layout.run_orb))
        d_on = np.abs(now - self.on).max()
        d_off = np.abs(now - self.off).max()
        if min(d_on, d_off) > 40:
            return None
        return "on" if d_on < d_off else "off"

    def maintain(self) -> None:
        g = self.game
        t = g.now()
        if t - self.last_check < CHECK_EVERY:
            return
        self.last_check = t
        state = self.state(g.grab())
        if state == "off" and self.last_state == "on":
            log.info("out of run energy; walking for a while")
            self.stats["ran_out"] += 1
            self.next_try = t + self.retry
        self.last_state = state or self.last_state
        if state != "off" or t < self.next_try:
            return
        g.controls.click(g.layout.run_orb)
        g.wait(0.3, 0.5)
        if self.state(g.grab()) == "on":
            log.info("run on")
            self.stats["enabled"] += 1
            self.last_state = "on"
        else:
            self.next_try = t + self.retry     # not enough energy yet
            self.last_state = "off"
