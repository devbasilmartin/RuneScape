"""Magic training by casting: teleport spells repeatedly, or High Alchemy on a tagged item.

Each cast: click the spell in the magic tab, then (for alchemy) the item; the game
switches to the inventory by itself and back to the spellbook after the cast. Runes are
tagged stacks; when a stack's tag disappears it's used up.
"""
import logging

from .game import BotError
from .tasks import Task

log = logging.getLogger("skillbot")


class CastTask(Task):
    def ready(self, img) -> bool:
        step = self.step
        tags = set(self.game.inv.tags(img).values())
        return all(r in tags for r in step.runes) and (step.on_item is None or step.on_item in tags)

    def run_batch(self) -> str:
        g, step = self.game, self.step
        if not self.ready(g.grab()):
            if not step.withdraw or not self.bank_and_restock() or not self.ready(g.grab()):
                log.info("%s: out of runes or items", step.name)
                return "exhausted"
        g.open_tab("magic")
        misses = 0
        for _ in range(step.casts_per_batch):
            img = g.grab()
            if not self.ready(img):
                break
            g.controls.click(step.spell)
            g.wait(0.3, 0.5)
            if step.on_item:
                slots = self.tagged(g.grab(), [step.on_item])
                if not slots:
                    misses += 1
                    if misses >= 3:
                        raise BotError(f"{step.name}: {step.on_item} keeps disappearing")
                    continue
                g.controls.click_rect(g.layout.slot(min(slots)))
            g.wait(step.cast_delay, step.cast_delay + 0.4)
            self.progressed(1)
        g.open_tab("inventory")
        self.stats["batches"] += 1
        return "ok"
