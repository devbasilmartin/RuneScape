"""Mouse and keyboard output. Coordinates passed in are canvas-relative.

Move the mouse into a screen corner at any time to abort (pyautogui failsafe).
"""
import random
import time

from .layout import Rect


class Controls:
    def __init__(self, screen, rng: random.Random | None = None):
        import pyautogui
        pyautogui.FAILSAFE = True
        pyautogui.PAUSE = 0
        self._pg = pyautogui
        self.screen = screen
        self.rng = rng or random.Random()

    def point_in(self, rect: Rect) -> tuple[int, int]:
        """A point near the middle of ``rect``, so clicks don't land on its edges."""
        cx, cy = rect.center
        x = cx + self.rng.gauss(0, rect.w / 8)
        y = cy + self.rng.gauss(0, rect.h / 8)
        x = min(max(x, rect.x + rect.w * 0.25), rect.x + rect.w * 0.75)
        y = min(max(y, rect.y + rect.h * 0.25), rect.y + rect.h * 0.75)
        return int(x), int(y)

    def click(self, pt, button: str = "left") -> None:
        x, y = self.screen.to_screen(pt)
        self._pg.moveTo(x, y, duration=self.rng.uniform(0.12, 0.3), tween=self._pg.easeOutQuad)
        time.sleep(self.rng.uniform(0.03, 0.08))
        self._pg.click(button=button)

    def click_rect(self, rect: Rect, button: str = "left") -> None:
        self.click(self.point_in(rect), button)

    def press(self, key: str, presses: int = 1) -> None:
        self._pg.press(key, presses=presses, interval=0.03)

    def type_text(self, text: str) -> None:
        self._pg.write(text, interval=self.rng.uniform(0.05, 0.1))

    def hold(self, key: str, seconds: float) -> None:
        self._pg.keyDown(key)
        time.sleep(seconds)
        self._pg.keyUp(key)

    def key_down(self, key: str) -> None:
        self._pg.keyDown(key)

    def key_up(self, key: str) -> None:
        self._pg.keyUp(key)

    def wait(self, lo: float, hi: float | None = None) -> None:
        time.sleep(lo if hi is None else self.rng.uniform(lo, hi))
