"""The fishing loop: fish until full, then drop / bank / cook, and repeat."""
import logging
import time

from . import vision
from .config import Config
from .inventory import Inventory

log = logging.getLogger("fishbot")


class BotError(RuntimeError):
    pass


class FishingBot:
    def __init__(self, cfg: Config, screen, controls, inventory: Inventory,
                 bank_template=None, now=time.monotonic):
        self.cfg = cfg
        self.screen = screen
        self.controls = controls
        self.inv = inventory
        self.bank_template = bank_template   # screenshot region proving the bank is open
        self.now = now
        self.layout = cfg.layout
        self.fishing = False
        self.last_count = -1
        self.last_progress = 0.0
        self.stats = {"trips": 0, "fish": 0}

    # ---- helpers -------------------------------------------------------------------------
    @property
    def player(self):
        return self.layout.viewport.center

    def blobs(self, img, color):
        return vision.find_blobs(img, color, self.cfg.color_tolerance, region=self.layout.viewport)

    def click_nearest(self, img, color) -> bool:
        blob = vision.nearest(self.blobs(img, color), self.player)
        if blob is None:
            return False
        self.controls.click_rect(blob.rect)
        return True

    def walk_until_visible(self, route: str, color) -> None:
        """Click minimap waypoints of ``route`` until ``color`` shows up in the viewport."""
        waypoints = self.cfg.routes.get(route) or []
        cx, cy = self.layout.minimap_center
        for dx, dy in waypoints:
            log.info("walking (%s) via minimap offset %+d,%+d", route, dx, dy)
            self.controls.click((cx + dx + self.controls.rng.randint(-2, 2),
                                 cy + dy + self.controls.rng.randint(-2, 2)))
            deadline = self.now() + self.cfg.walk_timeout
            while self.now() < deadline:
                self.controls.wait(0.6, 0.9)
                if self.blobs(self.screen.grab(), color):
                    return
        raise BotError(f"route {route!r} ended without finding the highlight {color}; "
                       "check the highlight color or add waypoints in config.yaml")

    def setup_camera(self) -> None:
        self.controls.click(self.layout.compass)   # face north so minimap routes line up
        self.controls.wait(0.4, 0.7)
        self.controls.hold("up", self.controls.rng.uniform(1.5, 2.0))  # max camera pitch

    # ---- fishing -------------------------------------------------------------------------
    def spot_nearby(self, img) -> bool:
        px, py = self.player
        r2 = self.cfg.spot_adjacent_px ** 2
        return any((b.center[0] - px) ** 2 + (b.center[1] - py) ** 2 <= r2
                   for b in self.blobs(img, self.cfg.fishing_color))

    def step_fish(self, img) -> None:
        count = len(self.inv.new_slots(img))
        t = self.now()
        if count != self.last_count:
            if count > self.last_count >= 0:
                self.stats["fish"] += count - self.last_count
            self.last_count, self.last_progress = count, t
        if (self.fishing and t - self.last_progress < self.cfg.idle_timeout
                and self.spot_nearby(img)):
            self.controls.wait(0.8, 1.4)
            return
        if not self.click_nearest(img, self.cfg.fishing_color):
            self.walk_until_visible("to_spot", self.cfg.fishing_color)
            return
        log.info("clicked fishing spot (%d fish in inventory)", count)
        self.fishing, self.last_progress = True, self.now()
        self.controls.wait(2.5, 4.0)   # walk to the spot and start the animation

    # ---- inventory full ------------------------------------------------------------------
    def drop_all(self) -> None:
        img = self.screen.grab()
        slots = self.inv.new_slots(img)
        log.info("dropping %d items", len(slots))
        self.controls.key_down("shift")
        try:
            for i in slots:
                self.controls.click_rect(self.layout.slot(i))
                self.controls.wait(0.08, 0.2)
        finally:
            self.controls.key_up("shift")
        self.controls.wait(0.4, 0.8)

    def cook(self) -> None:
        img = self.screen.grab()
        if not self.blobs(img, self.cfg.cook_color):
            self.walk_until_visible("to_cook", self.cfg.cook_color)
        for name in self.cfg.raw_items:
            for _attempt in range(5):     # level-ups interrupt cooking; retry
                img = self.screen.grab()
                slots = self.inv.slots_with(img, name)
                if not slots:
                    break
                log.info("cooking %d x %s", len(slots), name)
                self.controls.click_rect(self.layout.slot(slots[0]))   # Use
                self.controls.wait(0.3, 0.6)
                if not self.click_nearest(img, self.cfg.cook_color):
                    raise BotError("cooking target not visible")
                self.controls.wait(1.8, 2.6)       # walk to it and open the cook menu
                self.controls.press("space")        # cook all
                self.wait_for_cooking(name, len(slots))

    def wait_for_cooking(self, name: str, remaining: int) -> None:
        last_change = self.now()
        while self.now() - last_change < self.cfg.cook_idle_timeout:
            self.controls.wait(1.0, 1.5)
            n = len(self.inv.slots_with(self.screen.grab(), name))
            if n == 0:
                return
            if n < remaining:
                remaining, last_change = n, self.now()

    def bank(self) -> None:
        img = self.screen.grab()
        if not self.click_nearest(img, self.cfg.bank_color):
            self.walk_until_visible("to_bank", self.cfg.bank_color)
            if not self.click_nearest(self.screen.grab(), self.cfg.bank_color):
                raise BotError("bank highlight disappeared")
        self.wait_for_bank()
        # Left-click deposits the whole stack when the bank quantity is set to "All".
        for _ in range(30):
            slots = self.inv.new_slots(self.screen.grab(), in_bank=True)
            if not slots:
                break
            self.controls.click_rect(self.layout.slot(slots[0]))
            self.controls.wait(0.5, 0.9)
        else:
            raise BotError("could not empty the inventory in the bank")
        self.controls.press("esc")
        self.controls.wait(0.5, 0.9)

    def wait_for_bank(self) -> None:
        tmpl = self.bank_template
        deadline = self.now() + self.cfg.bank_open_wait + (6 if tmpl is not None else 0)
        while self.now() < deadline:
            self.controls.wait(0.5, 0.8)
            if tmpl is not None and vision.match_score(self.screen.grab(), tmpl)[0] > 0.85:
                self.controls.wait(0.3, 0.6)
                return
        if tmpl is not None:
            raise BotError("bank did not open")

    def handle_full(self) -> None:
        log.info("inventory full")
        mode = self.cfg.mode
        if mode.startswith("cook"):
            self.cook()
        if mode.endswith("drop"):
            self.drop_all()
        else:
            self.bank()
        self.stats["trips"] += 1
        self.fishing, self.last_count = False, -1
        log.info("trip %d done, %d fish caught so far", self.stats["trips"], self.stats["fish"])

    # ---- main loop -----------------------------------------------------------------------
    def run(self) -> None:
        if self.cfg.mode.startswith("cook"):
            missing = [n for n in self.cfg.raw_items if n not in self.inv.templates]
            if missing:
                raise BotError(f"cook mode needs item templates for {missing}; "
                               "use `python -m fishbot capture-item NAME SLOT`")
        end = self.now() + self.cfg.max_runtime_minutes * 60
        self.setup_camera()
        while self.now() < end:
            img = self.screen.grab()
            if self.inv.is_full(img):
                self.handle_full()
            else:
                self.step_fish(img)
        log.info("max runtime reached: %s", self.stats)
