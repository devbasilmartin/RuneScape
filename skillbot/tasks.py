"""Training methods. Each task's ``run_batch`` handles one inventory load and returns
"ok", or "exhausted" when it has run out of supplies."""
import logging

from .config import Step
from .game import BotError, Game

log = logging.getLogger("skillbot")

TARGET_PX = 15       # how far a highlight may be from where it was and still be "the same one"


class Task:
    def __init__(self, game: Game, step: Step):
        self.game = game
        self.step = step
        self.stats = {"batches": 0, "items": 0}
        self.on_progress = None     # called after each item gained or used up

    def progressed(self, n: int) -> None:
        self.stats["items"] += n
        if self.on_progress:
            self.on_progress()

    def tagged(self, img, names):
        return [i for i, n in self.game.inv.tags(img).items() if n in names]

    def has_items(self, img) -> bool:
        return bool(self.tagged(img, self.step.items))

    def bank_and_restock(self, keep=None) -> bool:
        """Deposit (except the step's ``keep`` items), withdraw this step's supplies and
        check they arrived. False (and one notification) when the bank is out of something."""
        step = self.step
        keep = step.keep if keep is None else keep
        missing = self.game.bank(step.walk.get("bank"), step.withdraw, keep=keep,
                                 tab=step.bank_tab)
        if missing:
            self.game.out_of_stock(step.name, missing)
        return not missing

    def run_batch(self) -> str:
        raise NotImplementedError


class GatherTask(Task):
    """Woodcutting, mining, fishing: click the nearest highlighted resource until full.

    Object Markers highlight one object ID on one tile, so a chopped tree or mined rock
    loses its highlight when it depletes; a fishing spot that moves does the same.
    """

    def __init__(self, game, step):
        super().__init__(game, step)
        self.processor = None
        if step.process:
            sub = {"name": f"{step.name} (process)", "skill": step.skill, "task": "process",
                   "tools": step.tools, **step.process}
            self.processor = ProcessTask(game, Step.from_dict(sub))

    def run_batch(self) -> str:
        g, step = self.game, self.step
        working, last_count, last_progress, failed = False, -1, g.now(), 0
        target_pos = g.player
        while not g.inv.is_full(img := g.grab(), step.tools):
            count = len(self.tagged(img, step.items))
            if count != last_count:
                if count > last_count >= 0:
                    self.progressed(count - last_count)
                    failed = 0
                last_count, last_progress = count, g.now()
            if (working and g.now() - last_progress < step.idle_timeout
                    and g.highlight_near(img, step.target, target_pos, TARGET_PX)):
                g.wait(0.8, 1.4)
                continue
            if failed >= 4:
                raise BotError(f"{step.name}: clicked {failed} times without gaining an item; "
                               "is everything you gather tagged in Inventory Tags?")
            g.walk(step.walk.get("target"), step.target)
            if not g.click_nearest(g.grab(), step.target):
                continue
            failed += working
            working, last_progress = True, g.now()
            g.wait(2.5, 4.0)   # walk over and start the animation
            # Once we're standing next to it, the resource we're using is the closest one.
            blob = g.nearest(g.grab(), step.target)
            target_pos = blob.center if blob else g.player
        log.info("%s: inventory full", step.name)
        if self.processor:
            self.processor.process_inventory()
        if step.when_full == "drop":
            g.drop(names=set(step.items))
        else:
            g.bank(step.walk.get("bank"))
        self.stats["batches"] += 1
        return "ok"


class ProcessTask(Task):
    """Cooking, smelting, smithing, crafting: turn tagged inputs into something else at
    a highlighted station, restocking from the bank."""

    def restock(self) -> bool:
        return self.bank_and_restock() and self.has_items(self.game.grab())

    def run_batch(self) -> str:
        if not self.has_items(self.game.grab()) and not self.restock():
            log.info("%s: out of supplies", self.step.name)
            return "exhausted"
        self.process_inventory()
        self.stats["batches"] += 1
        return "ok"

    def _use_item(self, img) -> str | None:
        use = self.step.use_item
        if use == "any":
            slots = self.tagged(img, self.step.items)
            return self.game.inv.tags(img)[min(slots)] if slots else None
        return use

    def process_inventory(self) -> None:
        g, step = self.game, self.step
        for _attempt in range(8):      # level-up dialogs interrupt make-all; start again
            img = g.grab()
            remaining = len(self.tagged(img, step.items))
            if not remaining:
                return
            if step.with_item:
                if not self._use_on_item(img):
                    return
                self._confirm()
                self._wait_for_progress(remaining)
                continue
            g.walk(step.walk.get("target"), step.target)
            img = g.grab()
            use = self._use_item(img)
            if use:
                slots = self.tagged(img, [use])
                if not slots:
                    return
                g.controls.click_rect(g.layout.slot(min(slots)))
                g.wait(0.3, 0.6)
            if not g.click_nearest(img, step.target):
                raise BotError(f"{step.name}: station not visible")
            g.wait(1.8, 2.6)       # walk over; the make menu / interface opens
            self._confirm()
            self._wait_for_progress(remaining)
        raise BotError(f"{step.name}: inputs are not being used up")

    def _use_on_item(self, img) -> bool:
        """Item-on-item (knife on logs, herb on vial...): click one, then the other."""
        g, step = self.game, self.step
        use = self._use_item(img)
        first = self.tagged(img, [use]) if use else []
        second = [i for i in self.tagged(img, [step.with_item]) if i not in first[:1]]
        if not first or not second:
            return False
        a = min(first)
        b = min(second, key=lambda i: abs(i - a))        # the nearest one: shortest mouse move
        g.controls.click_rect(g.layout.slot(a))
        g.wait(0.2, 0.4)
        g.controls.click_rect(g.layout.slot(b))
        g.wait(1.0, 1.5)           # the make menu opens
        return True

    def _confirm(self) -> None:
        g = self.game
        for action in self.step.confirm:
            if "key" in action:
                g.controls.press(action["key"])
            else:
                g.controls.click(tuple(action["click"]))
            g.wait(0.3, 0.6)

    def _wait_for_progress(self, remaining: int) -> None:
        g, last_change = self.game, self.game.now()
        while g.now() - last_change < self.step.idle_timeout:
            g.wait(1.0, 1.5)
            n = len(self.tagged(g.grab(), self.step.items))
            if n == 0:
                return
            if n < remaining:
                self.progressed(remaining - n)
                remaining, last_change = n, g.now()


class FiremakingTask(Task):
    """Light logs in a line starting from a Ground Marker tile (``target``)."""

    def run_batch(self) -> str:
        g, step = self.game, self.step
        if not self.has_items(g.grab()):
            if not self.bank_and_restock() or not self.has_items(g.grab()):
                log.info("%s: out of logs", step.name)
                return "exhausted"
        self._go_to_start()
        stuck = 0
        while slots := self.tagged(g.grab(), step.items):
            slot = min(slots)
            g.controls.click_rect(g.layout.slot(step.tool_slot))    # tinderbox
            g.wait(0.2, 0.4)
            g.controls.click_rect(g.layout.slot(slot))              # on the log
            lit = g.wait_until(lambda img: slot not in self.tagged(img, step.items),
                               timeout=step.idle_timeout)
            if lit:
                self.progressed(1)
                stuck = 0
                g.wait(0.6, 1.0)   # the player steps west after lighting
                continue
            stuck += 1       # probably standing on a fire or at the end of the lane
            if stuck >= 3:
                raise BotError(f"{step.name}: logs will not light")
            self._go_to_start()
        self.stats["batches"] += 1
        return "ok"

    def _go_to_start(self) -> None:
        g = self.game
        g.walk(self.step.walk.get("start"), self.step.target)
        if not g.click_nearest(g.grab(), self.step.target):
            raise BotError(f"{self.step.name}: start tile not visible")
        g.wait_until(lambda img: g.highlight_near(img, self.step.target, g.player, 25),
                     timeout=g.cfg.walk_timeout)

