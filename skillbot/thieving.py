"""Thieving: pickpocketing NPCs (knights, men) or stealing from stalls.

Click the highlighted NPC or stall (turn on Menu Entry Swapper's pickpocket swap so
left-click pickpockets). A stun shows as an HP drop on the Status Bars health bar: the
bot then waits it out. Coin pouches (tagged) are opened every `open_every` attempts.
Stall loot (the step's `items`) is banked or dropped when the inventory fills.
"""
import logging

from .combat import CombatTask
from .game import BotError

log = logging.getLogger("skillbot")

STUN_SECONDS = (4.6, 5.4)


class ThieveTask(CombatTask):
    """Built on the combat task for its HP reading, eating and restocking."""

    def __init__(self, game, step):
        super().__init__(game, step)
        self.stats.update(attempts=0, stuns=0)

    def run_batch(self) -> str:
        g, step = self.game, self.step
        last_hp, misses = self.hp(g.grab()), 0
        for n in range(step.attempts_per_batch):
            img = g.grab()
            hp = self.hp(img)
            if hp < step.eat_below and not self.eat(img):
                if step.when_out_of_food == "stop" or not self.restock():
                    return "exhausted"
                continue
            if step.items and g.inv.is_full(img, step.tools + len(self.tagged(img, step.food))):
                self.full_inventory()
            if step.pouch and n and n % step.open_every == 0:
                slots = self.tagged(img, [step.pouch])
                if slots:
                    g.controls.click_rect(g.layout.slot(min(slots)))   # Open-all
                    g.wait(0.8, 1.2)
            if not g.click_nearest(g.grab(), step.target):
                misses += 1
                if misses >= 10:
                    raise BotError(f"{step.name}: nothing to steal from in sight")
                g.wait(1.5, 2.5)          # stall restocking, or the NPC walked off
                continue
            misses = 0
            self.stats["attempts"] += 1
            self.progressed(1)
            g.wait(1.2, 1.6)
            now_hp = self.hp(g.grab())
            if now_hp < last_hp - 0.01:
                self.stats["stuns"] += 1
                g.wait(*STUN_SECONDS)
            last_hp = now_hp
        self.stats["batches"] += 1
        return "ok"
