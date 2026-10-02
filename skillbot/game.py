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
        self.run = None        # RunManager, when run: always
        self.reported = set()  # out-of-stock notices already sent

    def keep_running(self) -> None:
        if self.run is not None:
            self.run.maintain()

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
        self.keep_running()    # clicking a highlight usually means walking to it
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
    ARRIVED_PX = 30     # a route tile this close to the player means we're standing on it

    def walk(self, route: str | None, color) -> None:
        """Make ``color`` visible by following a route of Ground Marker tiles.

        Always clicks the furthest tile of the route that is on screen, so the bot can
        start anywhere along the route and never walks back to earlier tiles. Tile colors
        within one route must be distinct.
        """
        if self.blobs(self.grab(), color):
            return
        tiles = self.cfg.routes.get(route, []) if route else []
        clicked, clicked_at, retries = -1, self.now(), 0
        deadline = self.now() + self.cfg.walk_timeout * max(1, len(tiles))
        while self.now() < deadline:
            self.keep_running()
            img = self.grab()
            if self.blobs(img, color):
                return
            visible = [i for i, t in enumerate(tiles) if self.blobs(img, t)]
            furthest = max(visible, default=-1)
            if furthest > clicked:
                self.click_nearest(img, tiles[furthest])
                log.info("walking (%s) to tile %d/%d", route, furthest + 1, len(tiles))
                clicked, clicked_at, retries = furthest, self.now(), 0
            elif clicked >= 0 and self.highlight_near(img, tiles[clicked], self.player,
                                                      self.ARRIVED_PX):
                raise BotError(f"route {route!r}: reached tile {clicked + 1} but can see "
                               f"neither the next tile nor the target {color}")
            elif clicked >= 0 and self.now() - clicked_at > self.cfg.walk_timeout:
                if retries or clicked not in visible:
                    raise BotError(f"route {route!r}: stuck walking to tile {clicked + 1}")
                self.click_nearest(img, tiles[clicked])      # misclick or blocked; once more
                clicked_at, retries = self.now(), 1
            elif clicked < 0:
                raise BotError(f"highlight {color} not on screen and no tile of route "
                               f"{route!r} is visible")
            self.wait(0.6, 0.9)
        raise BotError(f"route {route!r}: timed out")

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

    def deposit(self, before: dict[int, str], keep=()) -> None:
        """Left-click one slot per item; with bank quantity "All" that deposits the stack.

        If Inventory Tags are drawn inside the bank, re-read them after each click;
        otherwise click every remembered slot (clicking an emptied slot does nothing).
        """
        before = {i: n for i, n in before.items() if n not in keep}
        if self.inv.any_tag_visible(self.grab()):
            for _ in range(len(before) + 1):
                tagged = {i: n for i, n in self.inv.tags(self.grab()).items() if n not in keep}
                if not tagged:
                    return
                self.controls.click_rect(self.layout.slot(min(tagged)))
                self.wait(0.5, 0.9)
            raise BotError("could not empty the inventory in the bank")
        for i in sorted(before):
            self.controls.click_rect(self.layout.slot(i))
            self.wait(0.3, 0.6)

    def open_bank_tab(self, tab: str) -> None:
        """Show a Bank Tags tab by searching ``tag:<name>``."""
        self.controls.click(self.layout.bank_search)
        self.wait(0.4, 0.7)
        self.controls.type_text(f"tag:{tab}")
        self.wait(0.6, 0.9)

    def withdraw(self, entries, tab: str | None = None) -> None:
        from .config import Withdraw
        entries = [w if isinstance(w, Withdraw) else Withdraw.parse(w) for w in entries]
        if tab and entries:
            self.open_bank_tab(tab)
        for w in entries:
            if w.quantity:
                self.controls.click(self.layout.bank_quantity[w.quantity])
                self.wait(0.3, 0.5)
            self.controls.click_rect(self.layout.bank_slot(w.slot))
            self.wait(0.5, 0.9)

    def missing(self, entries) -> list[str]:
        """Withdrawn items that didn't arrive (out of stock: only a placeholder left)."""
        have = set(self.inv.tags(self.grab()).values())
        return [w.item for w in entries if getattr(w, "item", None) and w.item not in have]

    def bank(self, route: str | None, withdraw=(), keep=(), tab: str | None = None) -> list[str]:
        """Deposit, withdraw and close. Returns the names of withdrawn items that are out
        of stock."""
        before = self.open_bank(route)
        self.deposit(before, keep)
        self.withdraw(withdraw, tab)
        self.close_interfaces()
        if tab and withdraw:
            self.close_interfaces()      # the first Esc may only end the search
        return self.missing(withdraw)

    def out_of_stock(self, step_name: str, items) -> None:
        """Tell you once per run which supplies a step has run out of."""
        from .notify import notify
        key = (step_name, tuple(sorted(items)))
        if key not in self.reported:
            self.reported.add(key)
            notify(f"{step_name}: the bank is out of {', '.join(items)} (buy more; the bot "
                   "moves on to other steps meanwhile)")
