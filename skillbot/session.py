"""Staying logged in: detect the login screen and either stop or log back in.

"Logged in" is recognised by sampling a few points of the side-panel frame and
comparing them to colors recorded by ``calibrate``. Credentials are only ever read
from the SKILLBOT_USERNAME / SKILLBOT_PASSWORD environment variables.
"""
import json
import logging
import os
from pathlib import Path

import numpy as np

from .game import Game, StopBot

log = logging.getLogger("skillbot")


def sample(img, points) -> list[list[int]]:
    out = []
    for x, y in points:
        patch = img[y - 2:y + 3, x - 2:x + 3].reshape(-1, img.shape[-1])[:, :3]
        out.append([int(v) for v in patch.mean(axis=0)])
    return out


class Session:
    def __init__(self, game: Game, fingerprint: list[list[int]], tolerance: int = 30):
        self.game = game
        self.fingerprint = np.array(fingerprint)
        self.tolerance = tolerance

    @classmethod
    def load(cls, game: Game, data_dir: Path) -> "Session":
        path = data_dir / "fingerprint.json"
        if not path.exists():
            raise SystemExit("No fingerprint yet: run `python -m skillbot calibrate` while logged in.")
        return cls(game, json.loads(path.read_text()))

    def logged_in(self, img) -> bool:
        now = np.array(sample(img, self.game.layout.fingerprint_points))
        close = np.all(np.abs(now - self.fingerprint) <= self.tolerance, axis=1)
        return close.mean() >= 0.75

    def ensure(self) -> None:
        g = self.game
        if self.logged_in(g.grab()):
            return
        # A short "connection lost" often fixes itself.
        if g.wait_until(self.logged_in, timeout=30, poll=(3, 4)):
            return
        if g.cfg.on_logout == "stop":
            raise StopBot("logged out (on_logout: stop)")
        self.login()

    def logout(self, attempts: int = 6) -> bool:
        """Log out from the logout tab. Retries while the game refuses (10 seconds after
        combat). True once the login screen shows."""
        g = self.game
        for _ in range(attempts):
            if not self.logged_in(g.grab()):
                return True
            g.close_interfaces()
            g.open_tab("logout")
            g.controls.click(g.layout.logout_button)
            if g.wait_until(lambda img: not self.logged_in(img), timeout=8, poll=(1, 1.5)):
                log.info("logged out")
                return True
            g.wait(5, 6)
        return not self.logged_in(g.grab())

    def login(self) -> None:
        g = self.game
        user, password = os.environ.get("SKILLBOT_USERNAME"), os.environ.get("SKILLBOT_PASSWORD")
        if not user or not password:
            raise StopBot("logged out and SKILLBOT_USERNAME / SKILLBOT_PASSWORD are not set")
        attempt = 0
        while not g.cfg.login_attempts or attempt < g.cfg.login_attempts:
            attempt += 1
            log.info("logging in (attempt %d)", attempt)
            g.controls.click(g.layout.login_existing_user)
            g.wait(1.0, 1.5)
            g.controls.press("backspace", presses=40)   # clear a remembered username
            g.controls.type_text(user)
            g.controls.press("tab")
            g.controls.type_text(password)
            g.controls.press("enter")
            g.wait(8, 10)
            g.controls.click(g.layout.login_play)          # "Click here to play"
            if g.wait_until(self.logged_in, timeout=20, poll=(2, 3)):
                log.info("logged in")
                g.setup_camera()
                g.open_tab("inventory")
                return
            g.controls.press("esc")
            backoff = min(60 * 2 ** (attempt - 1), 900)   # server restarts can take a while
            log.warning("login failed, retrying in %ds", backoff)
            g.wait(backoff)
        raise StopBot(f"could not log in after {attempt} attempts")
