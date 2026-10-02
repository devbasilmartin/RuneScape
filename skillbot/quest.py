"""Following RuneLite's Quest Helper (Plugin Hub) through a quest.

Quest Helper highlights what to do next; set its colors to the registry's:
quest_target (NPCs/objects to talk to or use), quest_dialog (the chat option to pick)
and quest_item (inventory items to use). Each action the bot takes, in order:

1. a "Click here to continue" page → space
2. a highlighted chat option → click that line
3. a highlighted inventory item → click it, then the highlighted target if there is one
4. a highlighted NPC/object → click it (walking there if needed)

With nothing highlighted for `idle_timeout` seconds it stops the step and tells you:
either a step it can't do (a puzzle, a fight, text-only instructions) or the quest is
finished. Items the quest needs are your job (or the bank, via `withdraw`).
"""
import logging

import numpy as np

from .colors import Registry
from .dialog import Dialog
from .tasks import Task
from .vision import color_mask

log = logging.getLogger("skillbot")


class QuestTask(Task):
    def __init__(self, game, step):
        super().__init__(game, step)
        reg = Registry.load(game.cfg.colors_file)
        self.target = reg.resolve("quest_target")
        self.option = reg.resolve("quest_dialog")
        self.item = reg.resolve("quest_item")
        self.stats.update(actions=0)

    def dialog_line(self, img):
        """Centre of the highlighted chat option, or None."""
        box = self.game.layout.chatbox
        ys, xs = np.nonzero(color_mask(box.crop(img), self.option, self.game.cfg.color_tolerance))
        if len(ys) < 10:
            return None
        return int(np.median(xs)) + box.x, int(np.median(ys)) + box.y

    def item_slot(self, img):
        g = self.game
        for i in range(28):
            area = g.layout.slot(i).grow(2).crop(img)
            if int(color_mask(area, self.item, g.cfg.color_tolerance).sum()) >= 6:
                return i
        return None

    def act(self) -> bool:
        """Do the next highlighted thing. False when nothing is highlighted."""
        g = self.game
        dialog = Dialog(g)
        img = g.grab()
        if dialog.waiting(img):
            dialog.advance(limit=1)
            return True
        line = self.dialog_line(img)
        if line is not None:
            g.controls.click(line)
            g.wait(0.8, 1.2)
            return True
        slot = self.item_slot(img)
        if slot is not None:
            g.controls.click_rect(g.layout.slot(slot))
            g.wait(0.3, 0.6)
            g.click_nearest(g.grab(), self.target)
            g.wait(1.5, 2.5)
            return True
        if g.click_nearest(img, self.target):
            g.wait(1.5, 2.5)
            return True
        return False

    def run_batch(self) -> str:
        g, step = self.game, self.step
        idle_since = None
        for _ in range(200):
            if self.act():
                idle_since = None
                self.stats["actions"] += 1
                continue
            idle_since = idle_since if idle_since is not None else g.now()
            if g.now() - idle_since >= step.idle_timeout:
                from .notify import notify
                notify(f"quest {step.name!r}: nothing highlighted for "
                       f"{step.idle_timeout:.0f}s; this step needs you (or the quest is done: "
                       f"`quest-done '{step.name}'`)")
                return "exhausted"
            g.wait(1.5, 2.5)
        self.stats["batches"] += 1
        return "ok"
