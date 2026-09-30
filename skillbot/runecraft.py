"""Runecrafting: bank -> ruins -> altar -> portal -> bank.

Runes: ``items: [rune_essence]``, enter the ruins by using a tagged talisman on them
(``enter_with``, also listed in ``keep`` so it isn't banked) or by wearing the tiara.
Tiaras: ``items: [tiara]`` with ``use_item: tiara`` and the talismans in the inventory;
each use of a tiara on the altar binds it.

The task works out where it is from what's on screen, so it can resume from anywhere
in the cycle after an error or a re-login.
"""
import logging

from .game import BotError
from .tasks import Task

log = logging.getLogger("skillbot")


class RunecraftTask(Task):
    def inside(self, img) -> bool:
        g = self.game
        return bool(g.blobs(img, self.step.target) or g.blobs(img, self.step.portal))

    def run_batch(self) -> str:
        g, step = self.game, self.step
        crafted = False
        for _ in range(12):
            img = g.grab()
            inside, has_inputs = self.inside(img), self.has_items(img)
            if inside and has_inputs:
                self.craft()
                crafted = True
            elif inside:
                self.leave()
                if crafted:
                    self.stats["batches"] += 1
                    return "ok"
            elif has_inputs:
                self.enter()
            else:
                g.bank(step.walk.get("bank"), step.withdraw, keep=step.keep)
                if not self.has_items(g.grab()):
                    log.info("%s: out of essence", step.name)
                    return "exhausted"
        raise BotError(f"{step.name}: could not complete a runecrafting trip")

    def enter(self) -> None:
        g, step = self.game, self.step
        g.walk(step.walk.get("target"), step.ruins)
        img = g.grab()
        if step.enter_with:
            slots = self.tagged(img, [step.enter_with])
            if not slots:
                raise BotError(f"{step.name}: no {step.enter_with} to enter the ruins with")
            g.controls.click_rect(g.layout.slot(min(slots)))
            g.wait(0.3, 0.6)
        if not g.click_nearest(img, step.ruins):
            raise BotError(f"{step.name}: ruins not visible")
        if not g.wait_until(self.inside, timeout=g.cfg.walk_timeout):
            raise BotError(f"{step.name}: did not get into the altar")
        g.wait(0.8, 1.2)     # the area finishes loading

    def craft(self) -> None:
        g, step = self.game, self.step
        for _attempt in range(30):     # tiaras bind one per use
            img = g.grab()
            remaining = len(self.tagged(img, step.items))
            if not remaining:
                return
            if step.use_item:
                slots = self.tagged(img, [step.use_item])
                if not slots:
                    raise BotError(f"{step.name}: no {step.use_item} left to use on the altar")
                g.controls.click_rect(g.layout.slot(min(slots)))
                g.wait(0.3, 0.6)
            if not g.click_nearest(img, step.target):
                raise BotError(f"{step.name}: altar not visible")
            if g.wait_until(lambda im: len(self.tagged(im, step.items)) < remaining,
                            timeout=step.idle_timeout):
                self.progressed(remaining - len(self.tagged(g.grab(), step.items)))
                g.wait(0.4, 0.8)
        raise BotError(f"{step.name}: the altar is not using up the inputs")

    def leave(self) -> None:
        g, step = self.game, self.step
        g.walk(None, step.portal)
        if not g.click_nearest(g.grab(), step.portal):
            raise BotError(f"{step.name}: portal not visible")
        if not g.wait_until(lambda im: not self.inside(im), timeout=g.cfg.walk_timeout):
            raise BotError(f"{step.name}: did not leave through the portal")
        g.wait(0.8, 1.2)
