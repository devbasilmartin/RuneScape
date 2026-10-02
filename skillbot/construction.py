"""Construction in your house, in build mode: build on the hotspot, remove, repeat.

Build: left-click the hotspot (an Object Marker in `build_spot`, or a fixed `hotspot`
point), then the furniture's number key in the build menu. Remove: right-click it, pick
the "Remove" row, confirm with 1. Each build uses tagged inputs (planks, bagged plants).
When they run out the bot travels to `bank_location`, restocks, and travels back to the
step's `location` (your house, e.g. via a house teleport hub).
"""
import logging

from .game import BotError
from .tasks import Task

log = logging.getLogger("skillbot")


class ConstructionTask(Task):
    def spot(self, img):
        """Where the hotspot / built furniture is on screen."""
        if self.step.hotspot is not None:
            return self.step.hotspot
        blob = self.game.nearest(img, self.step.target)
        return blob.center if blob else None

    def count(self, img) -> int:
        return len(self.tagged(img, self.step.items))

    def restock(self) -> bool:
        g, step = self.game, self.step
        if not step.bank_location or g.nav is None:
            return False
        g.nav.travel(step.bank_location, g.cfg.bank_color)
        if not self.bank_and_restock() or not self.has_items(g.grab()):
            return False
        if step.location:
            g.nav.travel(step.location, step.target)
        return True

    def build(self) -> bool:
        g, step = self.game, self.step
        img = g.grab()
        before = self.count(img)
        point = self.spot(img)
        if point is None:
            raise BotError(f"{step.name}: build spot not visible")
        g.controls.click(point)
        g.wait(1.0, 1.4)                         # the build menu opens
        g.controls.press(step.build_key)
        built = g.wait_until(lambda im: self.count(im) < before, timeout=step.idle_timeout)
        if built:
            self.progressed(1)
        return built

    def remove(self) -> None:
        g, step = self.game, self.step
        point = self.spot(g.grab())
        if point is None:
            raise BotError(f"{step.name}: built furniture not visible")
        g.controls.click(point, button="right")
        g.wait(0.4, 0.6)
        lay = g.layout
        g.controls.click((point[0], point[1] + lay.menu_header
                          + lay.menu_row * (step.remove_option - 1) + lay.menu_row // 2))
        g.wait(0.8, 1.2)
        g.controls.press("1")                    # "Yes, remove it"
        g.wait(1.0, 1.4)

    def run_batch(self) -> str:
        g, step = self.game, self.step
        if not self.has_items(g.grab()) and not self.restock():
            log.info("%s: out of materials", step.name)
            return "exhausted"
        failures = 0
        for _ in range(step.builds_per_batch):
            if not self.has_items(g.grab()):
                break
            if self.build():
                failures = 0
                self.remove()
            else:
                failures += 1
                g.close_interfaces()
                if failures >= 3:
                    raise BotError(f"{step.name}: building doesn't use any materials "
                                   "(build mode on? right build_key?)")
        self.stats["batches"] += 1
        return "ok"
