"""Rooftop (and other) agility courses.

Each obstacle carries an Object Marker in course order (obstacle_1, obstacle_2, ...; long
courses reuse the colors, which is fine as long as two of the same color are never in
view together). The bot clicks the next obstacle and counts it as crossed once the
camera has moved past it and the following obstacle is in view. Marks of grace are
picked up on the way. Falling off puts the first obstacle back in view without the
expected one: the lap restarts from there (after walking back if needed).
"""
import logging
import math

from .game import BotError
from .tasks import Task

log = logging.getLogger("skillbot")

MOVED_PX = 40          # the crossed obstacle must shift this much on screen
MARK_RADIUS_PX = 150


class AgilityTask(Task):
    def __init__(self, game, step):
        super().__init__(game, step)
        self.stats.update(laps=0, marks=0, falls=0)

    def pick_up_marks(self, img) -> bool:
        g, step = self.game, self.step
        if step.loot is None:
            return False
        px, py = g.player
        near = [b for b in g.blobs(img, step.loot)
                if math.dist(b.center, (px, py)) <= MARK_RADIUS_PX]
        if not near:
            return False
        g.click_blob(img, min(near, key=lambda b: math.dist(b.center, (px, py))))
        g.wait(1.5, 2.5)
        self.stats["marks"] += 1
        return True

    def cross(self, i: int) -> bool:
        """Click obstacle ``i`` and wait until it's behind us. False if it didn't work."""
        g, obs = self.game, self.step.obstacles
        img = g.grab()
        blob = g.nearest(img, obs[i])
        if blob is None:
            return False
        before = blob.center
        if not g.click_blob(img, blob):
            return False
        following = obs[(i + 1) % len(obs)]

        def crossed(im):
            now = g.nearest(im, obs[i])
            moved = now is None or math.dist(now.center, before) > MOVED_PX
            return moved and bool(g.blobs(im, following))
        return g.wait_until(crossed, timeout=self.step.idle_timeout, poll=(0.8, 1.2))

    def lap(self) -> None:
        g, obs = self.game, self.step.obstacles
        if not g.blobs(g.grab(), obs[0]):            # not at the start: walk back to it
            if g.nav is not None and self.step.location:
                g.nav.travel(self.step.location, obs[0])
            else:
                g.walk(self.step.walk.get("start"), obs[0])
        i, failures = 0, 0
        while i < len(obs):
            img = g.grab()
            if self.pick_up_marks(img):
                continue
            if self.cross(i):
                i, failures = i + 1, 0
                continue
            img = g.grab()
            if i > 0 and g.blobs(img, obs[0]) and not g.blobs(img, obs[i]):
                log.info("%s: fell off at obstacle %d, starting over", self.step.name, i + 1)
                self.stats["falls"] += 1
                i = 0
                continue
            failures += 1
            if failures >= 3:
                raise BotError(f"{self.step.name}: can't get past obstacle {i + 1}")
        self.stats["laps"] += 1
        self.progressed(1)

    def run_batch(self) -> str:
        for _ in range(self.step.laps_per_batch):
            self.lap()
        self.stats["batches"] += 1
        return "ok"
