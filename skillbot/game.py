"""Actions shared by every task: finding highlights, walking, banking, tabs."""
import logging
import time

from . import vision
from .config import Config
from .inventory import Inventory

log = logging.getLogger("skillbot")


class BotError(RuntimeError):
    """Something went wrong that recovery (close interfaces, re-login, retry) may fix."""


class StopBot(RuntimeError):
    """Stop for good: the plan is finished or a setting says to stop."""


class Game:
    def __init__(self, cfg: Config, screen, controls, inventory: Inventory, now=time.monotonic):
        self.cfg = cfg
        self.screen = screen
        self.controls = controls
        self.inv = inventory
        self.now = now
        self.layout = cfg.layout

    def grab(self):
        return self.screen.grab()

    def wait(self, lo, hi=None):
        self.controls.wait(lo, hi)

    @property
    def player(self):
        return self.layout.viewport.center

    # ---- highlights ----------------------------------------------------------------------
    def blobs(self, img, color):
        return vision.find_blobs(img, color, self.cfg.color_tolerance, region=self.layout.viewport)

    def nearest(self, img, color):
        return vision.nearest(self.blobs(img, color), self.player)

    def click_nearest(self, img, color) -> bool:
        blob = self.nearest(img, color)
        if blob is None:
            return False
        self.controls.click_rect(blob.rect)
        return True

    def highlight_near(self, img, color, point, radius: int) -> bool:
        px, py = point
        return any((b.center[0] - px) ** 2 + (b.center[1] - py) ** 2 <= radius ** 2
                   for b in self.blobs(img, color))

    def wait_until(self, check, timeout: float, poll=(0.6, 0.9)) -> bool:
        deadline = self.now() + timeout
        while self.now() < deadline:
            self.wait(*poll)
            if check(self.grab()):
                return True
        return False

    # ---- walking -------------------------------------------------------------------------
    def walk(self, route: str | None, color) -> None:
        """Make ``color`` visible: if it isn't, click the route's Ground Marker tiles in order."""
        if self.blobs(self.grab(), color):
            return
        for tile in self.cfg.routes.get(route, []) if route else []:
            if not self.click_nearest(self.grab(), tile):
                raise BotError(f"route {route!r}: no tile marked {tile} on screen")
            log.info("walking (%s) to tile %s", route, tile)
            if self.wait_until(lambda img: bool(self.blobs(img, color)), self.cfg.walk_timeout):
                return
        raise BotError(f"highlight {color} not on screen (route {route!r}); "
                       "check the color or mark more route tiles")

    # ---- interface -----------------------------------------------------------------------
    def open_tab(self, name: str) -> None:
        self.controls.click(self.layout.tabs[name])
        self.wait(0.4, 0.7)

    def close_interfaces(self) -> None:
        self.controls.press("esc")
        self.wait(0.4, 0.7)

    def setup_camera(self) -> None:
        self.controls.click(self.layout.compass)   # face north for a consistent view
        self.wait(0.4, 0.7)
        self.controls.hold("up", self.controls.rng.uniform(1.5, 2.0))  # max camera pitch

    def drop(self, names=None) -> None:
        tags = self.inv.tags(self.grab())
        slots = sorted(i for i, n in tags.items() if names is None or n in names)
        log.info("dropping %d items", len(slots))
        self.controls.key_down("shift")
        try:
            for i in slots:
                self.controls.click_rect(self.layout.slot(i))
                self.wait(0.08, 0.2)
        finally:
            self.controls.key_up("shift")
        self.wait(0.4, 0.8)

    # ---- bank ----------------------------------------------------------------------------
    def open_bank(self, route: str | None) -> dict[int, str]:
        """Walk to and open the bank. Returns the tagged items as they were before opening."""
        self.walk(route, self.cfg.bank_color)
        img = self.grab()
        before = self.inv.tags(img)   # item positions don't change when the bank opens
        if not self.click_nearest(img, self.cfg.bank_color):
            raise BotError("bank highlight disappeared")
        self.wait(self.cfg.bank_open_wait, self.cfg.bank_open_wait + 1.0)
        return before

    def deposit(self, before: dict[int, str]) -> None:
        """Left-click one slot per item; with bank quantity "All" that deposits the stack.

        If Inventory Tags are drawn inside the bank, re-read them after each click;
        otherwise click every remembered slot (clicking an emptied slot does nothing).
        """
        if self.inv.any_tag_visible(self.grab()):
            for _ in range(len(before) + 1):
                tagged = self.inv.tags(self.grab())
                if not tagged:
                    return
                self.controls.click_rect(self.layout.slot(min(tagged)))
                self.wait(0.5, 0.9)
            raise BotError("could not empty the inventory in the bank")
        for i in sorted(before):
            self.controls.click_rect(self.layout.slot(i))
            self.wait(0.3, 0.6)

    def withdraw(self, bank_slots) -> None:
        for i in bank_slots:
            self.controls.click_rect(self.layout.bank_slot(i))
            self.wait(0.5, 0.9)

    def bank(self, route: str | None, withdraw=()) -> None:
        before = self.open_bank(route)
        self.deposit(before)
        self.withdraw(withdraw)
        self.close_interfaces()
